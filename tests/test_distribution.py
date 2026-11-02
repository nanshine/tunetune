"""Distribution checks use a tiny static fixture, not npm or a frontend build."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
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
            shutil.copytree(ROOT / directory, self.source / directory, symlinks=True)
        (self.source / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/install-workspace.py", self.source / "scripts/install-workspace.py")
        (self.source / "workspace/dist").mkdir(parents=True)
        shutil.copyfile(ROOT / "workspace/workspace.py", self.source / "workspace/workspace.py")
        (self.source / "workspace/dist/index.html").write_text("<!doctype html><title>isolated kit fixture</title>", encoding="utf-8")
        (self.source / "workspace/dist/assets").mkdir()
        (self.source / "workspace/dist/assets/app.js").write_text("console.log('fixture');", encoding="utf-8")
        for directory in ("design", "notes", "reference", "workspace/src", "workspace/node_modules"):
            (self.source / directory).mkdir(parents=True, exist_ok=True)
            (self.source / directory / "DO_NOT_SHIP.md").write_text("private source fixture")
        self.output = self.base / "dist"
        self.kit, self.archive = builder.build(self.source, self.output)
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
        self.assertEqual((manifest["version"], manifest["schema_min"], manifest["schema_max"]), ("0.3.0", 1, 1))
        self.assertEqual(builder.TEMPLATES, installer.TEMPLATES)
        self.assertIn("research-contract.md", installer.TEMPLATES)
        self.assertEqual(set(builder.SKILLS), {"research-workspace", "tunetune-init", "build-evaluation", "train", "review"})
        self.assertEqual(set(payload), {f"template/{name}" for name in installer.TEMPLATES}
                         | {"install-workspace.py", "workspace/workspace.py", "workspace/assets/index.html", "workspace/assets/assets/app.js"}
                         | set(builder.collect_skills(self.source)))
        contract = (self.source / "skills/research-workspace/references/records.md").read_bytes()
        self.assertEqual(payload["template/research-contract.md"], contract)
        self.assertIn(b"research-contract.md", payload["template/AGENTS.md"])
        for entry in manifest["files"]:
            self.assertEqual(entry["sha256"], hashlib.sha256((self.kit / entry["path"]).read_bytes()).hexdigest())
        with tarfile.open(self.archive) as archive:
            names = archive.getnames()
            self.assertIn("workspace-kit-0.3.0/install-workspace.py", names)
            self.assertIn("workspace-kit-0.3.0/template/research-contract.md", names)
            self.assertFalse(any(any(part in name.split("/") for part in ("design", "notes", "reference", "evals", "src", "node_modules")) for name in names))
        for relative, source in builder.collect_skills(self.source).items():
            self.assertEqual(payload[relative], source.read_bytes())
            self.assertTrue((self.kit / relative).is_file())

    def test_missing_base_skill_dependency_is_refused(self):
        for relative in ("references/tools.md", "scripts/records.py"):
            path = self.source / "skills/research-workspace" / relative
            data = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(ValueError, path.name):
                builder.build(self.source, self.base / "missing-dependency")
            self.assertFalse((self.base / "missing-dependency").exists())
            path.write_bytes(data)

    def test_contract_comes_only_from_base_skill(self):
        # A stale duplicate in the template tree must never become the source of truth.
        (self.source / "templates/workspace/research-contract.md").write_text("stale duplicate")
        kit, archive_path = builder.build(self.source, self.base / "contract-dist")
        canonical = (self.source / "skills/research-workspace/references/records.md").read_bytes()
        self.assertEqual((kit / "template/research-contract.md").read_bytes(), canonical)
        with tarfile.open(archive_path) as archive:
            self.assertEqual(archive.extractfile("workspace-kit-0.3.0/skills/research-workspace/references/records.md").read(), canonical)
        (self.source / "skills/research-workspace/references/records.md").unlink()
        with self.assertRaisesRegex(ValueError, "records.md"):
            builder.build(self.source, self.base / "missing-contract-dist")
        self.assertFalse((self.base / "missing-contract-dist").exists())

    def test_all_skill_resources_use_recursive_allowlist(self):
        expected = set(builder.collect_skills(self.source))
        allowed = {
            "references/distribution-fixture/deep/contract.md": "# Fixture contract\n",
            "references/distribution-fixture/schema.json": '{"fixture":true}\n',
            "scripts/distribution-fixture/deep/helper.py": 'print("fixture")\n',
        }
        excluded = (
            "evals/distribution-fixture.json", "notes/distribution-fixture.md", "reference/distribution-fixture.md",
            "distribution-fixture.md", "distribution-fixture.py", ".hidden/distribution-fixture.md",
            "references/.hidden.md", "references/.hidden/fixture.json", "references/cache/fixture.md",
            "references/__pycache__/fixture.json", "references/evals/fixture.json", "references/notes/fixture.md",
            "references/reference/fixture.md", "references/fixture.py", "references/fixture.md~",
            "scripts/__pycache__/fixture.py", "scripts/__pycache__/fixture.pyc", "scripts/.cache/fixture.py",
            "scripts/cache/fixture.py", "scripts/node_modules/fixture.py", "scripts/evals/fixture.py",
            "scripts/notes/fixture.py", "scripts/reference/fixture.py", "scripts/fixture.sh",
            "scripts/fixture.exe", "scripts/fixture", "scripts/fixture.json", "scripts/.hidden.py",
        )
        for name in builder.SKILLS:
            root = self.source / "skills" / name
            for relative, content in allowed.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                expected.add(f"skills/{name}/{relative}")
            for relative in excluded:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("do not distribute")
                path.chmod(0o755)
        unknown = self.source / "skills/unlisted-skill/SKILL.md"
        unknown.parent.mkdir()
        unknown.write_text("not an allowed skill")
        kit, archive_path = builder.build(self.source, self.base / "resource-dist")
        actual = {path.relative_to(kit).as_posix() for path in (kit / "skills").rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        for relative in actual:
            self.assertEqual((kit / relative).read_bytes(), (self.source / relative).read_bytes())

    def test_bundle_requires_shared_record_tools(self):
        relative = "skills/research-workspace/scripts/records.py"
        (self.kit / relative).unlink()
        self.rewrite_manifest(lambda manifest: manifest.update(files=[item for item in manifest["files"] if item["path"] != relative]))
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.install()
        self.assertFalse(self.project.exists())

    def test_project_skills_are_installed_together_and_conflicts_preserved(self):
        self.install(host="claude")
        for name in builder.SKILLS:
            self.assertEqual((self.project / ".claude/skills" / name / "SKILL.md").read_bytes(),
                             (self.kit / "skills" / name / "SKILL.md").read_bytes())
        self.assertFalse((self.project / ".agents").exists())
        skill = self.project / ".claude/skills/tunetune-init/SKILL.md"
        skill.write_text("Existing local skill")
        before = self.snapshot(self.project)
        with self.assertRaisesRegex(ValueError, "Conflicting app file"):
            self.install(host="claude")
        self.assertEqual(self.snapshot(self.project), before)

    def test_skill_symlink_is_rejected_before_installation(self):
        outside = self.base / "external-skills"
        outside.mkdir()
        (self.project / ".agents").mkdir(parents=True)
        (self.project / ".agents/skills").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse((self.project / "project.json").exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_minimal_install(self):
        self.assertGreater(self.install(name="实际研究"), 0)
        self.assertEqual(json.loads((self.project / "project.json").read_text())["name"], "实际研究")
        self.assertEqual({path.name for path in self.project.iterdir()}, set(installer.TEMPLATES) | set(installer.BUSINESS_DIRS) | {".agents"})
        self.assertFalse((self.project / ".workspace/runtime").exists())
        self.assertFalse((self.project / "skills").exists())
        self.assertEqual((self.project / ".workspace/app/workspace.py").read_bytes(), (self.kit / "workspace/workspace.py").read_bytes())

    def test_template_defaults(self):
        self.install()
        expected = {
            "project.json": {"schema_version": 1, "name": "未命名研究", "language": "zh-CN", "current_evaluation": None},
            "goal.json": {"revision": 1, "summary": "", "sections": [], "examples": [], "proposal": ""},
            "resources.json": {"items": []}, "candidates.json": {"items": []},
            "workspace.json": {"title": "研究空间", "metric_columns": [], "presentation": {"id": "initial-goal", "panel": "goal"}},
        }
        for name, value in expected.items():
            self.assertEqual(json.loads((self.project / name).read_text()), value)

    def test_repeated_install_preserves_edits_and_feedback(self):
        self.install(name="原名称")
        goal = self.project / "goal.json"
        value = json.loads(goal.read_text())
        value["summary"] = "用户已经编辑"
        goal.write_text(json.dumps(value, ensure_ascii=False))
        (self.project / "AGENTS.md").write_text("Existing project instructions")
        (self.project / "research-contract.md").write_text("Existing locally adapted contract; not JSON")
        (self.project / "feedback/incoming").mkdir(parents=True)
        (self.project / "feedback/incoming/f1.json").write_text('{"id":"f1","text":"原话"}')
        before = self.snapshot(self.project)
        self.assertEqual(self.install(name="不得更名"), 0)
        self.assertEqual(before, self.snapshot(self.project))

    def test_existing_engineering_project_is_preserved(self):
        self.project.mkdir()
        (self.project / "train.py").write_text("# existing business code")
        (self.project / "AGENTS.md").write_text("Do not overwrite these instructions")
        (self.project / "research-contract.md").write_text("Keep this plain-text contract, not JSON")
        before = self.snapshot(self.project)
        with patch.object(installer, "validate_business", wraps=installer.validate_business) as validate:
            self.install()
        self.assertTrue(validate.called)
        self.assertTrue(all(call.args[0].endswith(".json") for call in validate.call_args_list))
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
        (self.project / "AGENTS.md").unlink()
        (self.project / "research-contract.md").unlink()
        before = self.snapshot(self.project)
        self.assertEqual(self.install(), 4)
        for name, data in before.items():
            self.assertEqual((self.project / name).read_bytes(), data)
        for name in ("AGENTS.md", "research-contract.md"):
            self.assertEqual((self.project / name).read_bytes(), (self.kit / "template" / name).read_bytes())
        self.assertEqual(self.install(), 0)

    def test_contract_is_added_without_changing_existing_agents(self):
        self.project.mkdir()
        instructions = b"Existing engineering instructions; preserve verbatim\n"
        (self.project / "AGENTS.md").write_bytes(instructions)
        self.install()
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), instructions)
        self.assertEqual((self.project / "research-contract.md").read_bytes(),
                         (self.kit / "template/research-contract.md").read_bytes())

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

    def test_contract_is_required_and_unlisted_templates_are_refused(self):
        original = (self.kit / "manifest.json").read_bytes()
        self.rewrite_manifest(lambda manifest: manifest.update(
            files=[entry for entry in manifest["files"] if entry["path"] != "template/research-contract.md"]))
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.install()
        (self.kit / "manifest.json").write_bytes(original)
        self.rewrite_manifest(lambda manifest: manifest["files"].append(
            {"path": "template/notes.md", "sha256": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "Unexpected manifest file"):
            self.install()
        self.assertFalse(self.project.exists())

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
        (self.project / "goal.json").unlink()
        (self.project / "research-contract.md").symlink_to(outside / "contract.md")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_contract_directory_collision_is_preflighted(self):
        (self.project / "research-contract.md").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Conflicting template path"):
            self.install()
        self.assertEqual({path.name for path in self.project.iterdir()}, {"research-contract.md"})

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

    def test_builder_rejects_skill_symlinks_before_publication(self):
        external = self.base / "external"
        external.mkdir()
        external_file = external / "payload.md"
        external_file.write_text("external content")
        cases = (
            ("skills/tunetune-init", external),
            ("skills/tunetune-init/SKILL.md", external_file),
            ("skills/research-workspace/references", external),
            ("skills/research-workspace/references/records.md", external_file),
            ("skills/research-workspace/scripts/records.py", external_file),
            ("skills/train/references/linked.json", external_file),
            ("skills/review/scripts/linked", external),
            ("skills/build-evaluation/evals/linked.json", external_file),
            ("skills/tunetune-init/notes/linked.md", external_file),
            ("skills/tunetune-init/references/.hidden.md", external_file),
            ("skills/tunetune-init/scripts/__pycache__/linked.pyc", external_file),
            ("skills/tunetune-init/scripts/dangling.py", self.base / "missing-target"),
        )
        output = self.base / "symlink-dist"
        for relative, target in cases:
            with self.subTest(path=relative):
                path = self.source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                backup = self.base / "saved-input"
                if path.exists():
                    path.rename(backup)
                try:
                    path.symlink_to(target, target_is_directory=target.is_dir())
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        builder.build(self.source, output)
                    self.assertFalse(output.exists())
                finally:
                    path.unlink()
                    if backup.exists():
                        backup.rename(path)

    def test_extracted_skills_run_and_sibling_references_resolve_without_source(self):
        extracted = self.base / "installed-skills"
        with tarfile.open(self.archive) as archive:
            archive.extractall(extracted)
        shutil.rmtree(self.source)
        shutil.rmtree(self.output)
        skills = extracted / "workspace-kit-0.3.0/skills"
        self.assertEqual({path.name for path in skills.iterdir()}, set(builder.SKILLS))
        script = skills / "research-workspace/scripts/records.py"
        result = subprocess.run([sys.executable, "-E", "-s", "-B", str(script), "--help"],
                                cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())
        for name in ("tunetune-init", "build-evaluation", "train", "review"):
            with self.subTest(skill=name):
                skill = skills / name / "SKILL.md"
                links = re.findall(r"\.\./research-workspace/[A-Za-z0-9_./-]+", skill.read_text(encoding="utf-8"))
                self.assertTrue(links, f"{name} must reference its packaged base skill")
                for link in links:
                    target = (skill.parent / link).resolve()
                    self.assertTrue(target.is_relative_to(skills / "research-workspace"), link)
                    self.assertTrue(target.is_file(), link)

    def test_packaged_installer_and_app_survive_source_removal_and_move(self):
        # Extract the release archive, then remove every build input and output.
        extracted = self.base / "extracted-kit"
        with tarfile.open(self.archive) as archive:
            archive.extractall(extracted)
        kit = extracted / "workspace-kit-0.3.0"
        shutil.rmtree(self.source)
        shutil.rmtree(self.output)
        result = subprocess.run([sys.executable, "-E", "-s", "-B", str(kit / "install-workspace.py"), "--kit", str(kit),
                                 "--project", str(self.project), "--name", "隔离项目"],
                                cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.project / "research-contract.md").read_bytes(), (kit / "template/research-contract.md").read_bytes())
        shutil.rmtree(extracted)
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
