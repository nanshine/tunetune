#!/usr/bin/env python3
"""Execute one prepared format-4 config; never infer scientific success."""
import argparse
from datetime import datetime, timezone
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

from records import (ATTEMPT, ID, PROCESS, Tree, check_invoke, check_record, digest, encoded, parts, read_record, require,
                     shape, split_samples, strict, verify_inputs, verify_model, verify_path_hash, verify_requires)


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
        for name in ("run.log", "outputs.jsonl", "result", "samples.jsonl"):
            require(not tree.exists(path + "/" + name), f"Attempt already has {name}; use a new ID")
        if "/evals/" not in path and tree.exists(path + "/model"):
            require(not tree.files(path + "/model"), "Attempt already has model files; use a new ID")
        if tree.exists(path + "/status.json"):
            status = read_record(tree, path + "/status.json")
            require(status["state"] == "pending" and not any(k in status for k in (*PROCESS, "target", "metrics", "usage")),
                    "Attempt already started or completed; use a new ID")
        verify_inputs(tree, path, config)
        # Conventional locations override same-named config values; see finalize in records.py.
        locations = {"TUNETUNE_PROJECT": tree.root, "TUNETUNE_ATTEMPT": os.path.join(tree.root, path)}
        if "/evals/" in path:
            experiment = path.split("/evals/")[0]
            target = read_record(tree, experiment + "/status.json")["target"]["path"]
            split = config.get("split", "development")
            samples = split_samples(tree, config["evaluation_version"], split)
            require(samples, f"Evaluation {config['evaluation_version']} has no {split} samples")
            if split == "final":
                # One final measurement per model and evaluation; repeated looks turn the final check into development.
                with tree.directory(parts(experiment + "/evals")) as runs:
                    others = sorted(os.listdir(runs))
                for other in others:
                    other_path = f"{experiment}/evals/{other}"
                    if other_path == path or not tree.exists(other_path + "/status.json"):
                        continue
                    other_config = read_record(tree, other_path + "/config.json")
                    require(not (other_config.get("split") == "final" and other_config["evaluation_version"] == config["evaluation_version"]
                                 and other_config["target_sha256"] == config["target_sha256"]
                                 and read_record(tree, other_path + "/status.json")["state"] == "succeeded"),
                            f"This model already has a final-check measurement: {other_path}")
            # The scorer reads only this run's split, so development runs never see final-check samples.
            tree.publish(path + "/samples.jsonl", b"".join(json.dumps(row, ensure_ascii=False, allow_nan=False).encode() + b"\n" for row in samples))
            locations.update(TUNETUNE_TARGET=os.path.join(tree.root, target),
                             TUNETUNE_EVALUATION=os.path.join(tree.root, "evaluation", config["evaluation_version"]),
                             TUNETUNE_SAMPLES=os.path.join(tree.root, path, "samples.jsonl"),
                             TUNETUNE_OUTPUT=os.path.join(tree.root, path, "result"))
            output = path + "/result"
        else:
            locations["TUNETUNE_OUTPUT"] = os.path.join(tree.root, path, "model")
            output = path + "/model"
        with tree.directory(parts(output), create=True):
            pass
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
                                env={**os.environ, **execution["environment"], **locations}, pass_fds=(cwd_fd, write_fd),
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


def run_entry(tree, argv, source, output, log_path, timeout):
    """Run one model entry point in its own process group from the project root."""
    started = time.monotonic()
    with open(log_path, "wb") as log:
        process = subprocess.Popen([*argv, source, output], cwd=tree.root, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True, shell=False)
        try:
            returncode, timed_out = process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            returncode, timed_out = None, True
        finally:
            kill_owned_group(process)
    return returncode, timed_out, time.monotonic() - started


