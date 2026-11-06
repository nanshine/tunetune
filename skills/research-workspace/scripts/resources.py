#!/usr/bin/env python3
"""Inspect or fetch explicit resources. This tool neither grants access nor executes downloaded code."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SPEC = importlib.util.spec_from_file_location("resource_records", Path(__file__).with_name("records.py"))
records = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(records)
MAX_FILES = 10000


def source_url(value):
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use a public resource URL without credentials, query or fragment")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")):
        raise ValueError("Resource URLs require HTTPS (HTTP is allowed only on loopback)")
    if not parsed.hostname:
        raise ValueError("Expected a resource URL")
    return value


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Redirect contains credentials or fragment")
        source_url(parsed._replace(query="").geturl())
        # Do not send authorization headers or credentials to redirected hosts.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ValueError("Resource preparation exceeded its time limit")
    return seconds


def download(url, output, budget, deadline, expected=None, internal=False):
    if not internal:
        source_url(url)
    digest = hashlib.sha256()
    count = 0
    opener = build_opener(ProxyHandler({}) if urlsplit(url).hostname in ("127.0.0.1", "localhost", "::1") else ProxyHandler(), Redirects())
    with opener.open(Request(url, headers={"User-Agent": "TuneTune/0.7.0"}), timeout=remaining(deadline)) as response:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > budget:
            raise ValueError("Resource exceeds --max-bytes")
        with output.open("xb") as stream:
            while True:
                remaining(deadline)
                chunk = response.read(min(65536, budget - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > budget:
                    raise ValueError("Resource exceeds --max-bytes")
                stream.write(chunk)
                digest.update(chunk)
    if expected and digest.hexdigest() != expected:
        raise ValueError("Downloaded SHA-256 differs from --sha256")
    return count, digest.hexdigest()


def safe_name(value):
    parts = records.parts(value)
    if any(x.startswith(".") or x in ("__pycache__", "node_modules") for x in parts):
        raise ValueError("Hidden or cached resource paths are not accepted")
    return parts


def git_files(source, revision, stage, limit, deadline):
    repository = stage / ".git"
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(stage),
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_TERMINAL_PROMPT": "0"}
    def git(*args):
        return subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, "-c", "protocol.file.allow=never",
                               "--git-dir=" + str(repository), *args], env=environment, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining(deadline)).stdout
    git("init", "--bare")
    git("fetch", "--depth=1", "--no-tags", source, revision)
    if git("rev-parse", "FETCH_HEAD").decode().strip() != revision:
        raise ValueError("Git fetched a different commit")
    entries = git("ls-tree", "-r", "-l", "-z", revision).split(b"\0")
    files = []
    total = 0
    for entry in filter(None, entries):
        metadata, name = entry.split(b"\t", 1)
        mode, kind, ident, size = metadata.split()
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("Git resources cannot contain links or submodules")
        path = name.decode("utf-8")
        # Repository metadata is unnecessary, not a reason to discard an otherwise useful repository.
        if any(p.startswith(".") for p in records.parts(path)):
            continue
        safe_name(path)
        total += int(size)
        files.append((path, ident.decode(), int(size)))
        if total > limit or len(files) > MAX_FILES:
            raise ValueError("Git resource exceeds file or byte limit")
    for path, ident, size in files:
        target = stage.joinpath(*safe_name(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        content = git("cat-file", "blob", ident)
        if len(content) != size:
            raise ValueError("Git object size changed")
        target.write_bytes(content)
    shutil.rmtree(repository)
    return total


def model_files(source, revision, stage, limit, deadline):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", source):
        raise ValueError("Model source must be a public Hugging Face owner/repository ID")
    metadata = stage / ".metadata"
    download(f"https://huggingface.co/api/models/{source}/revision/{revision}?blobs=true", metadata,
             min(limit, 16 * 1024 * 1024), deadline, internal=True)
    info = json.loads(metadata.read_text())
    metadata.unlink()
    if info.get("sha") != revision:
        raise ValueError("Model repository returned a different revision")
    files = []
    total = 0
    for item in info.get("siblings", []):
        name = item["rfilename"]
        if any(p.startswith(".") for p in records.parts(name)):
            continue
        safe_name(name)
        size = item.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("Model file size is unknown; inspect the source before fetching")
        total += size
        files.append((name, size))
    if not files or total > limit or len(files) > MAX_FILES:
        raise ValueError("Model resource exceeds file or byte limit, or is empty")
    consumed = 0
    for name, size in files:
        target = stage.joinpath(*safe_name(name))
        target.parent.mkdir(parents=True, exist_ok=True)
        count, _ = download(f"https://huggingface.co/{source}/resolve/{revision}/{quote(name, safe='/')}",
                            target, limit - consumed, deadline)
        if count != size:
            raise ValueError("Model file size differs from repository metadata")
        consumed += count
    return consumed


def publish_directory(stage, parent_fd, name):
    """Exclusive atomic directory rename on supported macOS/Linux, never replacing a destination."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        method = library.renameatx_np
        flags = 4  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        method = library.renameat2
        flags = 1  # RENAME_NOREPLACE
    else:
        raise ValueError("Exclusive directory publication requires macOS or Linux rename support")
    method.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    method.restype = ctypes.c_int
    source_fd = os.open(stage.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if method(source_fd, os.fsencode(stage.name), parent_fd, os.fsencode(name), flags) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    finally:
        os.close(source_fd)


def prepare(project, source, destination, kind="http", revision=None, sha256=None,
            max_bytes=1024 ** 3, timeout=300, fetch=False):
    if type(max_bytes) is not int or max_bytes <= 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Provide positive --max-bytes and finite --timeout")
    parts = safe_name(destination)
    if parts[0] not in ("resources", "inputs"):
        raise ValueError("Resource destination must be inside resources/ or inputs/")
    if kind not in ("http", "git", "model"):
        raise ValueError("Unknown resource kind")
    if kind != "model":
        source_url(source)
    elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", source):
        raise ValueError("Model source must be a public Hugging Face owner/repository ID")
    if kind in ("git", "model") and not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ValueError("Git and model resources require a fixed 40-character commit revision")
    if sha256 is not None and (kind != "http" or not re.fullmatch(r"[0-9a-f]{64}", sha256)):
        raise ValueError("--sha256 requires an HTTP resource and a SHA-256 value")
    tree = records.Tree(project)
    try:
        records.check_installed_metadata(tree)
        if tree.exists("project.json") and records.strict(tree.read("project.json")).get("schema_version") != 4:
            raise ValueError("Incompatible project format; format 4 is required")
        if tree.exists(destination):
            raise ValueError("Resource destination already exists")
        result = dict(kind=kind, source=source, revision=revision, destination=destination,
                      max_bytes=max_bytes, expected_bytes=None, state="planned")
        if not fetch:
            # Read-only: inspect any existing parent without creating directories.
            for index in range(1, len(parts)):
                if tree.exists("/".join(parts[:index])):
                    with tree.directory(parts[:index]):
                        pass
            return result
        deadline = time.monotonic() + timeout
        with tree.locked():
            if tree.exists(destination):
                raise ValueError("Resource destination already exists")
            with tree.directory(parts[:-1], create=True) as parent:
                # Private staging is outside the project; publication fails safely across filesystems.
                with tempfile.TemporaryDirectory(prefix="tunetune-resource-") as temporary:
                    stage = Path(temporary) / "content"
                    if kind == "http":
                        count, digest = download(source, stage, max_bytes, deadline, sha256)
                        os.link(stage, parts[-1], dst_dir_fd=parent, follow_symlinks=False)
                        result["sha256"] = digest
                    else:
                        stage.mkdir()
                        count = (git_files if kind == "git" else model_files)(source, revision, stage, max_bytes, deadline)
                        publish_directory(stage, parent, parts[-1])
                    os.fsync(parent)
        return dict(result, state="prepared", actual_bytes=count)
    finally:
        tree.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "fetch"))
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--kind", choices=("http", "git", "model"), default="http")
    parser.add_argument("--revision")
    parser.add_argument("--sha256")
    parser.add_argument("--max-bytes", type=int, default=1024 ** 3)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    try:
        result = prepare(args.project, args.source, args.destination, args.kind, args.revision,
                         args.sha256, args.max_bytes, args.timeout, args.action == "fetch")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Avoid child process stderr, which may contain remote credentials or private repository content.
        message = "Git preparation failed" if isinstance(error, subprocess.SubprocessError) else str(error)
        print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
