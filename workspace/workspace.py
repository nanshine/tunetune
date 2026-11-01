"""Local, file-backed research workspace. Writes only feedback and project-name metadata; no research execution."""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import stat
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import unicodedata
import uuid

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILES = 2000
MAX_ENTRIES = 10000
LOG_PREVIEW_BYTES = 64 * 1024
MAX_BODY_BYTES = 128 * 1024
MAX_TEXT_LENGTH = 16000
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
# A closed allowlist: wildcard matches exactly one safe path component.
PATTERNS = (
    "project.json", "goal.json", "resources.json", "candidates.json",
    "workspace.json", "review.md", "resources/status.json",
    "evaluation/draft/definition.json", "evaluation/versions/*/definition.json",
    "experiments/*/config.json", "experiments/*/status.json",
    "experiments/*/artifacts.json", "experiments/*/analysis.md", "experiments/*/train.log",
    "assessments/*/config.json", "assessments/*/status.json",
    "assessments/*/result.json", "assessments/*/outputs.jsonl",
    "releases/*.json", "acceptance/*/config.json", "acceptance/*/outputs.jsonl",
    "feedback/requests/*.json", "feedback/responses/*.json",
    "feedback/incoming/*.json", "feedback/handled/*.json",
)


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parts(path):
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError("Unsafe relative path")
    result = path.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in result):
        raise ValueError("Unsafe relative path")
    return result


def recognized(path):
    try:
        segments = parts(path)
    except ValueError:
        return False
    for pattern in PATTERNS:
        expected = pattern.split("/")
        if len(expected) == len(segments) and all(
            a == b or (a == "*" and b != "") or
            (a == "*.json" and b.endswith(".json") and len(b) > 5)
            for a, b in zip(expected, segments)
        ):
            return True
    return False


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Non-finite JSON number")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            invalid(value)
        return number

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid,
                      parse_float=finite_float)


