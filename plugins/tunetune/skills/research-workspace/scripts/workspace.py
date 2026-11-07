"""Local, file-backed research workspace. Writes only project-name metadata; no research execution."""
from __future__ import annotations

import argparse
import webbrowser
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import mimetypes
import os
import queue
import signal
import socketserver
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit, parse_qs
import unicodedata
import uuid

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILES = 2000
MAX_ENTRIES = 10000
MAX_BODY_BYTES = 128 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
# A closed allowlist: wildcard matches exactly one safe path component.
PATTERNS = (
    "project.json", "proposal.json", "plan.json", "resources.json",
    "evaluation/*/definition.json", "evaluation/*/samples.jsonl",
    "experiments/*/config.json", "experiments/*/status.json", "experiments/*/analysis.json",
    "experiments/*/evals/*/config.json", "experiments/*/evals/*/status.json",
    "experiments/*/evals/*/outputs.jsonl", "experiments/*/model/invoke.json",
    "comparison/inputs.jsonl", "comparison/outputs.jsonl", "responses/*.json",
)
VIEWS = ("proposal", "plan", "resources", "evaluation", "review", "acceptance")
ID = re.compile(r"[A-Za-z0-9_-]+\Z")

monitor_spec = importlib.util.spec_from_file_location("workspace_monitor", Path(__file__).with_name("monitor.py"))
monitor_module = importlib.util.module_from_spec(monitor_spec)
monitor_spec.loader.exec_module(monitor_module)


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
        if ".." in Path(root).parts:
            raise ValueError("Parent traversal is not allowed")
        self.root = Path(root).absolute()

    @contextmanager
    def directory(self, segments=(), create=False):
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for segment in self.root.parts[1:]:
                child = os.open(segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
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

    def publish(self, path, value, internal=False, replace=False):
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
                if replace:
                    try:
                        existing = os.stat(segments[-1], dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        if not stat.S_ISREG(existing.st_mode):
                            raise ValueError("Unsafe observation destination")
                    os.replace(temp, segments[-1], src_dir_fd=parent, dst_dir_fd=parent)
                else:
                    os.link(temp, segments[-1], src_dir_fd=parent, dst_dir_fd=parent,
                            follow_symlinks=False)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temp, dir_fd=parent)
                except FileNotFoundError:
                    pass


def find_helpers(root):
    """Research tools pinned in the project by initialization, never a newer skill elsewhere."""
    current = Path(root)
    try:
        for segment in (".workspace", "app"):
            current = current / segment
            if not stat.S_ISDIR(os.lstat(current).st_mode):
                raise OSError("Not a real directory")
        if all(stat.S_ISREG(os.lstat(current / name).st_mode) for name in ("records.py", "run.py")):
            return current
    except OSError:
        pass
    return None


def load_records(helpers):
    if helpers is None:
        return None
    spec = importlib.util.spec_from_file_location("workspace_records", helpers / "records.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def submit_response(reader, body):
    if reader.records is None:
        raise RequestError(503, "Research tools are not installed in this project")
    if not isinstance(body, dict) or not {"kind", "decision", "target_sha256"} <= set(body) <= {"kind", "decision", "target_sha256", "note", "items"}:
        raise RequestError(400, "Invalid response fields")
    note = body.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 4000):
        raise RequestError(400, "Invalid note")
    tree = reader.records.Tree(reader.tree.root)
    try:
        return reader.records.publish_response(tree, body["kind"], body["decision"], body["target_sha256"],
                                               note.strip() if note else None, body.get("items"))
    except ValueError as exc:
        raise RequestError(409 if "Conflict" in str(exc) or "busy" in str(exc).lower() else 400, str(exc)) from exc
    finally:
        tree.close()


def helper_command(reader, *args):
    return [sys.executable, "-E", "-s", str(reader.helpers / "run.py"), "--project", str(reader.tree.root), *args]


def write_runtime(tree, name, data):
    """Private scratch for the panel's own runs, never research evidence."""
    with tree.directory([".workspace", "runtime"], create=True) as parent:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    return ".workspace/runtime/" + name


def remove_runtime(tree, name):
    try:
        with tree.directory([".workspace", "runtime"]) as parent:
            os.unlink(name, dir_fd=parent)
    except OSError:
        pass


def physical_memory_gb():
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1e9
    except (ValueError, OSError, AttributeError):
        return None


class ModelPool:
    """Resident model processes the person loads from the panel, kept within a memory budget.

    A model with `serve` in its invoke.json can stay loaded, answering one JSONL request
    per stdin line after printing {"ready":true}. Nothing is evicted silently: when a
    load or run would exceed the budget, the person is told what to unload. Every
    process ends with the panel.
    """
    LOAD_TIMEOUT = 900
    ANSWER_TIMEOUT = 180

    def __init__(self, reader, budget_gb=None):
        self.reader = reader
        self.lock = threading.Lock()
        self.models = {}
        total = physical_memory_gb()
        self.budget_gb = budget_gb or (round(total / 2, 1) if total else 8.0)

    def entry(self, experiment, verify):
        if self.reader.records is None:
            raise RequestError(503, "Research tools are not installed in this project")
        tree = self.reader.records.Tree(self.reader.tree.root)
        try:
            return self.reader.records.model_entry(tree, experiment, verify=verify)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RequestError(400, str(exc)) from None
        finally:
            tree.close()

    def status(self):
        with self.lock:
            items = {ident: {key: item[key] for key in ("state", "memory_gb", "estimated", "error") if key in item}
                     for ident, item in self.models.items()}
            return {"budget_gb": self.budget_gb, "used_gb": round(self._used(), 2), "items": items}

    def _used(self, exclude=()):
        return sum(item["memory_gb"] for ident, item in self.models.items()
                   if item["state"] in ("loading", "loaded") and ident not in exclude)

    def check_room(self, need, experiment):
        """Caller holds the lock."""
        used = self._used(exclude=(experiment,))
        if used + need > self.budget_gb:
            names = "、".join(ident for ident, item in self.models.items() if item["state"] in ("loading", "loaded") and ident != experiment)
            raise RequestError(409, "Memory budget exceeded",
                               notice=f"内存预算 {self.budget_gb:g} GB 不够：这个模型约需 {need:g} GB，已加载的 {names or '无'} 占 {used:g} GB。先卸载一个再试。")

    def is_loaded(self, experiment):
        with self.lock:
            return self.models.get(experiment, {}).get("state") == "loaded"

    def load(self, experiment):
        if not isinstance(experiment, str) or not ID.fullmatch(experiment):
            raise RequestError(400, "Name one experiment")
        estimate = self.entry(experiment, verify=False)
        if not estimate["serve"]:
            raise RequestError(400, "This model has no serve command", notice="这个模型没有常驻运行方式，每次运行时加载。")
        with self.lock:
            current = self.models.get(experiment, {})
            if current.get("state") in ("loading", "loaded"):
                return {key: current[key] for key in ("state", "memory_gb", "estimated")}
            self.check_room(estimate["memory_gb"], experiment)
            item = {"state": "loading", "memory_gb": estimate["memory_gb"], "estimated": estimate["estimated"]}
            self.models[experiment] = item
        threading.Thread(target=self._start, args=(experiment, item), daemon=True).start()
        return {key: item[key] for key in ("state", "memory_gb", "estimated")}

    def _start(self, experiment, item):
        try:
            entry = self.entry(experiment, verify=True)
            name = f"serve-{experiment}.log"
            write_runtime(self.reader.tree, name, b"")
            with self.reader.tree.directory([".workspace", "runtime"]) as parent:
                log = os.fdopen(os.open(name, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, dir_fd=parent), "ab")
            with log:
                process = subprocess.Popen(entry["serve"], cwd=self.reader.tree.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=log, start_new_session=True, shell=False)
            answers, ready = queue.Queue(), threading.Event()

            def read():
                for line in process.stdout:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get("ready") is True:
                        ready.set()
                    elif isinstance(row, dict) and "sample_id" in row:
                        answers.put(row)
                answers.put(None)
                ready.set()
            threading.Thread(target=read, daemon=True).start()
            with self.lock:
                if self.models.get(experiment) is not item:
                    self._kill(process)
                    return
                item.update(process=process, answers=answers, ask_lock=threading.Lock())
            if not ready.wait(self.LOAD_TIMEOUT) or process.poll() is not None:
                raise RuntimeError(f"The model did not become ready; see .workspace/runtime/{name}")
            with self.lock:
                if self.models.get(experiment) is item:
                    item["state"] = "loaded"
        except (RequestError, OSError, RuntimeError, ValueError) as exc:
            with self.lock:
                if self.models.get(experiment) is item:
                    self._kill(item.pop("process", None))
                    item.update(state="failed", error=str(exc)[-500:])

    @staticmethod
    def _kill(process):
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if process is not None:
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def unload(self, experiment):
        with self.lock:
            item = self.models.pop(experiment, None)
            if item:
                self._kill(item.get("process"))
        return self.status()

    def ask(self, experiment, rows):
        """Send rows to a loaded model; a model that stops answering is unloaded."""
        with self.lock:
            item = self.models.get(experiment)
            if not item or item["state"] != "loaded":
                raise RequestError(409, "Model is not loaded")
        results = []
        with item["ask_lock"]:
            try:
                while not item["answers"].empty():
                    item["answers"].get_nowait()
                for row in rows:
                    item["process"].stdin.write((json.dumps({"sample_id": row["sample_id"], "input": row["input"]}, ensure_ascii=False) + "\n").encode())
                    item["process"].stdin.flush()
                    answer = item["answers"].get(timeout=self.ANSWER_TIMEOUT)
                    if answer is None or answer.get("sample_id") != row["sample_id"]:
                        raise RuntimeError("The loaded model stopped answering")
                    results.append({"sample_id": row["sample_id"], "input": row["input"], "output": answer.get("output")})
            except (OSError, RuntimeError, queue.Empty) as exc:
                with self.lock:
                    if self.models.get(experiment) is item:
                        self._kill(item.pop("process", None))
                        item.update(state="failed", error=str(exc) or "The loaded model did not answer in time")
                raise RequestError(504, "The loaded model did not answer") from None
        return results

    def close(self):
        with self.lock:
            for item in self.models.values():
                self._kill(item.get("process"))
            self.models.clear()


def check_cold_room(reader, experiments):
    """A model loaded for one run still has to fit beside the resident ones."""
    pool = reader.models
    for ident in experiments:
        try:
            need = pool.entry(ident, verify=False)["memory_gb"]
        except RequestError:
            continue
        with pool.lock:
            pool.check_room(need, ident)


def model_load(reader, body):
    if not isinstance(body, dict) or set(body) != {"experiment"}:
        raise RequestError(400, "Name one experiment")
    return reader.models.load(body["experiment"])


def model_unload(reader, body):
    if not isinstance(body, dict) or set(body) != {"experiment"} or not isinstance(body["experiment"], str):
        raise RequestError(400, "Name one experiment")
    return reader.models.unload(body["experiment"])


def start_acceptance(reader, body):
    """Run verified local models on the acceptance inputs; the runner merges their outputs.

    Loaded models answer through their resident process; the others load for this run only.
    """
    if reader.helpers is None:
        raise RequestError(503, "Research tools are not installed in this project")
    if not isinstance(body, dict) or set(body) != {"experiments"} or not isinstance(body["experiments"], list) \
            or not 0 < len(body["experiments"]) <= 8 or not all(isinstance(e, str) and ID.fullmatch(e) for e in body["experiments"]) \
            or len(set(body["experiments"])) != len(body["experiments"]):
        raise RequestError(400, "Name one to eight distinct experiments")
    if not reader.running.acquire(blocking=False):
        raise RequestError(409, "Another model run is in progress")
    try:
        check_cold_room(reader, [e for e in body["experiments"] if not reader.models.is_loaded(e)])
    except RequestError:
        reader.running.release()
        raise
    job = {"id": uuid.uuid4().hex[:8], "state": "running", "experiments": body["experiments"], "started_at": now()}
    reader.job = job

    def work():
        served = []
        try:
            arguments = []
            loaded = [e for e in body["experiments"] if reader.models.is_loaded(e)]
            if loaded:
                rows = [strict_json(line) for line in reader.tree.read("comparison/inputs.jsonl").decode("utf-8").splitlines() if line.strip()]
                for ident in loaded:
                    try:
                        answers = reader.models.ask(ident, rows)
                    except RequestError:
                        continue
                    name = f"served-{job['id']}-{ident}.jsonl"
                    write_runtime(reader.tree, name, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in answers).encode())
                    served.append(name)
                    arguments += ["--served", f"{ident}=.workspace/runtime/{name}"]
            result = subprocess.run(helper_command(reader, "--compare", *body["experiments"], "--timeout", "900", "--local-only", *arguments),
                                    capture_output=True, text=True, timeout=900 * len(body["experiments"]) + 60)
            report = {}
            try:
                report = json.loads(result.stdout or "{}").get("experiments", {})
            except ValueError:
                pass
            failed = [k for k, v in report.items() if v.get("returncode") != 0]
            job.update(state="succeeded" if result.returncode == 0 else "failed", finished_at=now(),
                       failed=failed, message=(result.stderr or "")[-1500:])
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            job.update(state="failed", finished_at=now(), message=str(exc)[-1500:])
        finally:
            for name in served:
                remove_runtime(reader.tree, name)
            reader.running.release()
    threading.Thread(target=work, daemon=True).start()
    return job


