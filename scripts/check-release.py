#!/usr/bin/env python3
"""Check that every shipped version, license and manifest agrees before a release is published."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "plugins/tunetune/skills"
LICENSE_ID = "Apache-2.0"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def python_version(relative):
    match = re.search(r'^VERSION = "([^"]+)"$', (ROOT / relative).read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def versions():
    """Every place a release number lives; each must be bumped together."""
    lock = read_json("workspace/package-lock.json")
    found = {
        "package.json": read_json("package.json")["version"],
        "workspace/package.json": read_json("workspace/package.json")["version"],
        "workspace/package-lock.json": lock["version"],
        "workspace/package-lock.json (root package)": lock["packages"][""]["version"],
        "plugins/tunetune/.claude-plugin/plugin.json": read_json("plugins/tunetune/.claude-plugin/plugin.json")["version"],
        "plugins/tunetune/.codex-plugin/plugin.json": read_json("plugins/tunetune/.codex-plugin/plugin.json")["version"],
        "plugins/tunetune/skills/research-workspace/manifest.json": read_json(
            "plugins/tunetune/skills/research-workspace/manifest.json")["version"],
    }
    for relative in ("scripts/build-skills.py",
                     "plugins/tunetune/skills/research-workspace/scripts/init.py",
                     "plugins/tunetune/skills/research-workspace/scripts/records.py"):
        found[relative] = python_version(relative)
    agent = re.search(r'TuneTune/([0-9][^"\s]*)', (SKILLS_DIR / "research-workspace/scripts/resources.py").read_text(encoding="utf-8"))
    found["research-workspace/scripts/resources.py (User-Agent)"] = agent.group(1) if agent else None
    return found


def problems(tag=None):
    found = versions()
    expected = found["package.json"]
    if tag is not None:
        if not tag.startswith("v"):
            return [f"Release tags look like v{expected}, not {tag}"]
        expected = tag[1:]
    issues = [f"{where}: version {value}, expected {expected}" for where, value in found.items() if value != expected]
    if not re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?", expected):
        issues.append(f"Not a semantic version: {expected}")

    license_text = (ROOT / "LICENSE").read_bytes() if (ROOT / "LICENSE").is_file() else b""
    if b"Apache License" not in license_text or b"Version 2.0" not in license_text:
        issues.append("LICENSE is missing or is not the Apache License 2.0")
    for relative in ("package.json", "plugins/tunetune/.claude-plugin/plugin.json", "plugins/tunetune/.codex-plugin/plugin.json"):
        if read_json(relative).get("license") != LICENSE_ID:
            issues.append(f"{relative}: license must be {LICENSE_ID}")
    builder = load("build_skills", ROOT / "scripts/build-skills.py")
    for name in builder.SKILLS:
        skill = SKILLS_DIR / name
        # Skill installers copy only the skill folder, so each one carries the full terms.
        if not (skill / "LICENSE.txt").is_file() or (skill / "LICENSE.txt").read_bytes() != license_text:
            issues.append(f"{name}/LICENSE.txt must be an exact copy of LICENSE")
        head = (skill / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
        if not re.search(rf"^license: {re.escape(LICENSE_ID)}\b", head, re.M):
            issues.append(f"{name}/SKILL.md: frontmatter must declare license: {LICENSE_ID}")
    if not builder.check(ROOT):
        issues.append("Skill manifest is stale; build the panel, then run scripts/build-skills.py")
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Release tag such as v0.7.0; every version must equal it")
    parser.add_argument("--print-version", action="store_true", help="Print the agreed version after checking")
    args = parser.parse_args()
    issues = problems(args.tag)
    if issues:
        parser.exit(1, "Release check failed:\n" + "".join(f"- {issue}\n" for issue in issues))
    print(versions()["package.json"] if args.print_version else "Release check passed")


if __name__ == "__main__":
    main()
