#!/usr/bin/env python3
"""Initialize a research project from this installed skill without replacing existing research."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile

VERSION = "0.7.0"
TEMPLATES = ("AGENTS.md", "project.json", "proposal.json", "resources.json")
APP_SCRIPTS = ("workspace.py", "monitor.py", "records.py", "run.py", "resources.py", "scout.py")
# Skill installers may reach the skill through a link; payload checks start at its real directory.
SKILL = Path(os.path.realpath(__file__)).parents[1]


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


def no_symlinks(path, root=None):
    for item in (path, *path.parents):
        if root is not None and item == root:
            return
        if item.is_symlink():
            raise ValueError(f"Symlinks are not supported: {item}")


def validate_business(name, data):
    # One canonical schema serves both initialization and research writes.
    source = Path(os.path.realpath(__file__)).with_name("records.py")
    if not source.is_file():
        raise ValueError("Missing canonical record validator")
    spec = importlib.util.spec_from_file_location("init_records", source)
    records = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(records)
    finally:
        sys.dont_write_bytecode = previous
    obj = records.shape(name, data)
    if name == "project.json" and not all(obj[key].strip() for key in ("name", "language")):
        raise ValueError("Project name and language must not be empty")
    if name == "resources.json" and any(not item[key].strip() for item in obj["items"] for key in ("title", "type")):
        raise ValueError("Resource title and type must not be empty")
    return obj


def project_path(relative):
    """Map a skill payload path to its pinned location in the project."""
    parts = PurePosixPath(relative).parts
    if parts[0] == "scripts":
        return ".workspace/app/" + parts[1]
    if parts[1] == "panel":
        return ".workspace/app/assets/" + "/".join(parts[2:])
    return parts[2]


def verify_skill(skill=SKILL):
    skill = Path(os.path.realpath(skill))
    if not skill.is_dir():
        raise ValueError("Skill directory is missing")
    manifest_path = skill / "manifest.json"
    no_symlinks(manifest_path, skill)
    if not manifest_path.is_file() or not stat.S_ISREG(manifest_path.stat().st_mode):
        raise ValueError("Skill manifest must be a regular file")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json_object(manifest_bytes, "manifest.json")
    if (manifest.get("version") != VERSION or type(manifest.get("schema_min")) is not int
            or type(manifest.get("schema_max")) is not int
            or manifest["schema_min"] != 4 or manifest["schema_max"] != 4):
        raise ValueError(f"Unsupported tool version or schema range; tools {VERSION} require schema 4 only")
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
        parts = PurePosixPath(relative).parts
        allowed = (relative in {f"scripts/{name}" for name in APP_SCRIPTS}
                   or relative in {f"assets/templates/{name}" for name in TEMPLATES}
                   or (len(parts) >= 3 and parts[:2] == ("assets", "panel")))
        if not allowed or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"Unexpected manifest file: {relative}")
        file = skill / relative
        no_symlinks(file, skill)
        if not file.is_file() or not stat.S_ISREG(file.stat().st_mode):
            raise ValueError(f"Not a regular skill file: {relative}")
        data = file.read_bytes()
        if digest(data) != entry["sha256"]:
            raise ValueError(f"Hash mismatch: {relative}")
        payload[relative] = data
    required = {f"scripts/{name}" for name in APP_SCRIPTS} | {f"assets/templates/{name}" for name in TEMPLATES}
    required.add("assets/panel/index.html")
    if not required <= payload.keys():
        raise ValueError("Skill is missing required files")
    # Leftovers from another build would be served or copied without a hash, so refuse them.
    for directory in ("assets/panel", "assets/templates"):
        for path in (skill / directory).rglob("*"):
            no_symlinks(path, skill)
            relative = path.relative_to(skill).as_posix()
            if not path.is_dir() and relative not in payload:
                raise ValueError(f"Unexpected skill asset: {relative}")
    for name in TEMPLATES:
        if name.endswith(".json"):
            validate_business(name, payload[f"assets/templates/{name}"])
    return manifest, manifest_bytes, payload


def install(project, name=None, skill=SKILL):
    skill, project = Path(os.path.realpath(skill)), Path(os.path.abspath(project))
    manifest, manifest_bytes, payload = verify_skill(skill)
    no_symlinks(project)
    if project == skill or skill in project.parents or project in skill.parents:
        raise ValueError("Project and skill directories must not overlap")
    if name is not None and not name.strip():
        raise ValueError("Project name must not be empty")
    if project.exists() and not project.is_dir():
        raise ValueError("Project path is not a directory")
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
        data = payload[f"assets/templates/{template}"]
        if template == "project.json" and name is not None:
            obj = json_object(data, template)
            obj["name"] = name
            data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        planned[template] = data
    installed_manifest = project / ".workspace/manifest.json"
    no_symlinks(installed_manifest)
    if installed_manifest.exists():
        if not installed_manifest.is_file() or json_object(installed_manifest.read_bytes(), str(installed_manifest)) != manifest:
            raise ValueError("Project tools differ from this skill; upgrades are not supported")
    app_payload = {project_path(key): data for key, data in payload.items() if not key.startswith("assets/templates/")}
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
    for relative, data in app_payload.items():
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
    return len(planned)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--name")
    args = parser.parse_args()
    try:
        count = install(args.project, args.name)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Initialization refused: {error}\n")
    project = Path(os.path.abspath(args.project))
    print(f"Added {count} missing files in {project}" if count else f"Project already initialized: {project}")
    print(f"Research tools: {project / '.workspace/app'}")
    print(f"Panel: python3 {project / '.workspace/app/workspace.py'} --project {project} --port 0 --open")


if __name__ == "__main__":
    main()
