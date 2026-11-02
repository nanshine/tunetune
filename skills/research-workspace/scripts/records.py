#!/usr/bin/env python3
"""Validate and publish research files without executing research commands."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import uuid

ID = r"[A-Za-z0-9_-]+"
SHA = re.compile(r"[a-f0-9]{64}\Z")
FINAL = ("succeeded", "failed", "cancelled")
RECORD = re.compile(
    rf"(?:project|goal|resources|candidates|workspace)\.json|review\.md|"
    rf"evaluation/(?:draft|versions/{ID})/definition\.json|"
    rf"experiments/{ID}/(?:config|status|artifacts)\.json|experiments/{ID}/analysis\.md|"
    rf"assessments/{ID}/(?:config|status|result)\.json|assessments/{ID}/outputs\.jsonl|"
    rf"releases/{ID}\.json|acceptance/{ID}/(?:config\.json|outputs\.jsonl)|"
    rf"feedback/(?:requests|responses|incoming|handled)/{ID}\.json")


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
    return json.loads(data, object_pairs_hook=pairs, parse_float=number,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid number: {value}")))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    require(datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None, "Timestamp requires timezone")


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

    def close(self):
        os.close(self.fd)

    @contextmanager
    def directory(self, segments, create=False):
        fd = os.dup(self.fd)
        try:
            for segment in segments:
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
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass


def shape(path, data):
    if path.endswith(".md"):
        data.decode("utf-8")
        return None
    if path.endswith(".jsonl"):
        rows = [strict(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        ids = []
        for row in rows:
            require(isinstance(row, dict), "JSONL row must be an object")
            require(all(k in row for k in ("sample_id", "input", "outputs" if path.startswith("acceptance/") else "output")), "Missing output fields")
            require(isinstance(row["sample_id"], str) and row["sample_id"], "sample_id must be nonempty")
            ids.append(row["sample_id"])
        require(len(ids) == len(set(ids)), "Duplicate sample_id")
        return rows
    obj = strict(data)
    require(isinstance(obj, dict), "JSON must be an object")
    leaf = path.split("/")[-1]
    fields = {
        "project.json": ("schema_version", "name", "language", "current_evaluation"),
        "goal.json": ("revision", "summary", "sections", "examples"),
        "resources.json": ("items",), "candidates.json": ("items",),
        "workspace.json": ("title", "metric_columns"),
        "definition.json": ("version", "description", "metrics", "datasets"),
        "status.json": ("state", "updated_at"), "result.json": ("state", "metrics", "completed_at"),
        "artifacts.json": ("items",),
    }.get(leaf, ())
    if leaf == "config.json":
        fields = ("id", "title", "parent_experiment_id", "goal_revision", "evaluation_version") if path.startswith("experiments/") else (
            ("id", "experiment_id", "artifact_id", "evaluation_version") if path.startswith("assessments/") else ("id", "version", "release_ids"))
    if path.startswith("releases/"):
        fields = ("id", "experiment_id", "artifact_id", "assessment_ids", "notes")
    if path.startswith("feedback/"):
        fields = {
            "requests": ("id", "title", "prompt", "options"),
            "responses": ("id", "kind", "text", "target", "target_sha256", "source", "created_at", "request_id"),
            "incoming": ("id", "kind", "text", "target", "target_sha256", "source", "created_at"),
            "handled": ("id", "feedback_id", "disposition", "reason", "changes"),
        }[path.split("/")[1]]
    require(all(key in obj for key in fields), f"Missing required fields: {', '.join(fields)}")
    for key in ("items", "examples", "sections", "sources", "datasets", "options", "changes", "metric_columns", "assessment_ids", "release_ids"):
        if key in obj:
            require(isinstance(obj[key], list), f"{key} must be an array")
    for key in ("name", "language", "title", "description", "summary", "proposal", "context", "expected_result", "prompt", "text", "reason", "notes"):
        if key in obj:
            require(isinstance(obj[key], str), f"{key} must be text")
    for key in ("id", "experiment_id", "artifact_id", "evaluation_version", "feedback_id", "request_id", "parent_experiment_id", "current_evaluation"):
        if key in obj and obj[key] is not None:
            require(isinstance(obj[key], str) and re.fullmatch(ID, obj[key]), f"Invalid {key}")
    if "id" in obj:
        expected = path.split("/")[-2] if leaf == "config.json" else Path(path).stem
        require(obj["id"] == expected, "ID does not match path")
    if path == "goal.json":
        require(all(isinstance(section, dict) and isinstance(section.get("title"), str)
                    and isinstance(section.get("body"), str) for section in obj["sections"]), "Invalid goal section")
        ids = []
        for example in obj["examples"]:
            require(isinstance(example, dict) and isinstance(example.get("id"), str)
                    and re.fullmatch(ID, example["id"]), "Invalid goal example ID")
            require(all(isinstance(example.get(key, ""), str) for key in ("title", "input", "expected_output", "source")), "Invalid example text")
            ids.append(example["id"])
        require(len(ids) == len(set(ids)), "Duplicate example ID")
    if path == "resources.json":
        ids = []
        for item in obj["items"]:
            require(isinstance(item, dict) and isinstance(item.get("id"), str) and re.fullmatch(ID, item["id"]), "Invalid resource ID")
            require(all(isinstance(item.get(key), str) and item[key].strip() for key in ("title", "type", "purpose")), "Invalid resource description")
            require(item.get("status") in ("unknown", "available", "preparing", "ready", "unavailable"), "Invalid resource status")
            for key in ("source", "path", "location", "notes", "version"):
                require(key not in item or isinstance(item[key], str), "Invalid resource detail")
            if "checked_at" in item:
                timestamp(item["checked_at"])
            ids.append(item["id"])
        require(len(ids) == len(set(ids)), "Duplicate resource ID")
    if path == "workspace.json" and "presentation" in obj:
        presentation = obj["presentation"]
        require(isinstance(presentation, dict) and isinstance(presentation.get("id"), str)
                and bool(presentation["id"]) and presentation.get("panel") in ("goal", "resources"), "Invalid presentation request")
    if path == "project.json":
        require(type(obj["schema_version"]) is int and obj["schema_version"] == 1, "Unsupported schema_version")
    for key in ("revision", "goal_revision"):
        if key in obj:
            require(type(obj[key]) is int and obj[key] >= 1, f"Invalid {key}")
    for key in ("updated_at", "completed_at", "created_at"):
        if key in obj:
            timestamp(obj[key])
    if leaf in ("status.json", "result.json"):
        states = FINAL if leaf == "result.json" else (("pending", "running") if path.startswith("assessments/") else ("pending", "running", *FINAL))
        require(obj["state"] in states, "Invalid execution state")
    if leaf == "result.json":
        require(isinstance(obj["metrics"], dict), "metrics must be an object")
        require(all(type(v) in (int, float) and math.isfinite(v) for v in obj["metrics"].values()), "Metrics must be finite numbers")
    if leaf == "definition.json":
        require(isinstance(obj["metrics"], list), "metrics must be an array")
        metric_ids = []
        for item in obj["metrics"]:
            require(isinstance(item, dict) and isinstance(item.get("id"), str) and re.fullmatch(ID, item["id"]) and isinstance(item.get("label"), str) and item.get("direction") in ("maximize", "minimize"), "Invalid metric definition")
            metric_ids.append(item["id"])
        require(len(set(metric_ids)) == len(metric_ids), "Duplicate metric ID")
        if path.startswith("evaluation/versions/"):
            require(obj["version"] == path.split("/")[2], "Version does not match directory")
    if "disposition" in obj:
        require(obj["disposition"] in ("adopted", "deferred", "rejected", "question"), "Invalid disposition")
    for key in ("artifact_sha256", "evaluation_sha256", "target_sha256"):
        if obj.get(key) is not None:
            require(isinstance(obj[key], str) and SHA.fullmatch(obj[key]), f"Invalid {key}")
    if obj.get("target") is not None:
        parts(obj["target"])
        require(obj.get("target_sha256") is not None, "Target requires hash")
    if "execution" in obj:
        execution = obj["execution"]
        require(isinstance(execution, dict), "execution must be an object")
        if leaf == "config.json":
            require(isinstance(execution.get("argv"), list) and execution["argv"] and all(isinstance(v, str) and "\x00" not in v for v in execution["argv"]), "execution.argv must be argument array")
            if execution.get("cwd") != ".":
                parts(execution.get("cwd"))
            require(isinstance(execution.get("environment"), dict), "execution.environment must be an object")
            if "timeout_seconds" in execution:
                require(type(execution["timeout_seconds"]) in (int, float) and execution["timeout_seconds"] > 0, "Invalid timeout")
    if "fixed_inputs" in obj:
        fixed = obj["fixed_inputs"]
        require(isinstance(fixed, dict) and all(k in fixed for k in ("code", "data", "starting_artifact", "parameters", "environment")), "Incomplete fixed_inputs")
        require(isinstance(fixed["code"], list) and isinstance(fixed["data"], list) and isinstance(fixed["parameters"], dict) and isinstance(fixed["environment"], dict), "Invalid fixed_inputs")
        for item in fixed["code"] + fixed["data"] + ([fixed["starting_artifact"]] if fixed["starting_artifact"] is not None else []):
            require(isinstance(item, dict) and isinstance(item.get("sha256"), str) and SHA.fullmatch(item["sha256"]), "Fixed input requires SHA-256")
            require(bool(item.get("path")) != bool(item.get("location")), "Fixed input needs path or external location")
            if "path" in item:
                parts(item["path"])
    if leaf == "artifacts.json":
        ids = []
        for item in obj["items"]:
            require(isinstance(item, dict) and isinstance(item.get("id"), str) and re.fullmatch(ID, item["id"]), "Invalid artifact ID")
            parts(item.get("path"))
            require(isinstance(item.get("sha256"), str) and SHA.fullmatch(item["sha256"]), "Artifact requires hash")
            ids.append(item["id"])
        require(len(ids) == len(set(ids)), "Duplicate artifact ID")
    return obj


def mutable(path, old, tree):
    if path in ("project.json", "goal.json", "resources.json", "candidates.json", "review.md"):
        return True
    if path.startswith("evaluation/draft/") or re.fullmatch(rf"experiments/{ID}/analysis\.md", path):
        return True
    if path.endswith("/status.json"):
        if path.startswith("assessments/"):
            return not tree.exists(path.replace("status.json", "result.json"))
        return old.get("state") not in FINAL
    return False


def write(tree, path, source, create=False, expected=None):
    parts(path)
    require(bool(RECORD.fullmatch(path)), "Path is not a writable research record")
    require(".." not in os.fspath(source).split("/"), "Parent traversal is not allowed")
    source_path = Path(os.path.abspath(source))
    source_tree = Tree(source_path.parent)
    try:
        data = source_tree.read(source_path.name)
    finally:
        source_tree.close()
    obj = shape(path, data)
    with tree.locked():
        if create:
            require(not tree.exists(path), "Record already exists")
        else:
            require(isinstance(expected, str) and SHA.fullmatch(expected), "Expected SHA-256 required")
            previous = tree.read(path)
            old = shape(path, previous)
            require(mutable(path, old, tree), "Record is immutable")
            require(digest(previous) == expected, "Conflict: expected hash differs")
            history = None
            if path == "goal.json":
                require(obj["revision"] == old["revision"] + 1, "Goal revision must increase by one")
                history = f"history/goals/{old['revision']}.json"
            elif path == "review.md":
                history = f"history/reviews/{uuid.uuid4().hex}.md"
            elif path.endswith("/analysis.md"):
                history = f"history/analyses/{path.split('/')[1]}/{uuid.uuid4().hex}.md"
            if history:
                if tree.exists(history):
                    require(tree.read(history) == previous, "History conflict")
                else:
                    tree.publish(history, previous)
        tree.publish(path, data, replace=not create)
    return {"path": path, "sha256": digest(data)}


def freeze(tree, root, source, path):
    require(bool(re.fullmatch(rf"evaluation/versions/{ID}|experiments/{ID}/snapshot", path)), "Invalid freeze destination")
    require(".." not in os.fspath(source).split("/"), "Parent traversal is not allowed")
    source_path, destination = Path(os.path.abspath(source)), Path(os.path.abspath(root)) / path
    require(source_path != destination and source_path not in destination.parents and destination not in source_path.parents, "Source and destination overlap")
    source_tree = Tree(source_path)
    try:
        names = source_tree.files("")
        require(names and "manifest.json" not in names, "Source must be nonempty without manifest.json")
        payload = {name: source_tree.read(name, with_mode=True) for name in names}
        if path.startswith("evaluation/"):
            require("definition.json" in payload, "Evaluation definition missing")
            shape(path + "/definition.json", payload["definition.json"][0])
        with tree.locked():
            segments = parts(path)
            with tree.directory(segments[:-1], create=True) as parent:
                os.mkdir(segments[-1], dir_fd=parent)
            for name, (data, mode) in payload.items():
                tree.publish(path + "/" + name, data, mode=mode)
            manifest = {"files": [{"path": name, "sha256": digest(data)} for name, (data, _) in payload.items()]}
            tree.publish(path + "/manifest.json", encoded(manifest))
        return {"path": path, "files": len(payload), "manifest_sha256": digest(encoded(manifest))}
    finally:
        source_tree.close()


def validate(tree):
    report = {"errors": [], "warnings": [], "unfinished": [], "unhandled_feedback": []}
    docs = {}
    raw = {}
    def error(path, message):
        report["errors"].append(f"{path}: {message}")
    def check_hash(path, expected, label):
        require(isinstance(expected, str) and SHA.fullmatch(expected), f"Invalid hash for {label}")
        require(digest(tree.read(path)) == expected, f"Hash mismatch: {label}")
    names = [p for p in ("project.json", "goal.json", "resources.json", "candidates.json", "workspace.json", "review.md") if tree.exists(p)]
    for prefix in ("evaluation", "experiments", "assessments", "releases", "acceptance", "feedback"):
        if tree.exists(prefix):
            try:
                names.extend(tree.files(prefix))
            except (OSError, ValueError) as exc:
                error(prefix, str(exc))
    for path in names:
        if RECORD.fullmatch(path):
            try:
                raw[path] = tree.read(path)
                docs[path] = shape(path, raw[path])
            except (OSError, ValueError, TypeError) as exc:
                error(path, str(exc))
    for required in ("project.json", "goal.json", "resources.json", "candidates.json"):
        if required not in docs:
            error(required, "Missing or invalid core record")
    project = docs.get("project.json", {})
    current = project.get("current_evaluation")
    if current and f"evaluation/versions/{current}/definition.json" not in docs:
        error("project.json", "Current evaluation is missing or invalid")
    if tree.exists(".workspace/manifest.json"):
        try:
            manifest = strict(tree.read(".workspace/manifest.json"))
            require(type(manifest.get("schema_min")) is int and type(manifest.get("schema_max")) is int and manifest["schema_min"] <= project.get("schema_version", 0) <= manifest["schema_max"], "Incompatible kit schema range")
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            error(".workspace/manifest.json", str(exc))
    else:
        report["warnings"].append("Missing workspace manifest; format compatibility is not verified")
    for path in names:
        if path.endswith("/manifest.json") and (path.startswith("evaluation/versions/") or "/snapshot/" in path):
            try:
                manifest = strict(tree.read(path))
                base = path.rsplit("/", 1)[0]
                require(isinstance(manifest, dict) and isinstance(manifest.get("files"), list), "Invalid manifest")
                listed = []
                for item in manifest["files"]:
                    require(isinstance(item, dict), "Invalid manifest entry")
                    parts(item.get("path"))
                    require(item["path"] != "manifest.json", "Manifest cannot include itself")
                    target = base + "/" + item["path"]
                    check_hash(target, item.get("sha256"), target)
                    listed.append(target)
                require(len(listed) == len(set(listed)), "Duplicate manifest paths")
                require(set(tree.files(base)) == set(listed) | {path}, "Manifest file set differs")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                error(path, str(exc))
    for path, obj in docs.items():
        if path.startswith(("experiments/", "assessments/", "acceptance/")) and not path.endswith("/config.json"):
            if path.rsplit("/", 1)[0] + "/config.json" not in docs:
                error(path, "Orphan record: missing config")
        if not isinstance(obj, dict):
            continue
        try:
            if path.endswith("/definition.json") and path.startswith("evaluation/versions/") and not tree.exists(path.replace("definition.json", "manifest.json")):
                report["warnings"].append(f"{path}: legacy version has no content manifest")
            if path.endswith("/artifacts.json"):
                for artifact in obj["items"]:
                    check_hash(artifact["path"], artifact["sha256"], artifact["id"])
            if path.startswith("experiments/") and path.endswith("/config.json"):
                base = path.rsplit("/", 1)[0]
                status = docs.get(base + "/status.json", {})
                if status.get("state") not in FINAL:
                    report["unfinished"].append(base)
                if status.get("state") == "succeeded":
                    require(docs.get(base + "/artifacts.json", {}).get("items"), "Successful training requires artifacts")
                revision = obj["goal_revision"]
                if revision != docs.get("goal.json", {}).get("revision"):
                    old = shape("goal.json", tree.read(f"history/goals/{revision}.json"))
                    require(old["revision"] == revision, "Goal history revision differs")
                require(f"evaluation/versions/{obj['evaluation_version']}/definition.json" in docs, "Missing evaluation version")
                parent = obj.get("parent_experiment_id")
                if parent:
                    require(parent != obj["id"] and f"experiments/{parent}/config.json" in docs, "Invalid parent experiment")
                if "fixed_inputs" not in obj or "execution" not in obj:
                    report["warnings"].append(f"{path}: legacy record lacks fixed inputs/execution evidence")
                fixed = obj.get("fixed_inputs", {})
                for item in fixed.get("code", []) + fixed.get("data", []) + ([fixed["starting_artifact"]] if fixed.get("starting_artifact") else []):
                    if "path" in item:
                        check_hash(item["path"], item["sha256"], item["path"])
                    else:
                        report["warnings"].append(f"{path}: external input not verified: {item['location']}")
            if path.startswith(("assessments/", "releases/")) and (path.endswith("/config.json") or path.startswith("releases/")):
                experiment = obj["experiment_id"]
                require(f"experiments/{experiment}/config.json" in docs, "Missing experiment")
                artifacts = docs.get(f"experiments/{experiment}/artifacts.json", {}).get("items", [])
                artifact = next((a for a in artifacts if a["id"] == obj["artifact_id"]), None)
                require(artifact is not None, "Missing artifact")
                if "artifact_sha256" in obj:
                    require(obj["artifact_sha256"] == artifact["sha256"], "Artifact reference hash differs")
                else:
                    report["warnings"].append(f"{path}: artifact hash not pinned in record")
                if path.startswith("assessments/"):
                    definition = f"evaluation/versions/{obj['evaluation_version']}/definition.json"
                    require(definition in docs, "Missing evaluation")
                    if "evaluation_sha256" in obj:
                        check_hash(definition, obj["evaluation_sha256"], definition)
                    else:
                        report["warnings"].append(f"{path}: evaluation hash not pinned")
                    if "execution" not in obj:
                        report["warnings"].append(f"{path}: execution evidence missing")
                    base = path.rsplit("/", 1)[0]
                    result = docs.get(base + "/result.json")
                    if result is None:
                        report["unfinished"].append(base)
                    else:
                        metric_ids = {m["id"] for m in docs[definition]["metrics"]}
                        require(set(result["metrics"]) <= metric_ids, "Unknown metric IDs")
                        if result["state"] == "succeeded":
                            require(docs.get(base + "/outputs.jsonl"), "Successful assessment requires outputs")
                            require(set(result["metrics"]) == metric_ids, "Successful assessment requires all declared metrics")
                else:
                    for assessment in obj["assessment_ids"]:
                        record = docs.get(f"assessments/{assessment}/config.json", {})
                        require(record.get("experiment_id") == experiment and record.get("artifact_id") == obj["artifact_id"], "Release assessment does not match artifact")
            if path.startswith("acceptance/") and path.endswith("/config.json"):
                for release in obj["release_ids"]:
                    require(f"releases/{release}.json" in docs, "Missing release")
                require(path.replace("config.json", "outputs.jsonl") in docs, "Acceptance outputs missing")
            if path.startswith("feedback/"):
                if obj.get("target"):
                    if not tree.exists(obj["target"]) or digest(tree.read(obj["target"])) != obj.get("target_sha256"):
                        report["warnings"].append(f"{path}: stale feedback target")
                if path.startswith("feedback/responses/"):
                    require(f"feedback/requests/{obj['request_id']}.json" in docs, "Missing feedback request")
                if path.startswith("feedback/handled/"):
                    require(any(f"feedback/{kind}/{obj['feedback_id']}.json" in docs for kind in ("responses", "incoming")), "Missing original feedback")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            error(path, str(exc))
    for path, obj in docs.items():
        if path.startswith(("feedback/responses/", "feedback/incoming/")):
            handled = [h for p, h in docs.items() if p.startswith("feedback/handled/") and h.get("feedback_id") == obj["id"]]
            if not handled or len(handled) > 1 or handled[0]["disposition"] in ("deferred", "question"):
                report["unhandled_feedback"].append(obj["id"])
    report["valid"] = not report["errors"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("hash", "validate", "write", "freeze"):
        command = commands.add_parser(name)
        command.add_argument("--project", required=True)
        if name != "validate":
            command.add_argument("--path", required=True)
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
        elif args.command == "hash":
            result = {"path": args.path, "sha256": digest(tree.read(args.path))}
        elif args.command == "write":
            result = write(tree, args.path, args.input, args.create, args.expected_sha256)
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
