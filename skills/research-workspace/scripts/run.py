#!/usr/bin/env python3
"""Execute one prepared format-3 config; never infer scientific success."""
import argparse
from datetime import datetime, timezone
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

from records import ATTEMPT, PROCESS, Tree, digest, encoded, parts, read_record, require, shape, verify_inputs


# Use fchdir in a fresh interpreter, not preexec_fn or a path that can be
# redirected between validation and spawn. -I isolates the supervisor itself.
# Keep this group leader alive after payload completion so its identity remains
# reserved until the parent kills the entire group and only then reaps it.
LAUNCHER = """
import json, os, signal, subprocess, sys
fd, result_fd = int(sys.argv[1]), int(sys.argv[3])
try:
    os.fchdir(fd)
    os.close(fd)
    signal.pthread_sigmask(signal.SIG_SETMASK, json.loads(sys.argv[2]))
    payload = subprocess.Popen(sys.argv[4:], close_fds=True, shell=False)
    result = {"returncode": payload.wait()}
except OSError as exc:
    result = {"returncode": None, "error": str(exc)}
with os.fdopen(result_fd, "w") as channel:
    json.dump(result, channel)
while True:
    signal.pause()
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def publish_status(tree, path, state, **details):
    target = path + "/status.json"
    status = dict(state=state, updated_at=now(), **details)
    data = encoded(status)
    shape(target, data)
    tree.publish(target, data, replace=tree.exists(target))
    return status


def kill_owned_group(process):
    # Only the Popen child from this invocation, never a PID read from a record.
    # Do not poll/reap first: retaining the leader prevents PID reuse before killpg.
    if process is not None and process.returncode is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def wait_result(fd, deadline):
    """Read only the supervisor's private pipe; never wait/poll its Popen handle."""
    chunks = []
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while True:
            remaining = max(0, deadline - time.monotonic())
            if not selector.select(remaining):
                raise subprocess.TimeoutExpired("payload", remaining)
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    if not chunks:
        raise OSError("Supervisor exited without a payload result")
    return json.loads(b"".join(chunks))


def execute(tree, path):
    """Run an experiment or its nested evaluation once; return the saved status."""
    require(isinstance(path, str) and re.fullmatch(ATTEMPT, path), "Invalid run path")
    with tree.locked():
        read_record(tree, "project.json")
        config_path = path + "/config.json"
        raw = tree.read(config_path)
        config = shape(config_path, raw)
        execution = config["execution"]
        timeout = execution["timeout_seconds"]
        for name in ("run.log", "outputs.jsonl"):
            require(not tree.exists(path + "/" + name), f"Attempt already has {name}; use a new ID")
        if "/evals/" not in path and tree.exists(path + "/model"):
            require(not tree.files(path + "/model"), "Attempt already has model files; use a new ID")
        if tree.exists(path + "/status.json"):
            status = read_record(tree, path + "/status.json")
            require(status["state"] == "pending" and not any(k in status for k in (*PROCESS, "target", "metrics", "usage")),
                    "Attempt already started or completed; use a new ID")
        verify_inputs(tree, path, config)
        cwd = [] if execution["cwd"] == "." else parts(execution["cwd"])
        with tree.directory(cwd) as cwd_fd, tree.directory(parts(path)) as record_fd:
            fd = os.open("run.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=record_fd)
            with os.fdopen(fd, "wb") as log:
                require(stat.S_ISREG(os.fstat(log.fileno()).st_mode), "Log must be a regular file")
                # The exclusive log is a permanent reservation, even empty after
                # a crash. Never delete it or reset a status to reuse an ID.
                os.fsync(log.fileno())
                os.fsync(record_fd)
                started_at, started = now(), time.monotonic()
                mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
                publish_status(tree, path, "running", started_at=started_at, config_sha256=digest(raw))
                process, timed_out, error, interrupted = None, False, None, None
                read_fd, write_fd, result = None, None, None
                try:
                    try:
                        # Defer termination until we own the Popen handle. Otherwise
                        # a signal during spawn can orphan a child before assignment.
                        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
                        try:
                            read_fd, write_fd = os.pipe()
                            process = subprocess.Popen(
                                [sys.executable, "-I", "-c", LAUNCHER, str(cwd_fd), json.dumps(sorted(mask)),
                                 str(write_fd), *execution["argv"]],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, **execution["environment"]}, pass_fds=(cwd_fd, write_fd),
                                start_new_session=True, shell=False,
                            )
                        finally:
                            if write_fd is not None:
                                os.close(write_fd)
                            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                        result = wait_result(read_fd, started + timeout)
                        error = result.get("error")
                    finally:
                        # Enter the cleanup mask inside the exception boundary: a
                        # first signal just before blocking must also be caught.
                        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
                except subprocess.TimeoutExpired:
                    timed_out, error = True, "Execution timeout"
                except OSError as exc:
                    error = str(exc)
                except BaseException as exc:
                    error, interrupted = f"Interrupted: {type(exc).__name__}", exc
                finally:
                    # Re-block if the first CLI signal interrupted mask entry.
                    # Its handler ignores repeats. Masks are thread-local: library
                    # callers must coordinate other threads and signal handlers.
                    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
                    try:
                        kill_owned_group(process)
                        if read_fd is not None:
                            os.close(read_fd)
                        facts = dict(
                            returncode=result["returncode"] if result is not None else (process.returncode if process else None),
                            started_at=started_at, completed_at=now(), elapsed_seconds=time.monotonic() - started,
                            timed_out=timed_out, config_sha256=digest(raw),
                        )
                        if error:
                            facts["error"] = error
                        log.flush()
                        os.fsync(log.fileno())
                        state = "failed" if error or facts["returncode"] != 0 else "completed"
                        status = publish_status(tree, path, state, **facts)
                    finally:
                        # A pending late signal may raise here, but the owned group
                        # is gone and the payload's actual process facts are saved.
                        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                if interrupted is not None:
                    raise interrupted
                return status


class InterruptedRun(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--path", required=True, help="experiments/<id> or experiments/<id>/evals/<run-id>")
    args = parser.parse_args()
    tree = None
    previous = {}

    def interrupt(signum, frame):
        # Ignore repeated termination while recording the first interruption.
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)
        raise InterruptedRun(f"Signal {signum}")

    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, interrupt)
        tree = Tree(args.project)
        status = execute(tree, args.path)
        print(json.dumps(status, ensure_ascii=False))
        return 0 if status["state"] == "completed" else 1
    except (OSError, ValueError, TypeError, KeyError, InterruptedRun) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if tree:
            tree.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())
