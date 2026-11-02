#!/usr/bin/env python3
"""Package explicit workspace inputs and prebuilt assets; bundle skills without running npm."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

VERSION = "0.3.0"
TEMPLATES = ("AGENTS.md", "research-contract.md", "project.json", "goal.json", "resources.json", "candidates.json", "workspace.json")
SKILLS = ("research-workspace", "tunetune-init", "build-evaluation", "train", "review")
SKILL_RESOURCES = {"references": {".md", ".json"}, "scripts": {".py"}}
EXCLUDED_SKILL_PARTS = {"evals", "notes", "reference", "__pycache__", "cache", "node_modules"}
ASSET_SUFFIXES = {".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf"}


def checked_file(path):
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise ValueError(f"Expected a regular non-symlink file: {path}")
    return path


def collect_skills(source):
    inputs = {}
    for relative in ("references/records.md", "references/tools.md", "scripts/records.py"):
        checked_file(source / "skills/research-workspace" / relative)
    for name in SKILLS:
        root = source / "skills" / name
        inputs[f"skills/{name}/SKILL.md"] = checked_file(root / "SKILL.md")
        for path in sorted(root.rglob("*")):
            # Reject links even in excluded trees; never follow them into other inputs.
            if path.is_symlink():
                raise ValueError(f"Skill symlink is not allowed: {path}")
            relative = path.relative_to(root)
            if (path.is_dir() or len(relative.parts) < 2
                    or any(part.startswith(".") or part in EXCLUDED_SKILL_PARTS for part in relative.parts)
                    or path.suffix not in SKILL_RESOURCES.get(relative.parts[0], set())):
                continue
            inputs[f"skills/{name}/{relative.as_posix()}"] = checked_file(path)
    return inputs


def build(source, output):
    source, output = Path(os.path.abspath(source)), Path(os.path.abspath(output))
    # The base skill owns the contract; there is no second template source to maintain.
    inputs = {f"template/{name}": checked_file(
        source / "skills/research-workspace/references/records.md" if name == "research-contract.md"
        else source / "templates/workspace" / name) for name in TEMPLATES}
    inputs["workspace/workspace.py"] = checked_file(source / "workspace/workspace.py")
    inputs["install-workspace.py"] = checked_file(source / "scripts/install-workspace.py")
    assets = source / "workspace/dist"
    checked_file(assets / "index.html")
    for path in sorted(assets.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Asset symlink is not allowed: {path}")
        if path.is_dir():
            continue
        checked_file(path)
        if path.suffix.lower() not in ASSET_SUFFIXES or any(part.startswith(".") for part in path.relative_to(assets).parts):
            raise ValueError(f"Unexpected built asset (sources and maps are not distributed): {path}")
        inputs["workspace/assets/" + path.relative_to(assets).as_posix()] = path
    skill_inputs = collect_skills(source)
    inputs.update(skill_inputs)
    name = f"workspace-kit-{VERSION}"
    targets = (output / name, output / f"{name}.tar.gz")
    for path in (output, *output.parents, *targets):
        if path.is_symlink():
            raise ValueError(f"Symlink output is not allowed: {path}")
    if any(path.exists() for path in targets):
        raise ValueError("Build outputs already exist; select a fresh --output directory")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".kit-build-", dir=output) as temporary:
        stage = Path(temporary)
        kit = stage / name
        for relative, path in inputs.items():
            destination = kit / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        manifest = {"version": VERSION, "schema_min": 1, "schema_max": 1,
                    "files": [{"path": relative, "sha256": hashlib.sha256((kit / relative).read_bytes()).hexdigest()}
                              for relative in sorted(inputs)]}
        (kit / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with tarfile.open(stage / f"{name}.tar.gz", "w:gz") as archive:
            archive.add(kit, arcname=name)
        # Output publication assumes one builder per output directory.
        kit.rename(targets[0])
        os.link(stage / f"{name}.tar.gz", targets[1])
    return targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1], help="Product source root")
    parser.add_argument("--output", type=Path, help="Defaults to <source>/dist; must not contain this version")
    args = parser.parse_args()
    try:
        outputs = build(args.source, args.output or args.source / "dist")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
