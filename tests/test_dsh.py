"""DeepSeek Harness bundle: package shape, published contents and the Node host tests."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins/tunetune/skills"
NODE = shutil.which("node")
NPM = shutil.which("npm")


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads((ROOT / "package.json").read_text())

    def test_package_declares_a_bundle_with_host_and_browser_halves(self):
        package = self.package
        self.assertEqual(package["name"], "dsh-tunetune")
        self.assertNotIn("private", package)
        self.assertEqual(package["dsh"]["bundle"], {"patch": "./dsh/cordis.patch.yml"})
        self.assertEqual(package["dsh"]["client"]["platform"], "web")
        self.assertRegex(package["engines"]["dsh"], r"^>=\S+ <\S+$")
        for target in (package["main"], package["icon"], *package["exports"].values()):
            if "*" not in target:
                self.assertTrue((ROOT / target).is_file(), target)
        for language in ("en", "zh"):
            meta = json.loads((ROOT / f"dsh/locale/{language}.json").read_text())["meta"]
            self.assertTrue(meta["title"] and meta["description"])
            expected_detail = "README_zh.md" if language == "zh" else "README.md"
            self.assertEqual(meta["detail"], expected_detail)
            self.assertTrue((ROOT / meta["detail"]).is_file())
            self.assertIn(meta["detail"], package["files"])
        patch = (ROOT / "dsh/cordis.patch.yml").read_text()
        self.assertIn("name: 'dsh-tunetune'", patch)
        # No dependencies means no install scripts and no build to allow on git installs.
        for field in ("dependencies", "peerDependencies", "optionalDependencies"):
            self.assertNotIn(field, package)
        self.assertFalse({"prepare", "preinstall", "install", "postinstall"} & set(package.get("scripts", {})))

    @unittest.skipUnless(NPM, "npm is not installed")
    def test_published_files_are_the_bundle_and_the_shipped_skills(self):
        result = subprocess.run([NPM, "pack", "--dry-run", "--json"], cwd=ROOT, capture_output=True, text=True, check=True)
        packed = {item["path"] for item in json.loads(result.stdout)[0]["files"]}
        skills = {path.relative_to(ROOT).as_posix() for path in SKILLS.rglob("*")
                  if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts}
        bundle = {path.relative_to(ROOT).as_posix() for path in (ROOT / "dsh").rglob("*") if path.is_file() and path.name != ".DS_Store"}
        self.assertEqual(packed, skills | bundle | {"package.json", "README.md", "README_zh.md", "INSTALL.md", "LICENSE", "NOTICE"})

    @unittest.skipUnless(NODE, "Node.js is not installed")
    def test_node_host_suite(self):
        tests = sorted(str(path) for path in (ROOT / "tests/dsh").glob("*.test.mjs"))
        self.assertTrue(tests)
        result = subprocess.run([NODE, "--test", *tests], cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