def try_model(reader, body):
    if reader.helpers is None:
        raise RequestError(503, "Research tools are not installed in this project")
    if not isinstance(body, dict) or set(body) != {"experiment", "input"} or not isinstance(body["experiment"], str) \
            or not ID.fullmatch(body["experiment"]):
        raise RequestError(400, "Name one experiment and an input")
    if reader.models.is_loaded(body["experiment"]):
        if len(json.dumps(body["input"], ensure_ascii=False).encode()) > 256 * 1024:
            raise RequestError(400, "Input is too large")
        started = time.monotonic()
        answer = reader.models.ask(body["experiment"], [{"sample_id": "try", "input": body["input"]}])[0]
        return {"experiment": body["experiment"], "output": answer["output"], "served": True, "elapsed_seconds": time.monotonic() - started}
    if not reader.running.acquire(blocking=False):
        raise RequestError(409, "Another model run is in progress")
    try:
        check_cold_room(reader, [body["experiment"]])
        result = subprocess.run(helper_command(reader, "--try", body["experiment"], "--timeout", "180"),
                                input=json.dumps(body["input"], ensure_ascii=False), capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        raise RequestError(504, "The model did not answer in time") from None
    finally:
        reader.running.release()
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {"error": json.loads(result.stderr or "{}").get("error", "Run failed")}
    except ValueError:
        return {"error": (result.stderr or "Run failed")[-1500:]}


def media_reference(snapshot, path):
    """Only explicit references in current display records expose project media."""
    if snapshot.get("error"):
        return False
    def contains(value, depth=0):
        if depth > 8:
            return False
        if isinstance(value, dict):
            if value.get("type") in ("image", "audio", "video", "file") and value.get("path") == path:
                return True
            return any(contains(child, depth + 1) for child in value.values())
        return isinstance(value, list) and any(contains(child, depth + 1) for child in value)
    visible = []
    for name, item in snapshot["files"].items():
        content = item["content"]
        if name == "proposal.json":
            for example in content.get("examples", []):
                if isinstance(example, dict):
                    visible.extend(example[key] for key in ("input", "expected_output") if key in example)
        elif name.startswith("comparison/") or name.endswith("/samples.jsonl") or name.endswith("/outputs.jsonl"):
            for row in content:
                visible.extend(row[key] for key in ("input", "reference", "output", "outputs") if key in row)
    return any(contains(value) for value in visible)


class Reader:
    def __init__(self, root: Path):
        self.tree = SafeTree(root)
        self.lock = threading.RLock()
        self._files = {}
        self._revision = hashlib.sha256(b"").hexdigest()
        self._synced_at = None
        self.monitor = monitor_module.ResourceMonitor(self.tree)
        self.job = None
        self.helpers = find_helpers(root)
        self.records = load_records(self.helpers)
        self.running = threading.Lock()
        self.models = ModelPool(self)

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
            raw = self.tree.read(path, limit=MAX_FILE_BYTES)
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Snapshot byte limit exceeded")
            try:
                if path.endswith(".json"):
                    content = strict_json(raw.decode("utf-8"))
                    if not isinstance(content, dict):
                        raise ValueError("JSON must be an object")
                    field = {"proposal.json": "examples", "resources.json": "items", "project.json": "deliveries"}.get(path)
                    if field in content and not isinstance(content[field], list):
                        raise ValueError(f"{field} must be an array")
                    if path == "resources.json":
                        for item in content.get("items", []):
                            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                                raise ValueError("Resource requires an ID")
                            if any(key in item and not isinstance(item[key], str) for key in ("title", "type", "status", "path", "location", "version", "size")):
                                raise ValueError("Invalid resource field")
                            if "monitor" in item and not isinstance(item["monitor"], dict):
                                raise ValueError("Invalid resource monitor")
                    if path.endswith("/status.json") and content.get("state") not in ("pending", "running", "completed", "succeeded", "failed", "cancelled"):
                        raise ValueError("Invalid execution state")
                elif path.endswith(".jsonl"):
                    content = [strict_json(line) for line in raw.decode("utf-8").splitlines()
                               if line.strip()]
                    if any(not isinstance(item, dict) for item in content):
                        raise ValueError("JSONL rows must be objects")
                else:
                    content = raw.decode("utf-8")
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"{path}: {exc}") from exc
            files[path] = {"content": content, "sha256": hashlib.sha256(raw).hexdigest()}
        if "project.json" not in files:
            raise ValueError("Missing required project.json")
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
            inventory = self._files.get("resources.json", {}).get("content", {"items": []})
            observations = self.monitor.snapshot(inventory) if not error else copy.deepcopy(self.monitor.report)
            return {"files": copy.deepcopy(self._files), "revision": self._revision,
                    "synced_at": self._synced_at or now(), "error": error, "observations": observations,
                    "view": self.view(), "acceptance": copy.deepcopy(self.job), "models": self.models.status()}

    def view(self):
        """Display focus published by the Agent; invalid or missing state is simply ignored."""
        try:
            with self.tree.directory([".workspace"]) as parent:
                fd = os.open("view.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        return None
                    raw = stream.read(64 * 1024 + 1)
            value = strict_json(raw.decode("utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        if not isinstance(value, dict) or type(value.get("revision")) is not int:
            return None
        focus = value.get("focus") if isinstance(value.get("focus"), dict) else {}
        experiment = focus.get("experiment")
        return {"revision": value["revision"],
                "open": [v for v in value.get("open", []) if v in VIEWS] if isinstance(value.get("open"), list) else [],
                "focus": {"experiment": experiment} if isinstance(experiment, str) and ID.fullmatch(experiment) else {},
                "attention": [{"view": n["view"], "message": n["message"][:200]} for n in value.get("attention", [])
                              if isinstance(n, dict) and n.get("view") in VIEWS and isinstance(n.get("message"), str)]
                if isinstance(value.get("attention"), list) else []}


class RequestError(Exception):
    def __init__(self, status, message, notice=None):
        self.status = status
        self.notice = notice  # Shown to the person as is.
        super().__init__(message)


def save_project_name(reader, body):
    if not isinstance(body, dict) or body.keys() != {"name", "expected_sha256"}:
        raise RequestError(400, "Invalid project name fields")
    if not isinstance(body["name"], str):
        raise RequestError(400, "Invalid project name")
    name = body["name"].strip()
    if not name or len(name) > 120 or any(
        unicodedata.category(char) in ("Cc", "Cs") for char in body["name"]
    ):
        raise RequestError(400, "Project name must be 1–120 characters without control characters")
    expected = body["expected_sha256"]
    if not isinstance(expected, str) or not HASH.fullmatch(expected):
        raise RequestError(400, "Invalid expected_sha256")

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
                if not isinstance(project, dict):
                    raise ValueError("project.json must be an object")
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise RequestError(409, "Project is stale; refresh before renaming")
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
                        raise RequestError(409, "project.json changed before renaming")
                    os.replace(temp, "project.json", src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                finally:
                    try:
                        os.unlink(temp, dir_fd=parent)
                    except FileNotFoundError:
                        pass
                return {"name": name, "sha256": hashlib.sha256(raw).hexdigest()}
        except (OSError, ValueError, RecursionError) as exc:
            raise RequestError(409, f"Cannot safely save project name: {exc}") from exc


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
                         "connect-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; "
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
            if path == "/api/media":
                query = parse_qs(parsed.query, strict_parsing=True)
                if set(query) != {"path"} or len(query["path"]) != 1:
                    raise ValueError("Expected one media path")
                relative = query["path"][0]
                parts(relative)
                suffix = Path(relative).suffix.lower()
                allowed = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
                           ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".flac": "audio/flac",
                           ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
                           ".glb": "application/octet-stream", ".gltf": "application/octet-stream", ".obj": "application/octet-stream",
                           ".stl": "application/octet-stream", ".ply": "application/octet-stream"}
                if suffix not in allowed or not media_reference(self.server.reader.snapshot(), relative):
                    raise ValueError("Media is not shared in research records")
                data = self.server.reader.tree.read(relative, limit=64 * 1024 * 1024)
                self.reply(200, data, allowed[suffix])
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
                raise RequestError(403, "Same Origin required")
            routes = {"/api/project/name": save_project_name, "/api/responses": submit_response,
                      "/api/acceptance/run": start_acceptance, "/api/try": try_model,
                      "/api/models/load": model_load, "/api/models/unload": model_unload}
            if self.path not in routes:
                raise RequestError(404, "Not found")
            if self.headers.get_all("Transfer-Encoding"):
                raise RequestError(400, "Transfer-Encoding is not supported")
            types = self.headers.get_all("Content-Type", [])
            if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
                raise RequestError(415, "application/json required")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                raise RequestError(411, "A single Content-Length is required")
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY_BYTES:
                raise RequestError(413, "Request body exceeds limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise RequestError(400, "Incomplete body")
            body = strict_json(raw.decode("utf-8"))
            self.reply(200, routes[self.path](self.server.reader, body))
        except RequestError as exc:
            self.reply(exc.status, {"error": str(exc), **({"notice": exc.notice} if exc.notice else {})})
        except (ValueError, RecursionError):
            self.reply(400, {"error": "Invalid JSON body"})
        except (OSError, TimeoutError):
            self.close_connection = True


class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer would resolve 127.0.0.1 through reverse DNS, which can stall startup for many seconds.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def make_server(root: Path, assets: Path, port: int = 0) -> HTTPServer:
    server = LoopbackServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.reader = Reader(root)
    server.assets = SafeTree(assets)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--assets", type=Path, default=Path(__file__).parent / "assets")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true", help="Open the local panel in the default browser")
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
        # Resident models run in their own sessions, so end them on termination as well as Ctrl-C.
        signal.signal(signal.SIGTERM, lambda signum, frame: (_ for _ in ()).throw(KeyboardInterrupt()))
        if args.open:
            threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.reader.models.close()
        server.server_close()
        if published:
            try:
                with tree.directory([".workspace", "runtime"]) as directory:
                    os.unlink(f"server-{port}.json", dir_fd=directory)
            except OSError:
                pass


if __name__ == "__main__":
    main()
