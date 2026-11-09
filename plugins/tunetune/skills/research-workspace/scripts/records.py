#!/usr/bin/env python3
"""Validate and publish research files without executing commands."""
import sys

# These tools rely on POSIX descriptor-relative opens, locks and process groups to protect
# research files; native Windows has none of them, so refuse clearly instead of failing on import.
if sys.platform == "win32":
    sys.exit("TuneTune tools need macOS or Linux. On Windows, run them inside WSL2 with the study "
             "in the Linux home directory, not under /mnt; INSTALL.md describes the setup.")
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

ID = r"[A-Za-z0-9_-]+"
SHA = re.compile(r"[a-f0-9]{64}\Z")
FINAL = ("succeeded", "failed", "cancelled")
VERSION = "0.8.7"
VIEWS = ("proposal", "plan", "resources", "evaluation", "review", "acceptance")
RESPONSE_TARGETS = {"proposal": "proposal.json", "plan": "plan.json", "evaluation_review": "evaluation/draft/samples.jsonl",
                    "acceptance": "comparison/outputs.jsonl"}
SPLITS = ("development", "final")
ATTEMPT = rf"experiments/{ID}(?:/evals/{ID})?"
RECORD = re.compile(
    rf"(?:project|proposal|resources|plan)\.json|comparison/(?:inputs|outputs)\.jsonl|responses/{ID}\.json|"
    rf"evaluation/{ID}/(?:definition\.json|samples\.jsonl)|"
    rf"{ATTEMPT}/(?:config|status)\.json|experiments/{ID}/analysis\.json|"
    rf"experiments/{ID}/evals/{ID}/outputs\.jsonl")
PROCESS = ("started_at", "completed_at", "elapsed_seconds", "returncode", "timed_out", "error", "config_sha256")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parts(path):
    require(isinstance(path, str) and path and not any(c in path for c in "\\:\x00"), "Unsafe path")
    value = path.split("/")
    require(all(p not in ("", ".", "..") for p in value), "Expected project-relative path")
    return value


def strict(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate key: {key}")
            result[key] = value
        return result
    def number(value):
        parsed = float(value)
        require(math.isfinite(parsed), "Non-finite number")
        return parsed
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data, object_pairs_hook=pairs, parse_float=number,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid number: {value}")))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    require("T" in value and datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None,
            "Timestamp requires timezone-bearing ISO 8601")


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def fields(obj, required, optional=()):
    require(isinstance(obj, dict), "Expected an object")
    require(all(k in obj for k in required), f"Missing required fields: {', '.join(required)}")
    require(set(obj) <= set(required) | set(optional), "Unknown fields: " + ", ".join(sorted(set(obj) - set(required) - set(optional))))


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(ID, value), "Invalid ID")


def hash_value(value):
    require(isinstance(value, str) and SHA.fullmatch(value), "Invalid SHA-256")


def argument_array(value):
    require(isinstance(value, list) and value and all(isinstance(v, str) and "\x00" not in v for v in value)
            and value[0], "Expected nonempty argument array")


def numbers(value):
    require(isinstance(value, dict) and all(finite_number(v) for v in value.values()), "Metrics/scores must be finite numbers")
    for key in value:
        identifier(key)


