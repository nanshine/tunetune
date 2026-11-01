"""Distribution checks use a tiny static fixture, not npm or a frontend build."""
import hashlib
import importlib.util
import json
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("build-kit")
installer = load_script("install-workspace")


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        self.source.mkdir()
        for directory in ("templates/workspace", "skills"):
            shutil.copytree(ROOT / directory, self.source / directory)
        (self.source / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/install-workspace.py", self.source / "scripts/install-workspace.py")
        (self.source / "workspace/dist").mkdir(parents=True)
        shutil.copyfile(ROOT / "workspace/workspace.py", self.source / "workspace/workspace.py")
        (self.source / "workspace/dist/index.html").write_text("<!doctype html><title>isolated kit fixture</title>", encoding="utf-8")
        (self.source / "workspace/dist/assets").mkdir()
        (self.source / "workspace/dist/assets/app.js").write_text("console.log('fixture');", encoding="utf-8")
        for directory in ("design", "reference", "workspace/src", "workspace/node_modules"):
            (self.source / directory).mkdir(parents=True, exist_ok=True)
            (self.source / directory / "DO_NOT_SHIP.txt").write_text("private source fixture")
        self.output = self.base / "dist"
        self.kit, self.archive, self.skills_archive = builder.build(self.source, self.output)
        self.project = self.base / "research"

    def rewrite_manifest(self, change):
        path = self.kit / "manifest.json"
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))

    def install(self, **kwargs):
        return installer.install(self.kit, self.project, **kwargs)

    def snapshot(self, directory):
        return {path.relative_to(directory).as_posix(): path.read_bytes()
                for path in directory.rglob("*") if path.is_file()}

    def test_explicit_isolated_package_and_hashes(self):
        manifest, _, payload = installer.verify_kit(self.kit)
        self.assertEqual((manifest["version"], manifest["schema_min"], manifest["schema_max"]), ("0.2.0", 1, 1))
        self.assertEqual(set(payload), {f"template/{name}" for name in installer.TEMPLATES}
                         | {"install-workspace.py", "workspace/workspace.py", "workspace/assets/index.html", "workspace/assets/assets/app.js"})
        for entry in manifest["files"]:
            self.assertEqual(entry["sha256"], hashlib.sha256((self.kit / entry["path"]).read_bytes()).hexdigest())
        with tarfile.open(self.archive) as archive:
            names = archive.getnames()
            self.assertIn("workspace-kit-0.2.0/install-workspace.py", names)
            self.assertFalse(any(any(part in name.split("/") for part in ("design", "reference", "src", "node_modules", "skills")) for name in names))
        with tarfile.open(self.skills_archive) as archive:
            self.assertEqual(set(archive.getnames()), {f"skills/{name}/SKILL.md" for name in builder.SKILLS})
            for member in archive.getmembers():
                content = archive.extractfile(member).read().decode()
                self.assertIn(f"name: {member.name.split('/')[1]}\n", content)
                self.assertIn("description:", content)

    def test_minimal_install(self):
        self.assertGreater(self.install(name="实际研究"), 0)
        self.assertEqual(json.loads((self.project / "project.json").read_text())["name"], "实际研究")
        self.assertEqual({path.name for path in self.project.iterdir()}, set(installer.TEMPLATES) | {".workspace"})
        self.assertFalse((self.project / ".workspace/runtime").exists())
        self.assertFalse((self.project / "skills").exists())
        self.assertEqual((self.project / ".workspace/app/workspace.py").read_bytes(), (self.kit / "workspace/workspace.py").read_bytes())

    def test_template_defaults(self):
        self.install()
        expected = {
            "project.json": {"schema_version": 1, "name": "未命名研究", "language": "zh-CN", "current_evaluation": None},
            "goal.json": {"revision": 1, "context": "", "expected_result": "", "examples": [], "sources": []},
            "resources.json": {"items": []}, "candidates.json": {"items": []},
            "workspace.json": {"title": "研究空间", "metric_columns": []},
        }
        for name, value in expected.items():
            self.assertEqual(json.loads((self.project / name).read_text()), value)

    def test_repeated_install_preserves_edits_and_feedback(self):
        self.install(name="原名称")
        goal = self.project / "goal.json"
        value = json.loads(goal.read_text())
        value["context"] = "用户已经编辑"
        goal.write_text(json.dumps(value, ensure_ascii=False))
        (self.project / "AGENTS.md").write_text("Existing project instructions")
        (self.project / "feedback/incoming").mkdir(parents=True)
        (self.project / "feedback/incoming/f1.json").write_text('{"id":"f1","text":"原话"}')
        before = self.snapshot(self.project)
        self.assertEqual(self.install(name="不得更名"), 0)
        self.assertEqual(before, self.snapshot(self.project))

    def test_existing_engineering_project_is_preserved(self):
        self.project.mkdir()
        (self.project / "train.py").write_text("# existing business code")
        (self.project / "AGENTS.md").write_text("Do not overwrite these instructions")
        before = self.snapshot(self.project)
        self.install()
        for name, data in before.items():
            self.assertEqual((self.project / name).read_bytes(), data)

    def test_legacy_layout_is_refused_before_writes(self):
        for name, kind in ((".workbench", "directory"), ("workbench.json", "file"),
                           (".workbench", "symlink")):
            with self.subTest(name=name, kind=kind):
                project = self.base / f"legacy-{kind}"
                project.mkdir()
                legacy = project / name
                if kind == "directory":
                    legacy.mkdir()
                    (legacy / "manifest.json").write_text('{"version":"0.1.0"}')
                elif kind == "file":
                    legacy.write_text('{"title":"已有展示配置","metric_columns":[]}')
                else:
                    legacy.symlink_to(self.base / "missing")
                before = self.snapshot(project)
                with self.assertRaisesRegex(ValueError, "automatic migration is not supported"):
                    installer.install(self.kit, project)
                self.assertEqual(before, self.snapshot(project))
                self.assertEqual({path.name for path in project.iterdir()}, {name})

    def test_workspace_settings_are_preserved(self):
        self.install()
        settings = self.project / "workspace.json"
        data = '{"title":"我的研究空间","metric_columns":["accuracy"]}'
        settings.write_text(data)
        self.assertEqual(self.install(), 0)
        self.assertEqual(settings.read_text(), data)

    def test_only_missing_files_are_repaired(self):
        self.install()
        (self.project / "resources.json").unlink()
        (self.project / ".workspace/app/assets/index.html").unlink()
        self.assertEqual(self.install(), 2)
        self.assertEqual(self.install(), 0)

    def test_late_collision_never_overwrites_another_writer(self):
        real_link = installer.os.link

        def collide(source, destination):
            if destination.name == "goal.json":
                destination.write_text("concurrent writer data")
            real_link(source, destination)

        with patch.object(installer.os, "link", side_effect=collide):
            with self.assertRaises(FileExistsError):
                self.install()
        self.assertEqual(self.snapshot(self.project), {"goal.json": b"concurrent writer data"})

    def test_hash_tampering_is_refused_before_writes(self):
        (self.kit / "workspace/assets/index.html").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            self.install()
        self.assertFalse(self.project.exists())

    def test_extra_kit_files_and_directories_are_refused(self):
        for name, directory in (("unexpected.txt", False), ("unexpected-directory", True)):
            with self.subTest(name=name):
                path = self.kit / name
                path.mkdir() if directory else path.write_text("unexpected")
                with self.assertRaisesRegex(ValueError, "Unexpected kit entry"):
                    self.install()
                path.rmdir() if directory else path.unlink()
        self.assertFalse(self.project.exists())

    def test_manifest_traversal_and_absolute_paths_are_refused(self):
        original = (self.kit / "manifest.json").read_bytes()
        for path in ("../escape", "/tmp/escape", "workspace/../escape", "workspace//assets/x", "./x", "C:/escape", "workspace\\escape"):
            with self.subTest(path=path):
                (self.kit / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest["files"].append({"path": path, "sha256": "0" * 64}))
                with self.assertRaisesRegex(ValueError, "Unsafe manifest path"):
                    self.install()
        self.assertFalse(self.project.exists())

    def test_duplicate_and_missing_manifest_entries_are_refused(self):
        original = (self.kit / "manifest.json").read_bytes()
        self.rewrite_manifest(lambda manifest: manifest["files"].append(manifest["files"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate manifest"):
            self.install()
        (self.kit / "manifest.json").write_bytes(original)
        self.rewrite_manifest(lambda manifest: manifest.update(files=[]))
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.install()

    def test_symlink_payload_is_refused(self):
        path = self.kit / "workspace/assets/index.html"
        external = self.base / "outside.html"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()
        self.assertFalse(self.project.exists())

    def test_symlink_destination_and_parent_are_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        self.project.mkdir()
        (self.project / ".workspace").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])
        (self.project / ".workspace").unlink()
        (self.project / "goal.json").symlink_to(outside / "goal.json")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()

    def test_malformed_or_conflicting_business_files_are_refused(self):
        self.project.mkdir()
        cases = [("project.json", "[]"), ("project.json", "not json"),
                 ("project.json", '{"schema_version":99}'), ("project.json", '{"schema_version":1,"schema_version":1}'),
                 ("goal.json", '{"unrelated":true}'), ("resources.json", '{"items":"business data"}'),
                 ("candidates.json", '{"items":[1]}'), ("workspace.json", '{"title":42}')]
        for name, data in cases:
            with self.subTest(name=name, data=data):
                path = self.project / name
                path.write_text(data)
                before = self.snapshot(self.project)
                with self.assertRaises(ValueError):
                    self.install()
                self.assertEqual(before, self.snapshot(self.project))
                path.unlink()

    def test_business_directory_collision_is_preflighted(self):
        self.project.mkdir()
        (self.project / "evaluation").write_text("unrelated business file")
        with self.assertRaisesRegex(ValueError, "Conflicting business directory"):
            self.install()
        self.assertEqual({path.name for path in self.project.iterdir()}, {"evaluation"})

    def test_app_version_change_and_modified_app_are_refused(self):
        self.install()
        path = self.project / ".workspace/manifest.json"
        original = path.read_bytes()
        obj = json.loads(original)
        obj["version"] = "99.0.0"
        path.write_text(json.dumps(obj))
        (self.project / "goal.json").unlink()
        with self.assertRaisesRegex(ValueError, "upgrades are not supported"):
            self.install()
        self.assertFalse((self.project / "goal.json").exists())
        path.write_bytes(original)
        (self.project / ".workspace/app/assets/index.html").write_text("local edit")
        before = self.snapshot(self.project)
        with self.assertRaisesRegex(ValueError, "Installed app differs"):
            self.install()
        self.assertEqual(before, self.snapshot(self.project))

    def test_app_directory_collision_is_preflighted(self):
        (self.project / ".workspace/app").mkdir(parents=True)
        (self.project / ".workspace/app/assets").write_text("business file")
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse((self.project / "project.json").exists())

    def test_builder_rejects_source_symlinks_maps_and_existing_outputs(self):
        with self.assertRaisesRegex(ValueError, "already exist"):
            builder.build(self.source, self.output)
        (self.source / "workspace/dist/leak.js.map").write_text("source map")
        with self.assertRaisesRegex(ValueError, "Unexpected built asset"):
            builder.build(self.source, self.base / "other-dist")
        (self.source / "workspace/dist/leak.js.map").unlink()
        (self.source / "workspace/dist/leak.js").symlink_to(self.source / "workspace/workspace.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            builder.build(self.source, self.base / "other-dist")

    def test_packaged_installer_and_app_survive_source_removal_and_move(self):
        # Invoke the copy inside the kit, not a script imported from product source.
        shutil.rmtree(self.source)
        result = subprocess.run([sys.executable, str(self.kit / "install-workspace.py"), "--kit", str(self.kit),
                                 "--project", str(self.project), "--name", "隔离项目"],
                                cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        shutil.rmtree(self.output)
        moved = self.base / "moved-research"
        self.project.rename(moved)
        process = subprocess.Popen([sys.executable, str(moved / ".workspace/app/workspace.py"), "--project", str(moved), "--port", "0"],
                                   cwd=self.base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=10), "Isolated server did not report startup")
            url = process.stdout.readline().strip()
            self.assertTrue(url.startswith("http://127.0.0.1:"), f"Unexpected startup output: {url}")
            with urlopen(url, timeout=5) as response:
                self.assertIn("isolated kit fixture", response.read().decode())
        finally:
            process.terminate()
            process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
