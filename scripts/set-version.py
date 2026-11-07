#!/usr/bin/env python3
"""Set the release version: package.json is the source, every shipped copy follows from it.

The npm package, both plugin manifests and the distributed tools each need their own copy:
installers read their own manifest, and the tools are copied alone into every study, where
their pinned version identifies the tools that study was made with. This writes them all,
then rebuilds the skill manifest; check-release.py verifies that they agree.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "plugins/tunetune/skills/research-workspace/scripts"
SEMVER = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?"
JSON_FILES = ("package.json", "plugins/tunetune/.claude-plugin/plugin.json", "plugins/tunetune/.codex-plugin/plugin.json")
# (file, pattern with one group around the version)
TEXT_FILES = (
    (TOOLS / "init.py", rf'^(VERSION = "){SEMVER}(")$'),
    (TOOLS / "records.py", rf'^(VERSION = "){SEMVER}(")$'),
    (TOOLS / "resources.py", rf'("User-Agent": "TuneTune/){SEMVER}(")'),
)


def set_json(path, version):
    text = path.read_text(encoding="utf-8")
    # Replace only the top-level field so formatting and key order stay as written.
    updated, count = re.subn(rf'^(  "version": "){SEMVER}(")', rf"\g<1>{version}\g<2>", text, count=1, flags=re.M)
    if count != 1 or json.loads(updated)["version"] != version:
        raise SystemExit(f"Could not find the top-level version in {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")


def set_text(path, pattern, version):
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, rf"\g<1>{version}\g<2>", text, count=1, flags=re.M)
    if count != 1:
        raise SystemExit(f"Could not find the version in {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="semantic version such as 0.8.2 or 0.9.0-rc.1")
    version = parser.parse_args().version.removeprefix("v")
    if not re.fullmatch(SEMVER, version):
        parser.error(f"not a semantic version: {version}")
    for relative in JSON_FILES:
        set_json(ROOT / relative, version)
    for path, pattern in TEXT_FILES:
        set_text(path, pattern, version)
    # The manifest pins the tools' bytes, so it must follow the files just written.
    subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build-skills.py")], check=True, stdout=subprocess.DEVNULL)
    print(f"Version set to {version}; run the tests, then python3 scripts/check-release.py --tag v{version}")


if __name__ == "__main__":
    main()