def try_model(tree, experiment, value, timeout):
    """Run one verified local model on one input for the person; nothing is recorded as evidence."""
    require(isinstance(experiment, str) and re.fullmatch(ID, experiment), "Invalid experiment ID")
    require(isinstance(timeout, (int, float)) and 0 < timeout < float("inf"), "Invalid timeout")
    data = encoded({"sample_id": "try", "input": value}).replace(b"\n", b"")
    require(len(data) <= 256 * 1024, "Input is too large")
    with tree.locked():
        read_record(tree, "project.json")
        target = verify_model(tree, "experiments/" + experiment)["target"]
        require(target["kind"] == "local", "Only local models can be tried from the panel")
        require(check_invoke(tree, target["path"]), f"Experiment {experiment} has no invoke.json entry point")
        argv = strict(tree.read(target["path"] + "/invoke.json"))["argv"]
    with tree.directory([".workspace", "runtime"], create=True):
        pass
    scratch = tempfile.mkdtemp(prefix="try-", dir=os.path.join(tree.root, ".workspace", "runtime"))
    try:
        source, output, log_path = (os.path.join(scratch, name) for name in ("input.jsonl", "output.jsonl", "run.log"))
        with open(source, "wb") as stream:
            stream.write(data + b"\n")
        returncode, timed_out, elapsed = run_entry(tree, argv, source, output, log_path, timeout)
        verify_path_hash(tree, target["path"], target["sha256"])
        verify_requires(tree, target["path"])
        result = {"experiment": experiment, "returncode": returncode, "timed_out": timed_out, "elapsed_seconds": elapsed}
        if returncode == 0 and os.path.exists(output):
            with open(output, "rb") as stream:
                rows = [strict(line) for line in stream.read().decode("utf-8").splitlines() if line.strip()]
            found = [row for row in rows if isinstance(row, dict) and row.get("sample_id") == "try"]
            if found and "output" in found[0]:
                result["output"] = found[0]["output"]
        if "output" not in result:
            with open(log_path, "rb") as stream:
                result["log_tail"] = stream.read()[-4000:].decode("utf-8", "replace")
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def compare(tree, experiments, timeout, local_only=False, served=None):
    """Run verified models' invoke.json entries on comparison/inputs.jsonl and merge comparison/outputs.jsonl.

    This is a same-input acceptance view, not a measurement: nothing is scored and
    failed or missing outputs stay missing. Models run without the writer lock.
    `served` maps an experiment to rows {sample_id,input,output} its resident process
    already answered under .workspace/runtime/; rows whose input has since changed are dropped.
    """
    served = served or {}
    require(set(served) <= set(experiments) and all(re.fullmatch(r"\.workspace/runtime/[A-Za-z0-9_.-]+\.jsonl", p) for p in served.values()),
            "Served outputs must name compared experiments and runtime files")
    require(experiments and len(set(experiments)) == len(experiments)
            and all(isinstance(e, str) and re.fullmatch(ID, e) for e in experiments), "Name distinct experiment IDs")
    require(isinstance(timeout, (int, float)) and 0 < timeout < float("inf"), "Invalid timeout")
    with tree.locked():
        read_record(tree, "project.json")
        raw_inputs = tree.read("comparison/inputs.jsonl")
        inputs = shape("comparison/inputs.jsonl", raw_inputs)
        require(inputs, "comparison/inputs.jsonl is empty")
        entries = {}
        for ident in experiments:
            target = verify_model(tree, "experiments/" + ident)["target"]
            require(check_invoke(tree, target["path"]), f"Experiment {ident} has no invoke.json entry point")
            require(not local_only or target["kind"] == "local", f"Experiment {ident} is not a local model")
            entries[ident] = (target, strict(tree.read(target["path"] + "/invoke.json"))["argv"])
        previous = tree.read("comparison/outputs.jsonl") if tree.exists("comparison/outputs.jsonl") else None
    with tree.directory([".workspace", "runtime"], create=True):
        pass
    report, produced = {}, {}
    scratch = tempfile.mkdtemp(prefix="compare-", dir=os.path.join(tree.root, ".workspace", "runtime"))
    try:
        source = os.path.join(scratch, "inputs.jsonl")
        with open(source, "wb") as stream:
            stream.write(raw_inputs)
        known = {row["sample_id"]: row["input"] for row in inputs}
        for ident, (target, argv) in entries.items():
            output, log_path = os.path.join(scratch, ident + ".jsonl"), os.path.join(scratch, ident + ".log")
            if ident in served:
                answered = [strict(line) for line in tree.read(served[ident]).decode("utf-8").splitlines() if line.strip()]
                with open(output, "wb") as stream:
                    stream.write(b"".join((json.dumps({"sample_id": row["sample_id"], "output": row.get("output")}, ensure_ascii=False) + "\n").encode() for row in answered
                                          if isinstance(row, dict) and row.get("sample_id") in known and row.get("input") == known[row["sample_id"]]))
                with open(log_path, "wb") as stream:
                    stream.write(b"Answered by the panel's loaded process.\n")
                returncode, timed_out, elapsed = 0, False, 0.0
            else:
                returncode, timed_out, elapsed = run_entry(tree, argv, source, output, log_path, timeout)
            with open(log_path, "rb") as stream:
                tree.publish(f"comparison/logs/{ident}.log", stream.read(), replace=tree.exists(f"comparison/logs/{ident}.log"))
            verify_path_hash(tree, target["path"], target["sha256"])
            verify_requires(tree, target["path"])
            rows = {}
            if returncode == 0 and os.path.exists(output):
                with open(output, "rb") as stream:
                    for line in stream.read().decode("utf-8").splitlines():
                        if line.strip():
                            row = strict(line)
                            require(isinstance(row, dict) and row.get("sample_id") in known, f"{ident}: unknown output sample_id")
                            if row.get("output") is not None:
                                rows[row["sample_id"]] = row["output"]
                produced[ident] = rows
            report[ident] = dict(returncode=returncode, timed_out=timed_out, elapsed_seconds=elapsed,
                                 outputs=len(rows), log=f"comparison/logs/{ident}.log")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    with tree.locked():
        current = tree.read("comparison/outputs.jsonl") if tree.exists("comparison/outputs.jsonl") else None
        require(current == previous, "Conflict: comparison/outputs.jsonl changed during the run")
        old = {row["sample_id"]: row for row in shape("comparison/outputs.jsonl", previous)} if previous else {}
        merged = []
        for row in inputs:
            kept = old.get(row["sample_id"], {})
            outputs = {k: v for k, v in kept.get("outputs", {}).items() if k not in produced} if kept.get("input") == row["input"] else {}
            outputs.update({ident: values[row["sample_id"]] for ident, values in produced.items() if row["sample_id"] in values})
            merged.append({"sample_id": row["sample_id"], "input": row["input"], "outputs": outputs})
        data = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in merged).encode("utf-8")
        check_record(tree, "comparison/outputs.jsonl", shape("comparison/outputs.jsonl", data))
        tree.publish("comparison/outputs.jsonl", data, replace=previous is not None)
    return {"path": "comparison/outputs.jsonl", "experiments": report}


class InterruptedRun(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--path", help="experiments/<id> or experiments/<id>/evals/<run-id>")
    target.add_argument("--compare", nargs="+", metavar="EXPERIMENT", help="run invoke.json entries on comparison/inputs.jsonl")
    target.add_argument("--try", dest="try_experiment", metavar="EXPERIMENT", help="run one local model on one JSON input read from stdin")
    parser.add_argument("--timeout", type=float, default=600, help="per-model timeout for --compare and --try")
    parser.add_argument("--local-only", action="store_true", help="refuse API models in --compare")
    parser.add_argument("--served", action="append", default=[], metavar="EXPERIMENT=PATH",
                        help="use outputs a loaded model already produced for --compare")
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
        if args.try_experiment:
            result = try_model(tree, args.try_experiment, strict(sys.stdin.buffer.read(256 * 1024 + 1)), args.timeout)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if "output" in result else 1
        if args.compare:
            served = dict(item.split("=", 1) for item in args.served if "=" in item)
            require(len(served) == len(args.served), "Use --served EXPERIMENT=PATH")
            result = compare(tree, args.compare, args.timeout, args.local_only, served)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if all(item["returncode"] == 0 for item in result["experiments"].values()) else 1
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