class SafeTree:
    """Use directory descriptors and O_NOFOLLOW, including during publication."""

    def __init__(self, root):
        self.root = Path(root).absolute()

    @contextmanager
    def directory(self, segments=(), create=False):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for segment in segments:
                if segment in ("", ".", "..") or "/" in segment or "\\" in segment:
                    raise ValueError("Unsafe directory")
                if create:
                    try:
                        os.mkdir(segment, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    @contextmanager
    def locked(self):
        # Share the canonical records writer's nonblocking advisory lock.
        with self.directory([".workspace", "runtime"], create=True) as parent:
            fd = os.open("records.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError("Not a regular lock file")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                yield
            finally:
                os.close(fd)

    def read(self, path, limit=MAX_FILE_BYTES):
        segments = parts(path)
        with self.directory(segments[:-1]) as parent:
            fd = os.open(segments[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError(f"Not a regular file: {path}")
                if before.st_size > limit:
                    raise ValueError(f"File exceeds byte limit: {path}")
                raw = stream.read(limit + 1)
                after = os.fstat(stream.fileno())
                if len(raw) > limit:
                    raise ValueError(f"File exceeds byte limit: {path}")
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns
                ):
                    raise ValueError(f"File changed while reading: {path}")
                return raw

    def publish(self, path, value, internal=False):
        segments = path.split("/") if internal else parts(path)
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        with self.directory(segments[:-1], create=True) as parent:
            temp = ".pending-" + uuid.uuid4().hex
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Link publishes complete bytes without ever replacing an existing record.
                os.link(temp, segments[-1], src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
                os.fsync(parent)
            finally:
                os.unlink(temp, dir_fd=parent)


class Reader:
    def __init__(self, root: Path):
        self.tree = SafeTree(root)
        self.lock = threading.RLock()
        self._files = {}
        self._revision = hashlib.sha256(b"").hexdigest()
        self._synced_at = None

    def _paths(self):
        trie = {}
        for pattern in PATTERNS:
            node = trie
            for segment in pattern.split("/"):
                node = node.setdefault(segment, {})
        count = 0
        found = []

        def walk(fd, node, prefix):
            nonlocal count
            with os.scandir(fd) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_ENTRIES:
                        raise ValueError("Directory entry limit exceeded")
                    name = entry.name
                    key = name if name in node else (
                        "*" if "*" in node else
                        "*.json" if "*.json" in node and name.endswith(".json") else None
                    )
                    if key is None or name.startswith("."):
                        continue
                    path = "/".join(prefix + [name])
                    if entry.is_symlink():
                        raise ValueError(f"Symlink is not allowed: {path}")
                    if node[key]:
                        if not entry.is_dir(follow_symlinks=False):
                            raise ValueError(f"Expected directory: {path}")
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=fd)
                        try:
                            walk(child, node[key], prefix + [name])
                        finally:
                            os.close(child)
                    else:
                        if not recognized(path):
                            raise ValueError("Unsafe recognized filename")
                        found.append(path)
                        if len(found) > MAX_FILES:
                            raise ValueError("Recognized file count limit exceeded")
        with self.tree.directory() as root:
            walk(root, trie, [])
        return sorted(found)

    def _load(self):
        files = {}
        total = 0
        for path in self._paths():
            raw = self.tree.read(path)
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Snapshot byte limit exceeded")
            try:
                if path.endswith(".json"):
                    content = strict_json(raw.decode("utf-8"))
                    if not isinstance(content, dict):
                        raise ValueError("JSON must be an object")
                    if "schema_version" in content and (
                        type(content["schema_version"]) is not int or content["schema_version"] != 1
                    ):
                        raise ValueError("Unsupported schema_version (expected 1)")
                    field = {"goal.json": "examples", "resources.json": "items",
                             "candidates.json": "items"}.get(path)
                    if field in content and not isinstance(content[field], list):
                        raise ValueError(f"{field} must be an array")
                    if path.startswith("assessments/"):
                        if path.endswith("/status.json") and content.get("state") not in ("pending", "running"):
                            raise ValueError("state must be pending/running")
                        if path.endswith("/result.json") and content.get("state") not in ("succeeded", "failed", "cancelled"):
                            raise ValueError("state must be succeeded/failed/cancelled")
                elif path.endswith(".jsonl"):
                    content = [strict_json(line) for line in raw.decode("utf-8").splitlines()
                               if line.strip()]
                    if any(not isinstance(item, dict) for item in content):
                        raise ValueError("JSONL rows must be objects")
                elif path.endswith(".log"):
                    content = raw[-LOG_PREVIEW_BYTES:].decode("utf-8", errors="replace")
                else:
                    content = raw.decode("utf-8")
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"{path}: {exc}") from exc
            files[path] = {"content": content, "sha256": hashlib.sha256(raw).hexdigest()}
        if "project.json" not in files:
            raise ValueError("Missing required project.json")
        if files["project.json"]["content"].get("schema_version") != 1:
            raise ValueError("project.json requires schema_version=1")
        # Published assessment configs are pending intent; results arrive at completion.
        for path in files:
            if path.startswith("experiments/") and path.endswith("/config.json"):
                required = path.removesuffix("config.json") + "status.json"
                if required not in files:
                    raise ValueError(f"Incomplete record: missing {required}")
        return files

    def snapshot(self):
        with self.lock:
            error = None
            try:
                files = self._load()
                revision = hashlib.sha256(json.dumps(
                    [(path, item["sha256"]) for path, item in sorted(files.items())],
                    separators=(",", ":")
                ).encode()).hexdigest()
                self._files, self._revision, self._synced_at = files, revision, now()
            except (OSError, ValueError, RecursionError) as exc:
                error = f"Sync failed: {exc}"
            return {"files": copy.deepcopy(self._files), "revision": self._revision,
                    "synced_at": self._synced_at or now(), "error": error}


class FeedbackError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def save_project_name(reader, body):
    if not isinstance(body, dict) or body.keys() != {"name", "expected_sha256"}:
        raise FeedbackError(400, "Invalid project name fields")
    if not isinstance(body["name"], str):
        raise FeedbackError(400, "Invalid project name")
    name = body["name"].strip()
    if not name or len(name) > 120 or any(
        unicodedata.category(char) in ("Cc", "Cs") for char in body["name"]
    ):
        raise FeedbackError(400, "Project name must be 1–120 characters without control characters")
    expected = body["expected_sha256"]
    if not isinstance(expected, str) or not HASH.fullmatch(expected):
        raise FeedbackError(400, "Invalid expected_sha256")

    def version(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    with reader.lock:
        try:
            with reader.tree.locked(), reader.tree.directory() as parent:
                fd = os.open("project.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent)
                with os.fdopen(fd, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError("Not a regular file: project.json")
                    if before.st_size > MAX_FILE_BYTES:
                        raise ValueError("File exceeds byte limit: project.json")
                    raw = stream.read(MAX_FILE_BYTES + 1)
                    if len(raw) > MAX_FILE_BYTES:
                        raise ValueError("File exceeds byte limit: project.json")
                    if version(before) != version(os.fstat(stream.fileno())):
                        raise ValueError("project.json changed while reading")
                project = strict_json(raw.decode("utf-8"))
                if not isinstance(project, dict) or type(project.get("schema_version")) is not int or project["schema_version"] != 1:
                    raise ValueError("project.json requires schema_version=1")
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise FeedbackError(409, "Project is stale; refresh before renaming")
                project["name"] = name
                raw = (json.dumps(project, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError("File exceeds byte limit: project.json")
                temp = ".pending-" + uuid.uuid4().hex
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    current = os.stat("project.json", dir_fd=parent, follow_symlinks=False)
                    if not stat.S_ISREG(current.st_mode) or version(current) != version(before):
                        raise FeedbackError(409, "project.json changed before renaming")
                    os.replace(temp, "project.json", src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                finally:
                    try:
                        os.unlink(temp, dir_fd=parent)
                    except FileNotFoundError:
                        pass
                return {"name": name, "sha256": hashlib.sha256(raw).hexdigest()}
        except (OSError, ValueError, RecursionError) as exc:
            raise FeedbackError(409, f"Cannot safely save project name: {exc}") from exc


def save_feedback(reader, body):
    allowed = {"id", "kind", "text", "target", "target_sha256", "request_id", "choice", "sample_id"}
    required = {"id", "kind", "text", "target", "target_sha256"}
    if not isinstance(body, dict) or not required <= body.keys() or body.keys() - allowed:
        raise FeedbackError(400, "Invalid feedback fields")
    for key in ("id", "request_id"):
        if key in body and (not isinstance(body[key], str) or not ID.fullmatch(body[key])):
            raise FeedbackError(400, f"Invalid {key}")
    if body["kind"] not in ("comment", "change", "response", "preference", "acceptance"):
        raise FeedbackError(400, "Invalid feedback kind")
    if not isinstance(body["text"], str) or not body["text"].strip() or len(body["text"]) > MAX_TEXT_LENGTH:
        raise FeedbackError(400, "Invalid feedback text")
    for key in ("choice", "sample_id"):
        if key in body and (not isinstance(body[key], str) or not body[key] or len(body[key]) > 1024):
            raise FeedbackError(400, f"Invalid {key}")
    target, digest = body["target"], body["target_sha256"]
    if target is None:
        if digest is not None:
            raise FeedbackError(400, "Hash requires a target")
    elif not recognized(target) or not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise FeedbackError(400, "Invalid target or hash")
    if body["kind"] == "response":
        request_id = body.get("request_id")
        if not request_id or target != f"feedback/requests/{request_id}.json":
            raise FeedbackError(400, "Response must bind to its request")
    record = dict(body, source="workspace")
    folder = "responses" if body["kind"] == "response" else "incoming"
    destination = f"feedback/{folder}/{body['id']}.json"

    def existing():
        for subdir in ("incoming", "responses"):
            path = f"feedback/{subdir}/{body['id']}.json"
            try:
                saved = strict_json(reader.tree.read(path).decode("utf-8"))
            except FileNotFoundError:
                continue
            if not isinstance(saved, dict):
                raise FeedbackError(409, "Existing feedback is invalid")
            comparison = {k: v for k, v in saved.items() if k != "created_at"}
            if path != destination or comparison != record:
                raise FeedbackError(409, "Feedback id already has different content")
            return saved
        return None

    with reader.lock:
        try:
            saved = existing()
            if saved is not None:
                return saved, False
            if target is not None:
                files = reader._load()
                if target not in files or files[target]["sha256"] != digest:
                    raise FeedbackError(409, "Target is missing or stale; refresh before submitting")
                if body["kind"] == "response":
                    question = files[target]["content"]
                    if question.get("status") in ("closed", "handled", "resolved", "answered", "cancelled") or any(
                        question.get(key) for key in ("closed", "handled", "closed_at", "handled_at")
                    ):
                        raise FeedbackError(409, "Question is closed or handled")
                    response_ids = [item["content"].get("id") for path, item in files.items()
                                    if path.startswith("feedback/responses/") and
                                    isinstance(item["content"].get("id"), str) and
                                    item["content"].get("request_id") == request_id]
                    if response_ids:
                        raise FeedbackError(409, "Question already answered; submit a new comment to correct it")
                    evidence = question.get("target")
                    if evidence is not None and (not isinstance(evidence, str) or evidence not in files or
                            files[evidence]["sha256"] != question.get("target_sha256")):
                        raise FeedbackError(409, "Question evidence changed; ask Agent to refresh the question")
                    related = response_ids + [request_id]
                    for path, item in files.items():
                        if path.startswith("feedback/handled/") and (
                            Path(path).stem in related or any(
                                item["content"].get(key) in related
                                for key in ("request_id", "feedback_id", "response_id", "id")
                            )
                        ):
                            raise FeedbackError(409, "Question has been handled")
                    options = question.get("options", [])
                    if not isinstance(options, list):
                        raise FeedbackError(409, "Question options are invalid")
                    if options:
                        values = [option if isinstance(option, str) else
                                  option.get("id", option.get("value")) if isinstance(option, dict)
                                  else None for option in options]
                        if body.get("choice") not in values:
                            raise FeedbackError(400, "Choice is not a request option")
            record["created_at"] = now()
            try:
                reader.tree.publish(destination, record)
            except FileExistsError:
                record.pop("created_at")
                saved = existing()
                if saved is None:
                    raise FeedbackError(409, "Feedback publication conflict")
                return saved, False
            return record, True
        except (OSError, ValueError, RecursionError) as exc:
            raise FeedbackError(409, f"Cannot safely save feedback: {exc}") from exc


class Handler(BaseHTTPRequestHandler):
    server_version = "Workspace"

    def log_message(self, format, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def parse_request(self):
        if not super().parse_request():
            return False
        hosts = self.headers.get_all("Host", [])
        port = self.server.server_address[1]
        if len(hosts) != 1 or hosts[0] not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self.reply(403, {"error": "Exact loopback Host required"})
            return False
        return True

    def reply(self, status, value, mime="application/json; charset=utf-8"):
        data = json.dumps(value, ensure_ascii=True).encode() if isinstance(value, dict) else value
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "connect-src 'self'; object-src 'none'; base-uri 'none'; "
                         "frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not self.path.startswith("/") or self.path.startswith("//"):
                raise ValueError("Invalid request path")
            path = unquote(parsed.path, errors="strict")
            if path == "/api/state":
                self.reply(200, self.server.reader.snapshot())
                return
            if path.startswith("/api/"):
                self.reply(404, {"error": "Not found"})
                return
            relative = "index.html" if path == "/" else path[1:]
            parts(relative)
            data = self.server.assets.read(relative, limit=16 * 1024 * 1024)
            mime = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            self.reply(200, data, mime)
        except (OSError, ValueError):
            self.reply(404, {"error": "Asset not found"})

    def do_POST(self):
        try:
            if self.headers.get_all("Origin", []) != ["http://" + self.headers["Host"]]:
                raise FeedbackError(403, "Same Origin required")
            if self.path not in ("/api/feedback", "/api/project/name"):
                raise FeedbackError(404, "Not found")
            if self.headers.get_all("Transfer-Encoding"):
                raise FeedbackError(400, "Transfer-Encoding is not supported")
            types = self.headers.get_all("Content-Type", [])
            if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
                raise FeedbackError(415, "application/json required")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                raise FeedbackError(411, "A single Content-Length is required")
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY_BYTES:
                raise FeedbackError(413, "Feedback body exceeds limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise FeedbackError(400, "Incomplete body")
            body = strict_json(raw.decode("utf-8"))
            if self.path == "/api/project/name":
                self.reply(200, save_project_name(self.server.reader, body))
            else:
                record, created = save_feedback(self.server.reader, body)
                self.reply(201 if created else 200, record)
        except FeedbackError as exc:
            self.reply(exc.status, {"error": str(exc)})
        except (ValueError, RecursionError):
            self.reply(400, {"error": "Invalid JSON body"})
        except (OSError, TimeoutError):
            self.close_connection = True


def make_server(root: Path, assets: Path, port: int = 0) -> HTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.reader = Reader(root)
    server.assets = SafeTree(assets)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--assets", type=Path, default=Path(__file__).parent / "assets")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    args.project = args.project.absolute()
    if not args.project.is_dir() or args.project.is_symlink():
        parser.error("--project must be a non-symlink project directory")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    server = make_server(args.project, args.assets, args.port)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    tree = server.reader.tree
    runtime = f".workspace/runtime/server-{port}.json"
    published = False
    try:
        # Runtime is ephemeral; replace only our exact regular-file entry, never follow links.
        with tree.directory([".workspace", "runtime"], create=True) as directory:
            try:
                entry = os.stat(f"server-{port}.json", dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if not stat.S_ISREG(entry.st_mode):
                    raise ValueError("Unsafe runtime entry")
                os.unlink(f"server-{port}.json", dir_fd=directory)
        tree.publish(runtime, {"project": str(args.project), "pid": os.getpid(), "url": url}, internal=True)
        published = True
        print(url, flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if published:
            try:
                with tree.directory([".workspace", "runtime"]) as directory:
                    os.unlink(f"server-{port}.json", dir_fd=directory)
            except OSError:
                pass


if __name__ == "__main__":
    main()