class Tree:
    def __init__(self, root):
        require(".." not in os.fspath(root).split("/"), "Parent traversal is not allowed")
        absolute = os.path.abspath(root)
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for segment in parts(absolute.lstrip("/")):
                child = os.open(segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        self.root = absolute

    def close(self):
        os.close(self.fd)

    @contextmanager
    def directory(self, segments, create=False):
        fd = os.dup(self.fd)
        try:
            for segment in segments:
                require(parts(segment) == [segment], "Unsafe directory segment")
                if create:
                    try:
                        os.mkdir(segment, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    def read(self, path, with_mode=False):
        segments = parts(path)
        with self.directory(segments[:-1]) as parent:
            fd = os.open(segments[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                require(stat.S_ISREG(os.fstat(fd).st_mode), f"Not a regular file: {path}")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    data = stream.read()
                return (data, 0o600 | (os.fstat(fd).st_mode & 0o111)) if with_mode else data
            finally:
                os.close(fd)

    def exists(self, path):
        try:
            with self.directory(parts(path)[:-1]) as parent:
                os.stat(parts(path)[-1], dir_fd=parent, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def files(self, prefix):
        found = []
        def walk(fd, base):
            for name in sorted(os.listdir(fd)):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                path = f"{base}/{name}" if base else name
                parts(path)
                if stat.S_ISDIR(info.st_mode):
                    with self.directory(parts(path)) as child:
                        walk(child, path)
                else:
                    require(stat.S_ISREG(info.st_mode), f"Not a regular file: {path}")
                    found.append(path)
        with self.directory(parts(prefix) if prefix else []) as fd:
            walk(fd, prefix)
        return found

    @contextmanager
    def locked(self):
        # Reject incompatible installations before even creating lock directories.
        check_installed_metadata(self)
        with self.directory([".workspace", "runtime"], create=True) as parent:
            fd = os.open("records.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
            try:
                require(stat.S_ISREG(os.fstat(fd).st_mode), "Not a regular lock file")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                yield
            finally:
                os.close(fd)

    def publish(self, path, data, replace=False, mode=0o600):
        segments = parts(path)
        with self.directory(segments[:-1], create=True) as parent:
            if replace:
                info = os.stat(segments[-1], dir_fd=parent, follow_symlinks=False)
                require(stat.S_ISREG(info.st_mode), f"Not a regular file: {path}")
            temporary = ".records-" + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    os.fchmod(stream.fileno(), mode)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if replace:
                    os.replace(temporary, segments[-1], src_dir_fd=parent, dst_dir_fd=parent)
                else:
                    os.link(temporary, segments[-1], src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass


def shape(path, data):
    parts(path)
    require(bool(RECORD.fullmatch(path)), "Path is not a research record")
    if path.endswith(".jsonl"):
        rows = [strict(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        ids = []
        for row in rows:
            require(isinstance(row, dict), "JSONL row must be an object")
            plain = path.startswith("evaluation/") or path == "comparison/inputs.jsonl"
            required = ("sample_id", "input") if plain else (
                "sample_id", "input", "outputs" if path.startswith("comparison/") else "output")
            require(all(k in row for k in required), "Missing sample/output fields")
            require(isinstance(row["sample_id"], str) and row["sample_id"].strip(), "sample_id must be nonempty")
            if path == "comparison/outputs.jsonl":
                fields(row, required)
                require(isinstance(row["outputs"], dict), "Comparison outputs must be an object")
                for experiment, output in row["outputs"].items():
                    identifier(experiment)
                    require(output is not None, "Comparison output must be present")
            elif plain:
                require(row.get("reference_status", "draft") in ("confirmed", "corrected", "draft"), "Invalid reference_status")
                require(path == "comparison/inputs.jsonl" or row.get("split", "development") in SPLITS,
                        "split must be development or final")
            else:
                fields(row, required, ("reference", "scores"))
                if "scores" in row:
                    numbers(row["scores"])
            ids.append(row["sample_id"])
        require(len(ids) == len(set(ids)), "Duplicate sample_id")
        return rows
    obj = strict(data)
    require(isinstance(obj, dict), "JSON must be an object")
    leaf = path.split("/")[-1]
    evaluation_run = "/evals/" in path
    if path == "project.json":
        fields(obj, ("name", "language", "current_evaluation", "deliveries"))
        if obj["current_evaluation"] is not None:
            identifier(obj["current_evaluation"])
            require(obj["current_evaluation"] != "draft", "Current evaluation must be frozen")
        require(isinstance(obj["deliveries"], list), "deliveries must be an array")
        for item in obj["deliveries"]:
            identifier(item)
        require(len(obj["deliveries"]) == len(set(obj["deliveries"])), "Duplicate delivery")
    elif path == "proposal.json":
        texts = ("goal", "output", "evaluation", "budget", "stopping", "delivery")
        fields(obj, ("summary", "examples"), (*texts, "considered", "approaches", "sources", "assumptions", "feasibility"))
        require(isinstance(obj["summary"], str) and all(isinstance(obj[k], str) for k in texts if k in obj), "Invalid proposal text")
        require(isinstance(obj["examples"], list), "examples must be an array")
        require(isinstance(obj.get("considered", []), list) and isinstance(obj.get("sources", []), list), "considered/sources must be arrays")
        for item in obj.get("considered", []):
            fields(item, ("family", "decision", "reason"))
            require(item["decision"] in ("adopted", "excluded") and isinstance(item["family"], str) and isinstance(item["reason"], str), "Invalid considered family")
        for item in obj.get("sources", []):
            fields(item, ("title", "url"))
            require(isinstance(item["title"], str) and isinstance(item["url"], str) and re.fullmatch(r"https?://[^\s]+", item["url"]), "Invalid source")
        require(isinstance(obj.get("assumptions", []), list) and all(isinstance(x, str) for x in obj.get("assumptions", [])), "assumptions must be strings")
        ids = []
        for example in obj["examples"]:
            fields(example, ("id", "input"), ("expected_output",))
            identifier(example["id"])
            ids.append(example["id"])
        require(len(ids) == len(set(ids)), "Duplicate example ID")
        if "approaches" in obj:
            require(isinstance(obj["approaches"], list), "approaches must be an array")
            approach_ids = []
            for approach in obj["approaches"]:
                fields(approach, ("id", "title", "roles", "rationale"), ("limitations", "resource_ids"))
                identifier(approach["id"])
                approach_ids.append(approach["id"])
                require(all(isinstance(approach[k], str) for k in ("title", "rationale", "limitations") if k in approach), "Invalid approach text")
                require(isinstance(approach["roles"], list) and approach["roles"] and len(set(approach["roles"])) == len(approach["roles"])
                        and all(role in ("baseline", "recommended", "reference", "challenge") for role in approach["roles"]), "Invalid approach roles")
                require(isinstance(approach.get("resource_ids", []), list), "resource_ids must be an array")
                for resource in approach.get("resource_ids", []):
                    identifier(resource)
            require(len(set(approach_ids)) == len(approach_ids), "Duplicate approach ID")
        if "feasibility" in obj:
            fields(obj["feasibility"], ("verdict", "reason"))
            require(obj["feasibility"]["verdict"] in ("feasible", "conditional", "infeasible", "unknown")
                    and isinstance(obj["feasibility"]["reason"], str), "Invalid feasibility")
    elif path.startswith("responses/"):
        fields(obj, ("id", "kind", "target", "created_at", "decision"), ("note", "items"))
        require(obj["id"] == path[len("responses/"):-len(".json")], "Response ID must match its file name")
        require(obj["kind"] in RESPONSE_TARGETS, "Invalid response kind")
        fields(obj["target"], ("path", "sha256"))
        require(obj["target"]["path"] == RESPONSE_TARGETS[obj["kind"]] and isinstance(obj["target"]["sha256"], str)
                and SHA.fullmatch(obj["target"]["sha256"]), "Invalid response target")
        timestamp(obj["created_at"])
        require(obj["decision"] in ("approve", "revise", "continue", "stop", "submit"), "Invalid response decision")
        require(isinstance(obj.get("note", ""), str) and len(obj.get("note", "")) <= 4000, "Invalid response note")
        require(isinstance(obj.get("items", []), list) and len(obj.get("items", [])) <= 2000, "items must be an array")
        for item in obj.get("items", []):
            if obj["kind"] == "acceptance":
                # The person's judgment of one model's output on one acceptance input.
                fields(item, ("sample_id", "experiment_id", "verdict"), ("note",))
                identifier(item["experiment_id"])
                require(item["verdict"] in ("good", "bad"), "Invalid acceptance verdict")
            else:
                fields(item, ("sample_id", "verdict"), ("reference", "note"))
                require(item["verdict"] in ("confirm", "correct", "question"), "Invalid response verdict")
                require(item["verdict"] != "correct" or "reference" in item, "A correction needs its reference")
            require(isinstance(item["sample_id"], str) and item["sample_id"], "Invalid response sample")
            require(isinstance(item.get("note", ""), str), "Invalid response item note")
    elif path == "plan.json":
        fields(obj, ("rounds",), ("ideas",))
        require(isinstance(obj["rounds"], list), "rounds must be an array")
        item_ids = []
        for number, round_ in enumerate(obj["rounds"], 1):
            fields(round_, ("round", "goal", "budget", "items"), ("conclusion",))
            require(round_["round"] == number and type(round_["round"]) is int, "Rounds must be numbered 1, 2, 3 in order")
            require(all(isinstance(round_[k], str) for k in ("goal", "budget", "conclusion") if k in round_), "Invalid round text")
            require(isinstance(round_["items"], list), "items must be an array")
            for item in round_["items"]:
                fields(item, ("id", "title", "question", "expected", "state"),
                       ("intervention", "parent", "comparator", "cost", "resource_ids", "note"))
                identifier(item["id"])
                item_ids.append(item["id"])
                require(item["state"] in ("planned", "running", "done", "dropped"), "Invalid plan item state")
                for key in ("parent", "comparator"):
                    if item.get(key) is not None:
                        identifier(item[key])
                require(all(isinstance(item[k], str) for k in ("title", "question", "expected", "intervention", "cost", "note") if k in item), "Invalid plan item text")
                require(isinstance(item.get("resource_ids", []), list), "resource_ids must be an array")
                for resource in item.get("resource_ids", []):
                    identifier(resource)
        require(len(item_ids) == len(set(item_ids)), "Duplicate plan item ID")
        require(isinstance(obj.get("ideas", []), list), "ideas must be an array")
        for idea in obj.get("ideas", []):
            fields(idea, ("title", "reason"))
            require(isinstance(idea["title"], str) and isinstance(idea["reason"], str), "Invalid idea")
    elif path == "resources.json":
        fields(obj, ("items",))
        require(isinstance(obj["items"], list), "items must be an array")
        ids = []
        for item in obj["items"]:
            fields(item, ("id", "title", "type", "status"), ("path", "location", "version", "size", "monitor", "purpose", "source", "preparation", "access"))
            identifier(item["id"])
            ids.append(item["id"])
            require(all(isinstance(item[k], str) for k in item if k != "monitor"), "Invalid resource text")
            require(item["status"] in ("ready", "missing", "changed", "busy", "unknown"), "Invalid resource status")
            require(not ("path" in item and "location" in item), "Use path or location, not both")
            if "path" in item:
                parts(item["path"])
            if "location" in item:
                require(item["location"].strip() and "\x00" not in item["location"], "Invalid external location")
            if "monitor" in item:
                probe = item["monitor"]
                fields(probe, ("kind",), ("index",))
                require(probe["kind"] in ("file", "memory", "nvidia_gpu", "python"), "Invalid monitor kind")
                require("index" not in probe or type(probe["index"]) is int and probe["index"] >= 0, "Invalid monitor index")
        require(len(ids) == len(set(ids)), "Duplicate resource ID")
    elif leaf == "definition.json":
        fields(obj, ("version", "description", "rubric", "metrics", "command"), ("no_final_reason",))
        identifier(obj["version"])
        require("no_final_reason" not in obj or isinstance(obj["no_final_reason"], str) and obj["no_final_reason"].strip(),
                "no_final_reason must be nonempty text")
        require(path.split("/")[1] == "draft" or obj["version"] == path.split("/")[1], "Version does not match directory")
        require(isinstance(obj["rubric"], str), "rubric must be text")
        argument_array(obj["command"])
        require(isinstance(obj["metrics"], list), "metrics must be an array")
        ids = []
        for metric in obj["metrics"]:
            fields(metric, ("id", "label", "direction"), ("description",))
            identifier(metric["id"])
            require(isinstance(metric["label"], str) and metric["direction"] in ("maximize", "minimize")
                    and isinstance(metric.get("description", ""), str), "Invalid metric definition")
            ids.append(metric["id"])
        require(len(ids) == len(set(ids)), "Duplicate metric ID")
    elif leaf == "analysis.json":
        fields(obj, ("outcome", "summary"))
        require(obj["outcome"] in ("baseline", "keep", "discard", "inconclusive", "invalid"), "Invalid analysis outcome")
    elif leaf == "config.json":
        if evaluation_run:
            fields(obj, ("id", "evaluation_version", "target_sha256", "evaluation_sha256", "execution"), ("inputs", "split"))
            identifier(obj["evaluation_version"])
            require(obj["evaluation_version"] != "draft", "Evaluation must be frozen")
            require(obj.get("split", "development") in SPLITS, "split must be development or final")
        else:
            fields(obj, ("id", "title", "parent_experiment_id", "hypothesis", "parameters", "inputs", "snapshot_sha256", "execution"),
                   ("method", "model_name", "framework", "role", "data_split"))
            require(obj.get("role", "candidate") in ("baseline", "candidate", "reference"), "Invalid experiment role")
            if "data_split" in obj:
                fields(obj["data_split"], ("path", "sha256"))
                parts(obj["data_split"]["path"])
                hash_value(obj["data_split"]["sha256"])
            if obj["parent_experiment_id"] is not None:
                identifier(obj["parent_experiment_id"])
            require(isinstance(obj["parameters"], dict), "parameters must be an object")
        identifier(obj["id"])
        require(obj["id"] == path.split("/")[-2], "ID does not match path")
        execution = obj["execution"]
        fields(execution, ("argv", "cwd", "environment", "timeout_seconds"))
        argument_array(execution["argv"])
        if execution["cwd"] != ".":
            parts(execution["cwd"])
        require(isinstance(execution["environment"], dict) and all(
            k and "=" not in k and "\x00" not in k and isinstance(v, str) and "\x00" not in v
            for k, v in execution["environment"].items()), "Invalid execution.environment")
        require(not any(re.search(r"(?:^|_)(?:API_KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?)(?:$|_)", name, re.I) for name in execution["environment"]), "Pass credentials through the inherited environment, not config overrides")
        require(finite_number(execution["timeout_seconds"]) and execution["timeout_seconds"] > 0, "Invalid timeout")
        require(isinstance(obj.get("inputs", []), list), "inputs must be an array")
        paths = []
        for item in obj.get("inputs", []):
            fields(item, ("path", "sha256"))
            parts(item["path"])
            hash_value(item["sha256"])
            paths.append(item["path"])
        require(len(paths) == len(set(paths)), "Duplicate input path")
    elif leaf == "status.json":
        fields(obj, ("state", "updated_at"), PROCESS + ("usage",) + (("metrics",) if evaluation_run else ("target",)))
        require(obj["state"] in ("pending", "running", "completed", *FINAL), "Invalid execution state")
        for key in ("updated_at", "started_at", "completed_at"):
            if key in obj:
                timestamp(obj[key])
        if "returncode" in obj:
            require(obj["returncode"] is None or type(obj["returncode"]) is int, "Invalid returncode")
        if "timed_out" in obj:
            require(type(obj["timed_out"]) is bool, "Invalid timed_out")
        if "elapsed_seconds" in obj:
            require(finite_number(obj["elapsed_seconds"]) and obj["elapsed_seconds"] >= 0, "Invalid elapsed_seconds")
        if obj["state"] in ("completed", "succeeded"):
            require(obj.get("returncode", 0) == 0 and not obj.get("timed_out") and "error" not in obj,
                    "Successful/completed status conflicts with process failure")
        if "usage" in obj:
            fields(obj["usage"], (), ("requests", "input_tokens", "output_tokens", "cost", "currency", "latency_seconds"))
            for key, value in obj["usage"].items():
                require(isinstance(value, str) and bool(value.strip()) if key == "currency" else finite_number(value) and value >= 0, "Invalid usage value")
            require("cost" not in obj["usage"] or "currency" in obj["usage"], "Cost requires currency")
        if "target" in obj:
            target = obj["target"]
            fields(target, ("kind", "path", "sha256"))
            require(target["kind"] in ("local", "api"), "Invalid target kind")
            parts(target["path"])
            hash_value(target["sha256"])
            base = path.rsplit("/", 1)[0] + "/model"
            require(target["path"] == base or target["path"].startswith(base + "/"), "Model must be inside this experiment's model directory")
        if "metrics" in obj:
            numbers(obj["metrics"])
    for key in ("name", "language", "title", "description", "summary", "hypothesis", "method", "model_name", "framework", "error"):
        if key in obj:
            require(isinstance(obj[key], str), f"{key} must be text")
    for key in ("snapshot_sha256", "target_sha256", "evaluation_sha256", "config_sha256"):
        if key in obj:
            hash_value(obj[key])
    return obj


def read_record(tree, path):
    return shape(path, tree.read(path))


def split_samples(tree, version, split="development"):
    """The frozen samples an evaluation run of this split scores; unmarked samples are development."""
    return [row for row in read_record(tree, f"evaluation/{version}/samples.jsonl") if row.get("split", "development") == split]


def check_installed_metadata(tree):
    """Fresh, uninstalled trees are allowed; an installed project must be pinned to these tools."""
    if not tree.exists(".workspace/manifest.json"):
        return False
    kit = strict(tree.read(".workspace/manifest.json"))
    require(isinstance(kit, dict) and kit.get("version") == VERSION,
            f"Project is pinned to other tools; tools {VERSION} do not migrate research")
    return True


def same_json(left, right):
    """Compare JSON values without Python's bool/number coercion or key order."""
    def canonical(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return canonical(left) == canonical(right)


def verify_hash(tree, path, expected):
    hash_value(expected)
    require(digest(tree.read(path)) == expected, f"Hash mismatch: {path}")


def verify_manifest(tree, base, expected=None):
    path = base + "/manifest.json"
    raw = tree.read(path)
    if expected is not None:
        hash_value(expected)
        require(digest(raw) == expected, f"Hash mismatch: {path}")
    manifest = strict(raw)
    fields(manifest, ("files",))
    require(isinstance(manifest["files"], list) and manifest["files"], "Empty or invalid manifest")
    listed = []
    for item in manifest["files"]:
        fields(item, ("path", "sha256"))
        parts(item["path"])
        require(item["path"] != "manifest.json", "Manifest cannot include itself")
        target = base + "/" + item["path"]
        verify_hash(tree, target, item["sha256"])
        listed.append(target)
    require(len(listed) == len(set(listed)), "Duplicate manifest paths")
    require(set(tree.files(base)) == set(listed) | {path}, "Manifest file set differs")
    return manifest


def verify_path_hash(tree, path, expected):
    """A file pins bytes; a directory pins its verified manifest bytes."""
    with tree.directory(parts(path)[:-1]) as parent:
        mode = os.stat(parts(path)[-1], dir_fd=parent, follow_symlinks=False).st_mode
    require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), f"Not a regular file or directory: {path}")
    if stat.S_ISDIR(mode):
        verify_manifest(tree, path, expected)
    else:
        verify_hash(tree, path, expected)


def check_invoke(tree, base):
    """An optional model entry point: argv receives an input and output JSONL path.

    `requires` pins files or verified directories outside the model, such as shared
    weights under resources/, so experiments that differ only in prompts or code
    reference one copy instead of duplicating it.
    """
    try:
        if not tree.exists(base + "/invoke.json"):
            return False
    except NotADirectoryError:
        return False
    entry = strict(tree.read(base + "/invoke.json"))
    fields(entry, ("argv",), ("description", "requires", "serve"))
    argument_array(entry["argv"])
    require(isinstance(entry.get("description", ""), str), "Invalid invoke description")
    if "serve" in entry:
        # A resident process: one JSONL request per stdin line, one answer per stdout line after {"ready":true}.
        fields(entry["serve"], ("argv",), ("memory_gb",))
        argument_array(entry["serve"]["argv"])
        if "memory_gb" in entry["serve"]:
            require(finite_number(entry["serve"]["memory_gb"]) and entry["serve"]["memory_gb"] > 0, "Invalid serve memory_gb")
    required = entry.get("requires", [])
    require(isinstance(required, list), "invoke requires must be an array")
    for item in required:
        fields(item, ("path", "sha256"))
        parts(item["path"])
        hash_value(item["sha256"])
        require(item["path"] != base and not item["path"].startswith(base + "/") and not base.startswith(item["path"] + "/"),
                "invoke requires must point outside the model")
    require(len({item["path"] for item in required}) == len(required), "Duplicate invoke requires paths")
    return True


def verify_requires(tree, base):
    """Verify the pinned files a model's entry point depends on."""
    if not check_invoke(tree, base):
        return
    for item in strict(tree.read(base + "/invoke.json")).get("requires", []):
        verify_path_hash(tree, item["path"], item["sha256"])


def verify_target(tree, target):
    verify_path_hash(tree, target["path"], target["sha256"])
    with tree.directory(parts(target["path"])[:-1]) as parent:
        if stat.S_ISDIR(os.stat(parts(target["path"])[-1], dir_fd=parent, follow_symlinks=False).st_mode):
            verify_requires(tree, target["path"])
    if target["kind"] == "api":
        # The directory manifest fixes the adapter as well as the descriptor, not remote weights.
        verify_manifest(tree, target["path"], target["sha256"])
        descriptor = strict(tree.read(target["path"] + "/api.json"))
        fields(descriptor, ("provider", "model", "request", "credential_env", "limitations"), ("revision", "endpoint"))
        require(all(isinstance(descriptor[key], str) and descriptor[key].strip() for key in ("provider", "model", "limitations")), "Invalid API identity")
        require(isinstance(descriptor["request"], dict), "API request must be an object")
        require(isinstance(descriptor["credential_env"], list) and all(isinstance(name, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", name) for name in descriptor["credential_env"]), "Invalid credential environment names")
        if "revision" in descriptor:
            require(isinstance(descriptor["revision"], str), "Invalid API revision")
        if "endpoint" in descriptor:
            from urllib.parse import urlsplit
            endpoint = urlsplit(descriptor["endpoint"])
            require(endpoint.scheme in ("http", "https") and endpoint.hostname and not endpoint.username and not endpoint.password and not endpoint.query and not endpoint.fragment, "Endpoint must not contain credentials")
        def no_credentials(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    require(str(key).lower().replace("-", "_") not in ("api_key", "x_api_key", "authorization", "password", "secret", "access_token", "token"), "Keep credentials out of API descriptors")
                    no_credentials(child)
            elif isinstance(value, list):
                for child in value:
                    no_credentials(child)
        no_credentials(descriptor["request"])


def byte_size(tree, path):
    with tree.directory(parts(path)[:-1]) as parent:
        mode = os.stat(parts(path)[-1], dir_fd=parent, follow_symlinks=False).st_mode
    if not stat.S_ISDIR(mode):
        with tree.directory(parts(path)[:-1]) as parent:
            return os.stat(parts(path)[-1], dir_fd=parent, follow_symlinks=False).st_size
    total = 0
    for name in tree.files(path):
        with tree.directory(parts(name)[:-1]) as parent:
            total += os.stat(parts(name)[-1], dir_fd=parent, follow_symlinks=False).st_size
    return total


def model_entry(tree, experiment, verify=True):
    """A local model's entry point, optional resident command and memory need, for running it from the panel.

    Without a declared serve memory_gb, memory is estimated as 1.2 times the bytes
    of the model and its pinned requires, which is rough and marked as an estimate.
    """
    require(isinstance(experiment, str) and re.fullmatch(ID, experiment), "Invalid experiment ID")
    status = verify_model(tree, "experiments/" + experiment) if verify else read_record(tree, f"experiments/{experiment}/status.json")
    target = status.get("target")
    require(status["state"] == "succeeded" and target, "Experiment requires a succeeded model")
    require(target["kind"] == "local", f"Experiment {experiment} is not a local model")
    require(check_invoke(tree, target["path"]), f"Experiment {experiment} has no invoke.json entry point")
    entry = strict(tree.read(target["path"] + "/invoke.json"))
    serve = entry.get("serve")
    declared = (serve or {}).get("memory_gb")
    if declared is None:
        size = byte_size(tree, target["path"]) + sum(byte_size(tree, item["path"]) for item in entry.get("requires", []))
        declared = max(0.01, round(size * 1.2 / 1e9, 2))
    return {"experiment": experiment, "target": target, "argv": entry["argv"], "serve": serve["argv"] if serve else None,
            "memory_gb": declared, "estimated": not (serve and "memory_gb" in serve)}


def verify_model(tree, experiment):
    read_record(tree, experiment + "/config.json")
    status = read_record(tree, experiment + "/status.json")
    require(status["state"] == "succeeded" and "target" in status, "Experiment requires a succeeded model")
    if "config_sha256" in status:
        verify_hash(tree, experiment + "/config.json", status["config_sha256"])
    verify_target(tree, status["target"])
    return status


def verify_inputs(tree, path, config):
    """Verify frozen packages, ancestry, model and any additional local inputs."""
    if "/evals/" in path:
        model = verify_model(tree, path.split("/evals/")[0])
        require(model["target"]["sha256"] == config["target_sha256"], "Model reference hash differs")
        evaluation = "evaluation/" + config["evaluation_version"]
        verify_manifest(tree, evaluation, config["evaluation_sha256"])
        read_record(tree, evaluation + "/definition.json")
        read_record(tree, evaluation + "/samples.jsonl")
    else:
        verify_manifest(tree, path + "/snapshot", config["snapshot_sha256"])
        seen = {config["id"]}
        parent = config["parent_experiment_id"]
        while parent is not None:
            require(parent not in seen, "Invalid parent experiment: ancestry cycle")
            seen.add(parent)
            parent = read_record(tree, f"experiments/{parent}/config.json")["parent_experiment_id"]
    for item in config.get("inputs", []):
        verify_path_hash(tree, item["path"], item["sha256"])
    if "data_split" in config:
        reference = config["data_split"]
        verify_hash(tree, reference["path"], reference["sha256"])
        split = strict(tree.read(reference["path"]))
        fields(split, ("train", "reserved"))
        for group in ("train", "reserved"):
            require(isinstance(split[group], list), "Split groups must be arrays")
            for item in split[group]:
                fields(item, ("path", "sha256"))
                verify_path_hash(tree, item["path"], item["sha256"])
        train_paths = {item["path"] for item in split["train"]}
        reserved_paths = {item["path"] for item in split["reserved"]}
        require(not train_paths & reserved_paths and not {item["sha256"] for item in split["train"]} & {item["sha256"] for item in split["reserved"]}, "Training and reserved inputs overlap")
        declared = {(item["path"], item["sha256"]) for item in config["inputs"]}
        require(all((item["path"], item["sha256"]) in declared for item in split["train"]), "Declare every training input")
        for item in config["inputs"]:
            require(not any(item["path"] == reserved or reserved.startswith(item["path"] + "/") or item["path"].startswith(reserved + "/") for reserved in reserved_paths)
                    and item["sha256"] not in {row["sha256"] for row in split["reserved"]}, "Reserved input used by experiment")


def attachment_paths(value, found, depth=0):
    """Display attachment paths inside a value, the same explicit {type,path} references the panel serves."""
    if depth > 8:
        return found
    if isinstance(value, dict):
        if value.get("type") in ("image", "audio", "video", "file") and isinstance(value.get("path"), str):
            found.add(value["path"])
        for child in value.values():
            attachment_paths(child, found, depth + 1)
    elif isinstance(value, list):
        for child in value:
            attachment_paths(child, found, depth + 1)
    return found


def check_attachments(tree, path, obj, package=None):
    """Attachment paths are project-relative, so a path relative to its evaluation directory shows nowhere.
    `package` is (frozen destination, files being frozen into it): files there count before they are copied."""
    found = set()
    if path == "proposal.json":
        for example in obj.get("examples", []):
            if isinstance(example, dict):
                for key in ("input", "expected_output"):
                    if key in example:
                        attachment_paths(example[key], found)
    elif path.endswith("/samples.jsonl"):
        for row in obj:
            for key in ("input", "reference"):
                if key in row:
                    attachment_paths(row[key], found)
    drafted = re.fullmatch(rf"evaluation/({ID})/samples\.jsonl", path)
    missing = []
    for item in sorted(found):
        if tree.exists(item):
            continue
        if package and item.startswith(package[0] + "/") and item[len(package[0]) + 1:] in package[1]:
            continue
        # A draft's pictures move with it when frozen, so a later version directory is a valid address.
        later = re.fullmatch(rf"evaluation/{ID}/(.+)", item)
        if drafted and drafted.group(1) == "draft" and later and tree.exists("evaluation/draft/" + later.group(1)):
            continue
        missing.append(item)
    require(not missing, "Attachment paths are relative to the project root and must exist (not relative to the evaluation directory); missing: "
            + ", ".join(missing[:3]) + (" …" if len(missing) > 3 else ""))


def check_record(tree, path, obj):
    """Check references and success evidence, also before publication."""
    if path == "proposal.json" or path.endswith("/samples.jsonl"):
        check_attachments(tree, path, obj)
    if path == "project.json":
        if obj["current_evaluation"] is not None:
            base = "evaluation/" + obj["current_evaluation"]
            verify_manifest(tree, base)
            read_record(tree, base + "/definition.json")
            read_record(tree, base + "/samples.jsonl")
        for ident in obj["deliveries"]:
            require(verify_model(tree, "experiments/" + ident)["target"]["kind"] == "local", "Only local models can be deliveries")
    elif path == "proposal.json":
        resources = read_record(tree, "resources.json")
        ids = {item["id"] for item in resources["items"]}
        require(all(ident in ids for approach in obj.get("approaches", []) for ident in approach.get("resource_ids", [])), "Unknown approach resource")
    elif path == "plan.json":
        resources = {item["id"] for item in read_record(tree, "resources.json")["items"]}
        for round_ in obj["rounds"]:
            for item in round_["items"]:
                require(all(ident in resources for ident in item.get("resource_ids", [])), "Unknown plan item resource")
                if item["state"] in ("running", "done"):
                    require(tree.exists(f"experiments/{item['id']}/config.json"), f"Plan item {item['id']} has no experiment")
    elif path == "resources.json":
        for item in obj["items"]:
            if "path" in item and tree.exists(item["path"]):
                with tree.directory(parts(item["path"])[:-1]) as parent:
                    mode = os.stat(parts(item["path"])[-1], dir_fd=parent, follow_symlinks=False).st_mode
                require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), "Resource path is not a regular file or directory")
    elif path == "comparison/outputs.jsonl":
        for ident in {ident for row in obj for ident in row["outputs"]}:
            read_record(tree, f"experiments/{ident}/config.json")
    elif path.startswith("experiments/"):
        base, leaf = path.rsplit("/", 1)
        if leaf == "config.json":
            verify_inputs(tree, base, obj)
            return
        config = read_record(tree, base + "/config.json")
        if leaf == "status.json":
            if "config_sha256" in obj:
                verify_hash(tree, base + "/config.json", obj["config_sha256"])
            if "target" in obj:
                verify_target(tree, obj["target"])
            if "/evals/" in base:
                definition = read_record(tree, f"evaluation/{config['evaluation_version']}/definition.json")
                metrics = {m["id"] for m in definition["metrics"]}
                require(set(obj.get("metrics", {})) <= metrics, "Unknown metric IDs")
                if obj["state"] == "succeeded":
                    require("metrics" in obj and set(obj["metrics"]) == metrics, "Successful evaluation requires all declared metrics")
                    if config.get("split") == "final":
                        require(not tree.exists(base + "/outputs.jsonl"), "Final-check runs publish only aggregate metrics")
                    else:
                        outputs = read_record(tree, base + "/outputs.jsonl")
                        require(outputs, "Successful evaluation requires outputs")
                        check_record(tree, base + "/outputs.jsonl", outputs)
                        samples = split_samples(tree, config["evaluation_version"])
                        require({r["sample_id"] for r in outputs} == {r["sample_id"] for r in samples}, "Successful evaluation requires outputs for all samples of its split")
            elif obj["state"] == "succeeded":
                require("target" in obj, "Successful experiment requires a model")
            if obj["state"] == "succeeded":
                verify_inputs(tree, base, config)
        elif leaf == "outputs.jsonl":
            require(config.get("split") != "final", "Final-check runs publish only aggregate metrics")
            evaluation = f"evaluation/{config['evaluation_version']}"
            samples = {row["sample_id"]: row for row in read_record(tree, evaluation + "/samples.jsonl")}
            metrics = {m["id"] for m in read_record(tree, evaluation + "/definition.json")["metrics"]}
            for row in obj:
                sample = samples.get(row["sample_id"])
                require(sample is not None, "Unknown output sample_id")
                require(sample.get("split", "development") == "development", "Outputs include final-check samples")
                require(same_json(row["input"], sample["input"]), "Output input differs from sample")
                require("reference" not in row or "reference" in sample and same_json(row["reference"], sample["reference"]), "Output reference differs from sample")
                require(set(row.get("scores", {})) <= metrics, "Unknown score IDs")


def mutable(path, old, tree=None):
    return (path in ("project.json", "proposal.json", "plan.json", "resources.json", "comparison/inputs.jsonl", "comparison/outputs.jsonl")
            or path.startswith("evaluation/draft/") or path.endswith("/analysis.json")
            or path.endswith("/status.json") and old["state"] not in FINAL)


def write(tree, path, source, create=False, expected=None):
    parts(path)
    require(bool(RECORD.fullmatch(path)), "Path is not a writable research record")
    require(not path.startswith("responses/"), "Responses are written only by the person through the panel")
    require(not create or expected is None, "Choose create or expected SHA-256, not both")
    require(".." not in os.fspath(source).split("/"), "Parent traversal is not allowed")
    source_path = Path(os.path.abspath(source))
    source_tree = Tree(source_path.parent)
    try:
        data = source_tree.read(source_path.name)
    finally:
        source_tree.close()
    obj = shape(path, data)
    with tree.locked():
        if tree.exists("project.json"):
            read_record(tree, "project.json")
        if create:
            require(not tree.exists(path), "Record already exists")
        else:
            hash_value(expected)
            previous = tree.read(path)
            old = shape(path, previous)
            require(mutable(path, old), "Record is immutable")
            require(digest(previous) == expected, "Conflict: expected hash differs")
            if path.endswith("/status.json"):
                allowed = {"pending": ("pending", "running", "completed", *FINAL),
                           "running": ("running", "completed", *FINAL), "completed": ("completed", *FINAL)}
                require(obj["state"] in allowed[old["state"]], "Execution state cannot move backwards")
                for key in (*PROCESS, "metrics", "target", "usage"):
                    require(key not in old or key in obj and obj[key] == old[key], f"Preserve recorded fact: {key}")
        if path.startswith("evaluation/") and not path.startswith("evaluation/draft/"):
            require(not tree.exists(path.rsplit("/", 1)[0] + "/manifest.json"), "Frozen package is immutable")
        if path.endswith("/outputs.jsonl") and path.startswith("experiments/"):
            status_path = path.replace("outputs.jsonl", "status.json")
            require(not tree.exists(status_path) or read_record(tree, status_path)["state"] not in FINAL, "Final measurements are immutable")
        check_record(tree, path, obj)
        tree.publish(path, data, replace=not create)
    return {"path": path, "sha256": digest(data)}


def freeze(tree, root, source, path):
    require(bool(re.fullmatch(rf"evaluation/{ID}|experiments/{ID}/snapshot", path)) and path != "evaluation/draft", "Invalid freeze destination")
    require(".." not in os.fspath(source).split("/"), "Parent traversal is not allowed")
    source_path, destination = Path(os.path.abspath(source)), Path(os.path.abspath(root)) / path
    require(source_path != destination and source_path not in destination.parents and destination not in source_path.parents, "Source and destination overlap")
    source_tree = Tree(source_path)
    try:
        names = source_tree.files("")
        require(names and "manifest.json" not in names, "Source must be nonempty without manifest.json")
        for name in names:
            segments = parts(name)
            require(not any(segment.startswith(".") or segment in ("__pycache__", "node_modules", "cache") for segment in segments)
                    and Path(name).suffix.lower() not in (".pyc", ".pyo", ".pem", ".key")
                    and not any(word in Path(name).name.lower() for word in ("credentials", "secrets")), "Unsafe snapshot content: " + name)
        payload = {name: source_tree.read(name, with_mode=True) for name in names}
        if path.startswith("evaluation/"):
            require("definition.json" in payload and "samples.jsonl" in payload, "Evaluation requires definition.json and samples.jsonl")
            definition = shape(path + "/definition.json", payload["definition.json"][0])
            rows = shape(path + "/samples.jsonl", payload["samples.jsonl"][0])
            splits = [row.get("split", "development") for row in rows]
            check_attachments(tree, path + "/samples.jsonl", rows, (path, set(payload)))
            # A final check has to be set aside before methods are tuned, or decided against openly.
            require("development" in splits, "Evaluation requires development samples")
            require("final" in splits or "no_final_reason" in definition,
                    'Mark final-check samples with "split": "final", or state definition no_final_reason')
        with tree.locked():
            if tree.exists("project.json"):
                read_record(tree, "project.json")
            segments = parts(path)
            with tree.directory(segments[:-1], create=True) as parent:
                os.mkdir(segments[-1], dir_fd=parent)
            for name, (data, mode) in payload.items():
                tree.publish(path + "/" + name, data, mode=mode)
            manifest_data = encoded({"files": [{"path": name, "sha256": digest(data)} for name, (data, _) in payload.items()]})
            tree.publish(path + "/manifest.json", manifest_data)
        return {"path": path, "files": len(payload), "manifest_sha256": digest(manifest_data)}
    finally:
        source_tree.close()


def manifest(tree, path):
    """Generate one model or resource directory manifest in place, without copying data."""
    parts(path)
    require(re.fullmatch(rf"experiments/{ID}/model(?:/.+)?|resources/.+", path),
            "Manifest destination must be an experiment model or resource directory")
    with tree.locked():
        read_record(tree, "project.json")
        return write_manifest(tree, path)


def write_manifest(tree, path):
    """Caller holds the lock."""
    require(not tree.exists(path + "/manifest.json"), "Manifest already exists")
    status_path = "/".join(parts(path)[:2]) + "/status.json"
    require(not tree.exists(status_path) or read_record(tree, status_path)["state"] not in FINAL, "Final models are immutable")
    for length in range(3, len(parts(path))):
        require(not tree.exists("/".join(parts(path)[:length]) + "/manifest.json"), "Frozen model package is immutable")
    names = tree.files(path)
    require(names, "Empty model directory")
    data = encoded({"files": [{"path": name[len(path) + 1:], "sha256": digest(tree.read(name))} for name in names]})
    tree.publish(path + "/manifest.json", data)
    return {"path": path, "files": len(names), "manifest_sha256": digest(data)}


def finalize(tree, path, kind="local", target=None):
    """Publish a completed attempt's conventional results and mark it succeeded.

    An experiment publishes its model directory (or `target` inside it). An
    evaluation run publishes `result/outputs.jsonl` rows `{sample_id,output,scores?}`,
    `result/metrics.json` and optional `result/usage.json`; inputs and references
    are copied from the frozen samples. A final-check run publishes only its metrics
    and removes the per-sample rows once their coverage is checked; its result may hold
    no other files. Nothing is
    published unless every check passes.
    """
    require(isinstance(path, str) and re.fullmatch(ATTEMPT, path), "Invalid attempt path")
    require(kind in ("local", "api"), "Invalid target kind")
    with tree.locked():
        read_record(tree, "project.json")
        config = read_record(tree, path + "/config.json")
        status = read_record(tree, path + "/status.json") if tree.exists(path + "/status.json") else {}
        require(status.get("state") == "completed", "Only a completed attempt can be finalized")
        status = dict(status, state="succeeded", updated_at=datetime.now().astimezone().isoformat())
        verify_inputs(tree, path, config)
        if "/evals/" in path:
            require(target is None and kind == "local", "Evaluation runs have no target")
            evaluation = "evaluation/" + config["evaluation_version"]
            final = config.get("split") == "final"
            if final:
                # Any other file, such as a scorer's per-image scratch, would keep final per-sample results to tune against.
                extra = [name for name in tree.files(path + "/result")
                         if name.rsplit("/", 1)[-1] not in ("outputs.jsonl", "metrics.json", "usage.json")]
                require(not extra, "A final-check result may contain only outputs.jsonl, metrics.json and usage.json; "
                        "have the evaluation remove its other files before exiting: " + ", ".join(extra[:5]))
            samples = {row["sample_id"]: row for row in split_samples(tree, config["evaluation_version"], config.get("split", "development"))}
            rows = []
            for line in tree.read(path + "/result/outputs.jsonl").decode("utf-8").splitlines():
                if line.strip():
                    row = strict(line)
                    require(isinstance(row, dict) and row.get("sample_id") in samples, "Unknown output sample_id for this run's split")
                    sample = samples[row["sample_id"]]
                    row = {"sample_id": row["sample_id"], "input": sample["input"],
                           **({"reference": sample["reference"]} if "reference" in sample else {}),
                           **{k: v for k, v in row.items() if k != "sample_id"}}
                    rows.append(row)
            data = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows).encode("utf-8")
            outputs = shape(path + "/outputs.jsonl", data)
            require({row["sample_id"] for row in outputs} == set(samples), "Outputs must cover every sample of this run's split")
            status["metrics"] = strict(tree.read(path + "/result/metrics.json"))
            if tree.exists(path + "/result/usage.json"):
                status["usage"] = strict(tree.read(path + "/result/usage.json"))
            status_data = encoded(status)
            shape(path + "/status.json", status_data)
            metrics = {m["id"] for m in read_record(tree, evaluation + "/definition.json")["metrics"]}
            require(set(status["metrics"]) == metrics, "Successful evaluation requires all declared metrics")
            require(not tree.exists(path + "/outputs.jsonl"), "Outputs already published; finalize the status explicitly")
            if not final:
                check_record(tree, path + "/outputs.jsonl", outputs)
                tree.publish(path + "/outputs.jsonl", data)
        else:
            target = target or path + "/model"
            require(target == path + "/model" or target.startswith(path + "/model/"), "Target must be inside this experiment's model directory")
            with tree.directory(parts(target)[:-1]) as parent:
                directory = stat.S_ISDIR(os.stat(parts(target)[-1], dir_fd=parent, follow_symlinks=False).st_mode)
            if directory:
                verify_requires(tree, target)
            if not directory:
                sha = digest(tree.read(target))
            elif tree.exists(target + "/manifest.json"):
                verify_manifest(tree, target)
                sha = digest(tree.read(target + "/manifest.json"))
            else:
                sha = write_manifest(tree, target)["manifest_sha256"]
            status["target"] = {"kind": kind, "path": target, "sha256": sha}
            status_data = encoded(status)
            shape(path + "/status.json", status_data)
        check_record(tree, path + "/status.json", status)
        tree.publish(path + "/status.json", status_data, replace=True)
        if "/evals/" in path and config.get("split") == "final":
            # Per-sample final results would invite tuning against the final check.
            with tree.directory(parts(path + "/result")) as result:
                os.unlink("outputs.jsonl", dir_fd=result)
    return status


def validate(tree):
    report = {"errors": [], "warnings": [], "unfinished": []}
    docs = {}
    def error(path, exc):
        report["errors"].append(f"{path}: {exc}")
    names = [p for p in ("project.json", "proposal.json", "plan.json", "resources.json") if tree.exists(p)]
    for prefix in ("evaluation", "experiments", "comparison", "responses"):
        try:
            if tree.exists(prefix):
                names.extend(tree.files(prefix))
        except (OSError, ValueError) as exc:
            error(prefix, exc)
    for path in names:
        if RECORD.fullmatch(path):
            try:
                docs[path] = read_record(tree, path)
            except (OSError, ValueError, TypeError) as exc:
                error(path, exc)
    for required in ("project.json", "proposal.json", "resources.json"):
        if required not in docs:
            error(required, "Missing or invalid core record")
    try:
        if not check_installed_metadata(tree):
            report["warnings"].append("Missing workspace manifest; tool compatibility is not verified")
    except (OSError, ValueError, TypeError) as exc:
        error(".workspace/manifest.json", exc)
    packages = {p.rsplit("/", 1)[0] for p in names if re.fullmatch(rf"evaluation/{ID}/(?:definition.json|samples.jsonl|manifest.json)|experiments/{ID}/snapshot/manifest.json", p)}
    packages |= {p.rsplit("/", 1)[0] + "/snapshot" for p in docs if re.fullmatch(rf"experiments/{ID}/config.json", p)}
    # An evaluation version has a definition or samples; a manifest alone pins other material, such as reserved sources.
    versions = {p.rsplit("/", 1)[0] for p in names if re.fullmatch(rf"evaluation/{ID}/(?:definition.json|samples.jsonl)", p)}
    for base in sorted(packages - {"evaluation/draft"}):
        try:
            verify_manifest(tree, base)
            if base in versions:
                read_record(tree, base + "/definition.json")
                read_record(tree, base + "/samples.jsonl")
        except (OSError, ValueError, TypeError) as exc:
            error(base, exc)
    problem, omitted = display_check(tree)
    if problem:
        error("panel", problem)
    for item in omitted:
        report["warnings"].append(f"The panel leaves out {item['path']} ({item['size']} bytes), too large even to page")
    current = docs.get("project.json", {}).get("current_evaluation")
    measured = {(run["experiment"], run["target_sha256"]) for run in final_runs(docs) if run["version"] == current and run["state"] == "succeeded"}
    for ident in docs.get("project.json", {}).get("deliveries", []):
        try:
            target = read_record(tree, f"experiments/{ident}/status.json").get("target", {})
            if not target.get("path") or not check_invoke(tree, target["path"]):
                report["warnings"].append(f"Delivery {ident} has no invoke.json entry point")
            elif any(not tree.exists(item["path"]) for item in strict(tree.read(target["path"] + "/invoke.json")).get("requires", [])):
                report["warnings"].append(f"Delivery {ident} requires files that are missing")
            if current and split_samples(tree, current, "final") and (ident, target.get("sha256")) not in measured:
                report["warnings"].append(f"Delivery {ident} has no final-check measurement on evaluation {current}")
        except (OSError, ValueError, TypeError):
            pass
    deliveries = set(docs.get("project.json", {}).get("deliveries", []))
    if deliveries:
        # Leakage leads surface where a model is chosen, without a separate step to remember.
        try:
            for finding in audit(tree)["findings"]:
                if finding["experiment"] in deliveries:
                    report["warnings"].append(f"Delivery {finding['experiment']} audit {finding['check']}: "
                                              + ", ".join(finding["values"][:5]) + (" …" if finding["count"] > 5 else ""))
        except (OSError, ValueError, TypeError):
            pass
    for path, obj in docs.items():
        try:
            check_record(tree, path, obj)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            error(path, exc)
        if path.startswith("experiments/") and path.endswith("/config.json"):
            base = path.rsplit("/", 1)[0]
            if docs.get(base + "/status.json", {}).get("state") not in FINAL:
                report["unfinished"].append(base)
    report["valid"] = not report["errors"]
    return report


def display_check(tree):
    """(problem, omitted): what would stop the panel from showing these records and what it leaves out,
    read with the panel's own reader beside this tool, so the two never disagree."""
    source = Path(__file__).with_name("workspace.py")
    if not source.is_file():
        return None, []
    try:
        spec = importlib.util.spec_from_file_location("tunetune_display", source)
        module = importlib.util.module_from_spec(spec)
        previous = sys.dont_write_bytecode
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        _, _, omitted = module.load_display(module.SafeTree(tree.root))
    except (OSError, ValueError, RecursionError) as exc:
        return f"The panel cannot show these records: {exc}", []
    return None, omitted


def final_runs(docs):
    """Every final-check attempt among loaded records, whatever its state, so repeated use stays visible."""
    runs = []
    for path, config in sorted(docs.items()):
        if re.fullmatch(rf"experiments/{ID}/evals/{ID}/config\.json", path) and config.get("split") == "final":
            runs.append({"experiment": path.split("/")[1], "run": path.split("/")[3], "version": config["evaluation_version"],
                         "target_sha256": config["target_sha256"],
                         "state": docs.get(path.replace("config.json", "status.json"), {}).get("state", "pending")})
    return runs


def strings(value):
    if isinstance(value, str):
        yield value.strip()
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def readable_text(tree, base, limit=1_000_000):
    """UTF-8 text a method was written in: prompts, code and configuration, not weights or other large files."""
    if not tree.exists(base):
        return {}
    try:
        names = tree.files(base)
    except NotADirectoryError:
        names = [base]
    found = {}
    for name in names:
        if name.endswith("/manifest.json") or byte_size(tree, name) > limit:
            continue
        try:
            found[name] = tree.read(name).decode("utf-8")
        except UnicodeDecodeError:
            continue
    return found


def windows(value, size=30):
    """A few fixed spans of a long text; one verbatim span in a method is enough to show it was copied."""
    value = " ".join(value.split())
    if len(value) < size * 2:
        return []
    return [value[:size], value[len(value) // 2:len(value) // 2 + size], value[-size:]]


def audit(tree):
    """Read-only leakage checks of methods against evaluation material; findings are leads to explain, not verdicts.

    A method's own files (snapshot, model directory without large files) are searched
    for labels that only final-check references contain, reference labels the proposal
    never names, verbatim final-check content and paths into evaluation packages.
    """
    docs = {}
    for prefix in ("evaluation", "experiments"):
        if tree.exists(prefix):
            for path in tree.files(prefix):
                if RECORD.fullmatch(path):
                    try:
                        docs[path] = read_record(tree, path)
                    except (OSError, ValueError, TypeError):
                        continue
    proposal = json.dumps(read_record(tree, "proposal.json"), ensure_ascii=False) if tree.exists("proposal.json") else ""
    labels = {"development": set(), "final": set()}
    final_texts = []
    for path, rows in docs.items():
        if re.fullmatch(rf"evaluation/{ID}/samples\.jsonl", path):
            for row in rows:
                split = row.get("split", "development")
                for value in strings(row.get("reference")):
                    if 2 <= len(value) <= 40:
                        labels[split].add(value)
                    elif split == "final":
                        final_texts.extend(windows(value))
                if split == "final":
                    final_texts.extend(span for value in strings(row["input"]) for span in windows(value))
    only_final = labels["final"] - labels["development"] - {label for label in labels["final"] if label in proposal}
    unconfirmed = (labels["development"] | labels["final"]) - {label for label in labels["development"] | labels["final"] if label in proposal}
    findings = []
    for path in sorted(docs):
        if not re.fullmatch(rf"experiments/{ID}/config\.json", path):
            continue
        experiment = path.split("/")[1]
        texts = {name: body for base in ("snapshot", "model") for name, body in readable_text(tree, f"experiments/{experiment}/{base}").items()}
        corpus = "\n".join(texts.values())
        def found(values):
            return sorted(value for value in values if value in corpus)
        for check, values in (("final_label", found(only_final)), ("unconfirmed_vocabulary", found(unconfirmed)),
                              ("final_content", found(set(final_texts)))):
            if values:
                findings.append({"experiment": experiment, "check": check, "values": values[:20], "count": len(values)})
        reading = sorted(name for name, body in texts.items() if re.search(r"evaluation/|TUNETUNE_EVALUATION|TUNETUNE_SAMPLES", body))
        if reading:
            findings.append({"experiment": experiment, "check": "reads_evaluation", "values": reading[:20], "count": len(reading)})
    usage = {}
    for run in final_runs(docs):
        entry = usage.setdefault(run["version"], {"attempts": 0, "succeeded": 0, "experiments": []})
        entry["attempts"] += 1
        entry["succeeded"] += run["state"] == "succeeded"
        if run["experiment"] not in entry["experiments"]:
            entry["experiments"].append(run["experiment"])
    return {"findings": findings, "final_checks": usage}


def next_id(tree, slug=None):
    """Next sequential experiment ID, counting existing experiments and planned items."""
    if slug is not None:
        require(bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)) and len(slug) <= 40, "Slug must be short lowercase words joined by hyphens")
    taken = []
    if tree.exists("experiments"):
        with tree.directory(["experiments"]) as fd:
            taken.extend(os.listdir(fd))
    if tree.exists("plan.json"):
        taken.extend(item["id"] for round_ in read_record(tree, "plan.json")["rounds"] for item in round_["items"])
    numbers = [int(m.group(1)) for name in taken if (m := re.fullmatch(r"e(\d{3,})(?:-.*)?", name))]
    number = max(numbers) + 1 if numbers else 0
    return {"id": f"e{number:03d}" + (f"-{slug}" if slug else "")}


def publish_response(tree, kind, decision, target_sha256, note=None, items=None):
    """Record the person's answer from the panel, bound to the exact bytes they saw."""
    require(kind in RESPONSE_TARGETS, "Invalid response kind")
    hash_value(target_sha256)
    target = RESPONSE_TARGETS[kind]
    with tree.locked():
        require(tree.exists(target), f"{target} does not exist")
        require(digest(tree.read(target)) == target_sha256, "Conflict: the file changed after it was shown; reload and respond again")
        ident = "r" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        value = {"id": ident, "kind": kind, "target": {"path": target, "sha256": target_sha256},
                 "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "decision": decision}
        if note:
            value["note"] = note
        if items:
            value["items"] = items
        path = f"responses/{ident}.json"
        data = encoded(value)
        shape(path, data)
        if kind == "evaluation_review":
            known = {row["sample_id"] for row in read_record(tree, target)}
            require(all(item["sample_id"] in known for item in items or []), "Unknown reviewed sample")
        elif kind == "acceptance":
            shown = {row["sample_id"]: row["outputs"] for row in read_record(tree, target)}
            require(items, "Acceptance feedback needs at least one judged output")
            require(all(item["experiment_id"] in shown.get(item["sample_id"], {}) for item in items), "Judged output was not shown")
            require(len({(item["sample_id"], item["experiment_id"]) for item in items}) == len(items), "Duplicate judged output")
        tree.publish(path, data)
    return value


def set_view(tree, open_views=(), focus=None, attention=(), clear=False):
    """Publish panel focus for the person; this is display state, not research evidence."""
    for view in open_views:
        require(view in VIEWS, f"Unknown view: {view}")
    if focus is not None:
        identifier(focus)
    notes = []
    for raw in attention:
        view, sep, message = raw.partition(":")
        require(sep and view in VIEWS and message.strip() and len(message) <= 200, "Attention must be view:message")
        notes.append({"view": view, "message": message.strip()})
    with tree.locked():
        previous = {}
        if tree.exists(".workspace/view.json"):
            try:
                previous = strict(tree.read(".workspace/view.json"))
            except ValueError:
                previous = {}
        kept = [] if clear else [n for n in previous.get("attention", []) if isinstance(n, dict) and n.get("view") not in {x["view"] for x in notes}]
        value = {"revision": int(previous.get("revision", 0)) + 1 if isinstance(previous.get("revision", 0), int) else 1,
                 "open": list(dict.fromkeys(open_views)), "attention": kept + notes,
                 "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        if focus is not None:
            value["focus"] = {"experiment": focus}
        tree.publish(".workspace/view.json", encoded(value), replace=tree.exists(".workspace/view.json"))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("hash", "validate", "audit", "write", "freeze", "manifest", "finalize", "next-id", "view"):
        command = commands.add_parser(name)
        command.add_argument("--project", required=True)
        if name == "next-id":
            command.add_argument("--slug")
        elif name == "view":
            command.add_argument("--open", action="append", default=[], choices=VIEWS)
            command.add_argument("--focus")
            command.add_argument("--attention", action="append", default=[], help="view:message for the person")
            command.add_argument("--clear", action="store_true", help="drop earlier attention notes")
        elif name not in ("validate", "audit"):
            command.add_argument("--path", required=True)
        if name == "finalize":
            command.add_argument("--kind", choices=("local", "api"), default="local")
            command.add_argument("--target")
        if name == "write":
            command.add_argument("--input", required=True)
            mode = command.add_mutually_exclusive_group(required=True)
            mode.add_argument("--create", action="store_true")
            mode.add_argument("--expected-sha256")
        if name == "freeze":
            command.add_argument("--source", required=True)
    args = parser.parse_args()
    tree = None
    try:
        tree = Tree(args.project)
        if args.command == "validate":
            result = validate(tree)
        elif args.command == "audit":
            result = audit(tree)
        elif args.command == "view":
            result = set_view(tree, args.open, args.focus, args.attention, args.clear)
        elif args.command == "next-id":
            result = next_id(tree, args.slug)
        elif args.command == "hash":
            result = {"path": args.path, "sha256": digest(tree.read(args.path))}
        elif args.command == "write":
            result = write(tree, args.path, args.input, args.create, args.expected_sha256)
        elif args.command == "manifest":
            result = manifest(tree, args.path)
        elif args.command == "finalize":
            result = finalize(tree, args.path, args.kind, args.target)
        else:
            result = freeze(tree, args.project, args.source, args.path)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("valid") is False else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if tree:
            tree.close()


if __name__ == "__main__":
    sys.exit(main())
