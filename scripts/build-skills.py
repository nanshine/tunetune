#!/usr/bin/env python3
"""Pin the shared skill's distributed tools and prebuilt panel in its manifest; never runs npm."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

VERSION = "0.7.1"
TEMPLATES = ("AGENTS.md", "project.json", "proposal.json", "resources.json")
SKILLS_DIR = "plugins/tunetune/skills"
SKILLS = ("research-workspace", "tunetune-init", "build-evaluation", "run-experiments")
APP_SCRIPTS = ("workspace.py", "monitor.py", "records.py", "run.py", "resources.py", "scout.py")
SHARED = ("references/records.md", "references/tools.md", "scripts/init.py")
ASSET_SUFFIXES = {".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf"}


def checked_file(path):
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise ValueError(f"Expected a regular non-symlink file: {path}")
    return path


def collect(source):
    """Return the manifest payload; every skill installer copies these files verbatim."""
    skills = source / SKILLS_DIR
    for name in SKILLS:
        checked_file(skills / name / "SKILL.md")
        for path in (skills / name).rglob("*"):
            # Installers copy whole skill folders, so a link could ship content from anywhere.
            if path.is_symlink():
                raise ValueError(f"Skill symlink is not allowed: {path}")
    shared = skills / "research-workspace"
    for relative in SHARED:
        checked_file(shared / relative)
    inputs = {f"scripts/{name}": checked_file(shared / "scripts" / name) for name in APP_SCRIPTS}
    templates = shared / "assets/templates"
    present = {path.name for path in templates.iterdir()} if templates.is_dir() else set()
    if present != set(TEMPLATES):
        raise ValueError(f"Templates must be exactly {', '.join(TEMPLATES)}: {templates}")
    inputs.update({f"assets/templates/{name}": checked_file(templates / name) for name in TEMPLATES})
    panel = shared / "assets/panel"
    checked_file(panel / "index.html")
    for path in sorted(panel.rglob("*")):
        if path.is_dir():
            continue
        checked_file(path)
        if path.suffix.lower() not in ASSET_SUFFIXES or any(part.startswith(".") for part in path.relative_to(panel).parts):
            raise ValueError(f"Unexpected built asset (sources and maps are not distributed): {path}")
        inputs["assets/panel/" + path.relative_to(panel).as_posix()] = path
    return inputs


def manifest_bytes(source):
    inputs = collect(source)
    manifest = {"version": VERSION,
                "files": [{"path": relative, "sha256": hashlib.sha256(inputs[relative].read_bytes()).hexdigest()}
                          for relative in sorted(inputs)]}
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build(source):
    source = Path(os.path.abspath(source))
    target = source / SKILLS_DIR / "research-workspace/manifest.json"
    data = manifest_bytes(source)
    if target.is_symlink():
        raise ValueError(f"Symlink output is not allowed: {target}")
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".manifest-", delete=False) as stream:
        stream.write(data)
    os.replace(stream.name, target)
    return target


def check(source):
    target = Path(os.path.abspath(source)) / SKILLS_DIR / "research-workspace/manifest.json"
    return target.is_file() and not target.is_symlink() and target.read_bytes() == manifest_bytes(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1], help="Product source root")
    parser.add_argument("--check", action="store_true", help="Exit 1 when the committed manifest is stale")
    args = parser.parse_args()
    try:
        if args.check:
            if not check(args.source):
                parser.exit(1, "Skill manifest is stale; build the panel, then run scripts/build-skills.py\n")
            print("Skill manifest is current")
        else:
            print(build(args.source))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
