#!/usr/bin/env python3
"""Install a verified local workspace kit without replacing existing research."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

VERSION = "0.3.0"
TEMPLATES = ("AGENTS.md", "research-contract.md", "project.json", "goal.json", "resources.json", "candidates.json", "workspace.json")
BUSINESS_DIRS = ("data", "src", "evaluation", "experiments", "assessments", "releases", "acceptance", "feedback", "history", ".workspace")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_object(data, label):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key in {label}: {key}")
            result[key] = value
        return result
    obj = json.loads(data, object_pairs_hook=unique,
                     parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {value}")))
    if not isinstance(obj, dict):
        raise ValueError(f"{label} must be a JSON object")
    return obj


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError(f"Unsafe manifest path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"Unsafe manifest path: {value!r}")
    return path


def no_symlinks(path):
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f"Symlinks are not supported: {item}")


def validate_business(name, data):
    obj = json_object(data, name)
    if name == "project.json":
        valid = (type(obj.get("schema_version")) is int and obj["schema_version"] == 1
                 and isinstance(obj.get("name"), str) and bool(obj["name"].strip())
                 and isinstance(obj.get("language"), str) and bool(obj["language"].strip())
                 and "current_evaluation" in obj
                 and (obj["current_evaluation"] is None or isinstance(obj["current_evaluation"], str)))
    elif name == "goal.json":
        valid = (type(obj.get("revision")) is int and obj["revision"] >= 1
                 and isinstance(obj.get("summary"), str)
                 and all(isinstance(obj.get(key), list) for key in ("examples", "sections")))
    elif name in ("resources.json", "candidates.json"):
        valid = isinstance(obj.get("items"), list) and all(isinstance(item, dict) for item in obj["items"])
    else:
        valid = isinstance(obj.get("title"), str) and isinstance(obj.get("metric_columns"), list)
    if not valid:
        raise ValueError(f"Conflicting or unsupported research file: {name}")
    return obj


def verify_kit(kit):
    no_symlinks(kit)
    if not kit.is_dir():
        raise ValueError("--kit must be an extracted local kit directory")
    manifest_path = kit / "manifest.json"
    no_symlinks(manifest_path)
    if not manifest_path.is_file() or not stat.S_ISREG(manifest_path.stat().st_mode):
        raise ValueError("Kit manifest must be a regular file")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json_object(manifest_bytes, "manifest.json")
    if (manifest.get("version") != VERSION or type(manifest.get("schema_min")) is not int
            or type(manifest.get("schema_max")) is not int
            or not manifest["schema_min"] <= 1 <= manifest["schema_max"]):
        raise ValueError("Unsupported kit version or schema range")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("Manifest files must be a list of {path, sha256}")
    payload = {}
    folded = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError("Invalid manifest file entry")
        relative = str(safe_path(entry["path"]))
        if relative.casefold() in folded:
            raise ValueError(f"Duplicate manifest path: {relative}")
        folded.add(relative.casefold())
        allowed = (relative in {f"template/{name}" for name in TEMPLATES}
                   or relative in ("workspace/workspace.py", "install-workspace.py")
                   or relative.startswith("workspace/assets/")
                   or (relative.startswith("skills/") and len(PurePosixPath(relative).parts) >= 3
                       and PurePosixPath(relative).parts[1] in ("research-workspace", "tunetune-init", "build-evaluation", "train", "review")))
        if not allowed or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"Unexpected manifest file: {relative}")
        file = kit / relative
        no_symlinks(file)
        if not file.is_file() or not stat.S_ISREG(file.stat().st_mode):
            raise ValueError(f"Not a regular kit file: {relative}")
        data = file.read_bytes()
        if digest(data) != entry["sha256"]:
            raise ValueError(f"Hash mismatch: {relative}")
        payload[relative] = data
    required = {f"template/{name}" for name in TEMPLATES} | {"workspace/workspace.py", "workspace/assets/index.html", "install-workspace.py"}
    required |= {f"skills/{name}/SKILL.md" for name in ("research-workspace", "tunetune-init", "build-evaluation", "train", "review")}
    required |= {"skills/research-workspace/" + path for path in
                 ("references/records.md", "references/tools.md", "scripts/records.py")}
    if not required <= payload.keys():
        raise ValueError("Kit is missing required files")
    expected = set(payload) | {"manifest.json"}
    directories = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != "."}
    for path in kit.rglob("*"):
        no_symlinks(path)
        relative = path.relative_to(kit).as_posix()
        if path.is_dir() and relative in directories:
            continue
        if not path.is_file() or relative not in expected:
            raise ValueError(f"Unexpected kit entry: {relative}")
    for name in TEMPLATES:
        if name.endswith(".json"):
            validate_business(name, payload[f"template/{name}"])
    return manifest, manifest_bytes, payload


def install(kit, project, name=None, host="agents"):
    if host not in ("agents", "claude"):
        raise ValueError("Unsupported skill host")
    kit, project = Path(os.path.abspath(kit)), Path(os.path.abspath(project))
    manifest, manifest_bytes, payload = verify_kit(kit)
    no_symlinks(project)
    if project == kit or kit in project.parents or project in kit.parents:
        raise ValueError("Project and kit directories must not overlap")
    if name is not None and not name.strip():
        raise ValueError("Project name must not be empty")
    if project.exists() and not project.is_dir():
        raise ValueError("Project path is not a directory")
    for legacy_name in (".workbench", "workbench.json"):
        legacy = project / legacy_name
        if legacy.exists() or legacy.is_symlink():
            raise ValueError("Legacy workbench layout detected; automatic migration is not supported")
    for directory in BUSINESS_DIRS:
        path = project / directory
        no_symlinks(path)
        if path.exists() and not path.is_dir():
            raise ValueError(f"Conflicting business directory: {path}")
    planned = {}
    for template in TEMPLATES:
        path = project / template
        no_symlinks(path)
        if path.exists():
            if not path.is_file():
                raise ValueError(f"Conflicting template path: {path}")
            if template.endswith(".json"):
                validate_business(template, path.read_bytes())
            continue
        data = payload[f"template/{template}"]
        if template == "project.json" and name is not None:
            obj = json_object(data, template)
            obj["name"] = name
            data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        planned[template] = data
    installed_manifest = project / ".workspace/manifest.json"
    no_symlinks(installed_manifest)
    if installed_manifest.exists():
        if not installed_manifest.is_file() or json_object(installed_manifest.read_bytes(), str(installed_manifest)) != manifest:
            raise ValueError("Installed workspace differs; upgrades are not supported")
    app_payload = {".workspace/app/" + key.removeprefix("workspace/"): data
                   for key, data in payload.items() if key.startswith("workspace/")}
    skill_root = ".agents/skills" if host == "agents" else ".claude/skills"
    skill_payload = {skill_root + "/" + key.removeprefix("skills/"): data
                     for key, data in payload.items() if key.startswith("skills/")}
    app = project / ".workspace/app"
    no_symlinks(app)
    if app.exists():
        if not app.is_dir():
            raise ValueError("Conflicting workspace app path")
        allowed_dirs = {str(parent) for key in app_payload for parent in PurePosixPath(key).parents}
        for path in app.rglob("*"):
            no_symlinks(path)
            relative = path.relative_to(project).as_posix()
            if path.is_dir() and relative in allowed_dirs:
                continue
            if not path.is_file() or relative not in app_payload or path.read_bytes() != app_payload[relative]:
                raise ValueError(f"Installed app differs: {relative}; upgrades are not supported")
    for relative, data in {**app_payload, **skill_payload}.items():
        path = project / relative
        no_symlinks(path)
        if path.exists():
            if not path.is_file() or path.read_bytes() != data:
                raise ValueError(f"Conflicting app file: {path}")
        else:
            planned[relative] = data
    if not installed_manifest.exists():
        planned[".workspace/manifest.json"] = manifest_bytes
    # Check every parent before any writes, including directories occupied by files.
    for relative in planned:
        for parent in (project / relative).parents:
            no_symlinks(parent)
            if parent.exists() and not parent.is_dir():
                raise ValueError(f"File occupies required directory: {parent}")
    if not planned:
        for directory in BUSINESS_DIRS:
            (project / directory).mkdir(parents=True, exist_ok=True)
        return 0
    ancestor = project.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    # Exclusive hard-link publication cannot overwrite files created after preflight.
    with tempfile.TemporaryDirectory(prefix=".workspace-install-", dir=ancestor) as temporary:
        staged = Path(temporary)
        for index, data in enumerate(planned.values()):
            (staged / str(index)).write_bytes(data)
        published = []
        try:
            for index, relative in enumerate(planned):
                destination = project / relative
                no_symlinks(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = staged / str(index)
                os.link(source, destination)
                published.append((destination, source.stat().st_ino, planned[relative]))
        except (OSError, ValueError):
            for destination, inode, original in reversed(published):
                if (destination.is_file() and not destination.is_symlink()
                        and destination.stat().st_ino == inode and destination.read_bytes() == original):
                    destination.unlink()
            raise
    for directory in BUSINESS_DIRS:
        (project / directory).mkdir(parents=True, exist_ok=True)
    return len(planned)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--name")
    parser.add_argument("--host", choices=("agents", "claude"), default="agents")
    args = parser.parse_args()
    try:
        count = install(args.kit, args.project, args.name, args.host)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Installation refused: {error}\n")
    print(f"Installed {count} missing files in {args.project.absolute()}")
    print("Start from the project: python3 .workspace/app/workspace.py --project . --port 0")


if __name__ == "__main__":
    main()
