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
from urllib.request import ProxyHandler, build_opener

urlopen = build_opener(ProxyHandler({})).open

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
        for name in ("workspace.py", "monitor.py"):
            shutil.copyfile(ROOT / "workspace" / name, self.source / "workspace" / name)
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
        self.assertEqual((manifest["version"], manifest["schema_min"], manifest["schema_max"]), ("0.5.0", 3, 3))
        self.assertEqual(builder.TEMPLATES, installer.TEMPLATES)
        self.assertEqual(set(installer.TEMPLATES), {"AGENTS.md", "project.json", "proposal.json", "resources.json"})
        self.assertEqual(set(builder.SKILLS), {"research-workspace", "tunetune-init", "build-evaluation", "run-experiments"})
        self.assertEqual(set(payload), {f"template/{name}" for name in installer.TEMPLATES}
                         | {"install-workspace.py", "workspace/workspace.py", "workspace/monitor.py",
                            "workspace/assets/index.html", "workspace/assets/assets/app.js"}
                         | set(builder.collect_skills(self.source)))
        contract = (self.source / "skills/research-workspace/references/records.md").read_bytes()
        self.assertEqual(payload["skills/research-workspace/references/records.md"], contract)
        self.assertIn(b"references/records.md", payload["template/AGENTS.md"])
        self.assertFalse(any("research-contract.md" in name for name in payload))
        for entry in manifest["files"]:
            self.assertEqual(entry["sha256"], hashlib.sha256((self.kit / entry["path"]).read_bytes()).hexdigest())
        with tarfile.open(self.archive) as archive:
            names = archive.getnames()
            self.assertIn("workspace-kit-0.5.0/install-workspace.py", names)
            self.assertIn("workspace-kit-0.5.0/workspace/monitor.py", names)
            self.assertFalse(any(any(part in name.split("/") for part in ("design", "notes", "reference", "evals", "src", "node_modules")) for name in names))
        for relative, source in builder.collect_skills(self.source).items():
            self.assertEqual(payload[relative], source.read_bytes())
            self.assertTrue((self.kit / relative).is_file())

    def test_missing_base_skill_dependency_is_refused(self):
        for relative in ("references/tools.md", "scripts/records.py", "scripts/run.py"):
            path = self.source / "skills/research-workspace" / relative
            data = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(ValueError, path.name):
                builder.build(self.source, self.base / "missing-dependency")
            self.assertFalse((self.base / "missing-dependency").exists())
            path.write_bytes(data)

    def test_contract_lives_only_in_base_skill(self):
        # Stale templates are excluded, not copied into a new format-3 project.
        for name in ("research-contract.md", "goal.json", "candidates.json", "workspace.json"):
            (self.source / "templates/workspace" / name).write_text("stale template")
        kit, archive_path = builder.build(self.source, self.base / "contract-dist")
        canonical = (self.source / "skills/research-workspace/references/records.md").read_bytes()
        self.assertEqual({path.name for path in (kit / "template").iterdir()}, set(installer.TEMPLATES))
        with tarfile.open(archive_path) as archive:
            self.assertEqual(archive.extractfile("workspace-kit-0.5.0/skills/research-workspace/references/records.md").read(), canonical)
            self.assertFalse(any("research-contract.md" in name for name in archive.getnames()))
        (self.source / "skills/research-workspace/references/records.md").unlink()
        with self.assertRaisesRegex(ValueError, "records.md"):
            builder.build(self.source, self.base / "missing-contract-dist")
        self.assertFalse((self.base / "missing-contract-dist").exists())

    def test_missing_monitor_is_refused_before_build_publication(self):
        (self.source / "workspace/monitor.py").unlink()
        with self.assertRaisesRegex(ValueError, "monitor.py"):
            builder.build(self.source, self.base / "missing-monitor")
        self.assertFalse((self.base / "missing-monitor").exists())

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

    def test_bundle_requires_shared_tools_and_monitor(self):
        original = (self.kit / "manifest.json").read_bytes()
        for relative in ("skills/research-workspace/scripts/records.py",
                         "skills/research-workspace/scripts/run.py", "workspace/monitor.py"):
            with self.subTest(path=relative):
                (self.kit / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest.update(
                    files=[item for item in manifest["files"] if item["path"] != relative]))
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
        self.assertEqual({path.name for path in self.project.iterdir()}, set(installer.TEMPLATES) | {".workspace", ".agents"})
        self.assertFalse((self.project / ".workspace/runtime").exists())
        self.assertFalse((self.project / "skills").exists())
        for name in ("workspace.py", "monitor.py"):
            self.assertEqual((self.project / ".workspace/app" / name).read_bytes(), (self.kit / "workspace" / name).read_bytes())
        required_parents = {parent for path in self.project.rglob("*") if path.is_file()
                            for parent in path.parents if parent.is_relative_to(self.project) and parent != self.project}
        self.assertEqual({path for path in self.project.rglob("*") if path.is_dir()}, required_parents)

    def test_template_defaults(self):
        self.install()
        expected = {
            "project.json": {"schema_version": 3, "name": "未命名研究", "language": "zh-CN",
                             "current_evaluation": None, "deliveries": []},
            "proposal.json": {"summary": "", "sections": [], "examples": []},
            "resources.json": {"items": []},
        }
        for name, value in expected.items():
            self.assertEqual(json.loads((self.project / name).read_text()), value)

    def test_repeated_install_preserves_current_research(self):
        self.install(name="原名称")
        proposal = self.project / "proposal.json"
        value = json.loads(proposal.read_text())
        value["summary"] = "用户已经编辑"
        value["sections"] = [{"title": "Constraints", "body": "Use local data only."}]
        value["examples"] = [{"id": "sample1", "input": {"text": "hello"}, "expected_output": "greeting"}]
        value["feasibility"] = {"verdict": "conditional", "reason": "Need independent examples."}
        proposal.write_text(json.dumps(value, ensure_ascii=False))
        (self.project / "AGENTS.md").write_text("Existing project instructions")
        (self.project / "experiments/e1").mkdir(parents=True)
        (self.project / "experiments/e1/analysis.json").write_text('{"outcome":"baseline","summary":"Measured reference"}')
        (self.project / "project.json").write_text(json.dumps({"schema_version": 3, "name": "原名称", "language": "zh-CN",
                                                              "current_evaluation": "v1", "deliveries": ["e1"]}))
        before = self.snapshot(self.project)
        directories = {path for path in self.project.rglob("*") if path.is_dir()}
        self.assertEqual(self.install(name="不得更名"), 0)
        self.assertEqual(before, self.snapshot(self.project))
        self.assertEqual(directories, {path for path in self.project.rglob("*") if path.is_dir()})

    def test_existing_engineering_project_is_preserved(self):
        self.project.mkdir()
        (self.project / "train.py").write_text("# existing business code")
        (self.project / "AGENTS.md").write_text("Do not overwrite these instructions")
        (self.project / "NOTES.txt").write_text("Keep existing research notes")
        before = self.snapshot(self.project)
        with patch.object(installer, "validate_business", wraps=installer.validate_business) as validate:
            self.install()
        self.assertTrue(validate.called)
        self.assertTrue(all(call.args[0].endswith(".json") for call in validate.call_args_list))
        for name, data in before.items():
            self.assertEqual((self.project / name).read_bytes(), data)

    def test_unrelated_notes_are_not_treated_as_protocol_files(self):
        self.project.mkdir()
        note = self.project / "review.md"
        note.write_text("Existing personal engineering notes")
        self.install()
        self.assertEqual(note.read_text(), "Existing personal engineering notes")
        self.assertTrue((self.project / "proposal.json").is_file())

    def test_schema_one_project_is_refused_without_writes(self):
        self.project.mkdir()
        (self.project / "project.json").write_text(json.dumps({
            "schema_version": 1, "name": "Previous study", "language": "en", "current_evaluation": None}))
        before = self.snapshot(self.project)
        with self.assertRaisesRegex(ValueError, "format 3 required; no automatic migration"):
            self.install()
        self.assertEqual(before, self.snapshot(self.project))
        self.assertEqual({path.name for path in self.project.iterdir()}, {"project.json"})

    def test_only_missing_files_are_repaired(self):
        self.install()
        missing = ("resources.json", ".workspace/app/assets/index.html", "AGENTS.md", ".workspace/app/monitor.py")
        originals = {name: (self.project / name).read_bytes() for name in missing}
        for name in missing:
            (self.project / name).unlink()
        before = self.snapshot(self.project)
        self.assertEqual(self.install(), len(missing))
        for name, data in {**before, **originals}.items():
            self.assertEqual((self.project / name).read_bytes(), data)
        self.assertEqual(self.install(), 0)

    def test_installed_guide_has_no_project_root_copy(self):
        self.project.mkdir()
        instructions = b"Existing engineering instructions; preserve verbatim\n"
        (self.project / "AGENTS.md").write_bytes(instructions)
        self.install()
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), instructions)
        self.assertEqual((self.project / ".agents/skills/research-workspace/references/records.md").read_bytes(),
                         (self.kit / "skills/research-workspace/references/records.md").read_bytes())
        self.assertFalse((self.project / "research-contract.md").exists())

    def test_late_collision_never_overwrites_another_writer(self):
        real_link = installer.os.link

        def collide(source, destination):
            if destination.name == "proposal.json":
                destination.write_text("concurrent writer data")
            real_link(source, destination)

        with patch.object(installer.os, "link", side_effect=collide):
            with self.assertRaises(FileExistsError):
                self.install()
        self.assertEqual(self.snapshot(self.project), {"proposal.json": b"concurrent writer data"})

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

    def test_shared_guide_is_required_and_unlisted_templates_are_refused(self):
        original = (self.kit / "manifest.json").read_bytes()
        self.rewrite_manifest(lambda manifest: manifest.update(
            files=[entry for entry in manifest["files"] if entry["path"] != "skills/research-workspace/references/records.md"]))
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.install()
        for name in ("notes.md", "research-contract.md", "goal.json", "candidates.json", "workspace.json"):
            with self.subTest(name=name):
                (self.kit / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest["files"].append(
                    {"path": f"template/{name}", "sha256": "0" * 64}))
                with self.assertRaisesRegex(ValueError, "Unexpected manifest file"):
                    self.install()
        self.assertFalse(self.project.exists())

    def test_kit_version_and_schema_range_are_exact(self):
        original = (self.kit / "manifest.json").read_bytes()
        for version, low, high in (("0.3.0", 1, 1), ("0.5.0", 1, 2), ("0.5.0", 2, 3), ("0.5.0", True, 2)):
            with self.subTest(version=version, low=low, high=high):
                (self.kit / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest.update(version=version, schema_min=low, schema_max=high))
                with self.assertRaisesRegex(ValueError, "Unsupported kit version or schema range"):
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
        (self.project / "proposal.json").symlink_to(outside / "proposal.json")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()
        (self.project / "proposal.json").unlink()
        (self.project / "resources.json").symlink_to(outside / "resources.json")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_proposal_directory_collision_is_preflighted(self):
        (self.project / "proposal.json").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Conflicting template path"):
            self.install()
        self.assertEqual({path.name for path in self.project.iterdir()}, {"proposal.json"})

    def test_malformed_or_conflicting_business_files_are_refused(self):
        self.project.mkdir()
        project = {"schema_version": 3, "name": "Research", "language": "en", "current_evaluation": None, "deliveries": []}
        proposal = {"summary": "", "sections": [], "examples": []}
        resource = {"id": "r1", "title": "Data", "type": "dataset", "status": "unknown"}
        cases = [("project.json", "[]"), ("project.json", "not json"),
                 ("project.json", '{"schema_version":99}'), ("project.json", '{"schema_version":3,"schema_version":3}'),
                 ("project.json", json.dumps({**project, "deliveries": ["../escape"]})),
                 ("project.json", json.dumps({**project, "deliveries": ["e1", "e1"]})),
                 ("project.json", json.dumps({**project, "current_evaluation": "../escape"})),
                 ("project.json", json.dumps({**project, "current_evaluation": "draft"})),
                 ("proposal.json", '{"unrelated":true}'),
                 ("proposal.json", json.dumps({**proposal, "revision": 1})),
                 ("proposal.json", json.dumps({**proposal, "confirmation": {}})),
                 ("proposal.json", json.dumps({**proposal, "sections": [{"title": "missing body"}]})),
                 ("proposal.json", json.dumps({**proposal, "examples": [{"id": "s1"}]})),
                 ("resources.json", '{"items":"business data"}'), ("resources.json", '{"items":[1]}'),
                 ("resources.json", json.dumps({"items": [{**resource, "path": "../private"}]})),
                 ("resources.json", json.dumps({"items": [{**resource, "path": "data.txt", "location": "/external"}]})),
                 ("resources.json", json.dumps({"items": [{**resource, "location": " "}]})),
                 ("resources.json", json.dumps({"items": [{**resource, "location": chr(0)}]})),
                 ("resources.json", json.dumps({"items": [{**resource, "monitor": {"kind": "shell", "command": "id"}}]})),
                 ("resources.json", json.dumps({"items": [{**resource, "monitor": {"kind": "nvidia_gpu", "index": True}}]}))]
        for name, data in cases:
            with self.subTest(name=name, data=data):
                path = self.project / name
                path.write_text(data)
                before = self.snapshot(self.project)
                with self.assertRaises(ValueError):
                    self.install()
                self.assertEqual(before, self.snapshot(self.project))
                path.unlink()

    def test_only_installation_parents_are_preflighted(self):
        self.project.mkdir()
        (self.project / "evaluation").write_text("unrelated business file")
        (self.project / "data").symlink_to(self.base / "unavailable")
        self.install()
        self.assertEqual((self.project / "evaluation").read_text(), "unrelated business file")
        self.assertTrue((self.project / "data").is_symlink())
        self.assertEqual({path.name for path in self.project.iterdir()},
                         set(installer.TEMPLATES) | {".agents", ".workspace", "evaluation", "data"})

    def test_required_parent_collision_is_preflighted(self):
        self.project.mkdir()
        (self.project / ".agents").write_text("existing file")
        with self.assertRaisesRegex(ValueError, "File occupies required directory"):
            self.install()
        self.assertEqual(self.snapshot(self.project), {".agents": b"existing file"})

    def test_resource_inventory_is_preserved_without_probing_locations(self):
        self.project.mkdir()
        inventory = {"items": [
            {"id": "data", "title": "Dataset", "type": "private corpus", "status": "missing", "path": "data/train.jsonl",
             "monitor": {"kind": "file"}},
            {"id": "remote", "title": "External", "type": "storage", "status": "unknown", "location": "/not-accessed"},
            {"id": "gpu", "title": "GPU", "type": "compute", "status": "unknown", "monitor": {"kind": "nvidia_gpu", "index": 0}},
        ]}
        data = json.dumps(inventory).encode()
        (self.project / "resources.json").write_bytes(data)
        self.install()
        self.assertEqual((self.project / "resources.json").read_bytes(), data)
        self.assertFalse((self.project / "data").exists())
        self.assertFalse((self.project / ".workspace/runtime").exists())

    def test_app_version_change_and_modified_app_are_refused(self):
        self.install()
        path = self.project / ".workspace/manifest.json"
        original = path.read_bytes()
        obj = json.loads(original)
        obj["version"] = "99.0.0"
        path.write_text(json.dumps(obj))
        (self.project / "proposal.json").unlink()
        with self.assertRaisesRegex(ValueError, "upgrades are not supported"):
            self.install()
        self.assertFalse((self.project / "proposal.json").exists())
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
            ("skills/run-experiments/references/linked.json", external_file),
            ("skills/run-experiments/scripts/linked", external),
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
        skills = extracted / "workspace-kit-0.5.0/skills"
        self.assertEqual({path.name for path in skills.iterdir()}, set(builder.SKILLS))
        for name in ("records.py", "run.py", "scout.py"):
            script = skills / "research-workspace/scripts" / name
            result = subprocess.run([sys.executable, "-E", "-s", "-B", str(script), "--help"],
                                    cwd=self.base, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout.lower())
        for name in ("tunetune-init", "build-evaluation", "run-experiments"):
            with self.subTest(skill=name):
                skill = skills / name / "SKILL.md"
                links = re.findall(r"\.\./research-workspace/[A-Za-z0-9_./-]+", skill.read_text(encoding="utf-8"))
                self.assertTrue(links, f"{name} must reference its packaged base skill")
                for link in links:
                    target = (skill.parent / link).resolve()
                    self.assertTrue(target.is_relative_to(skills / "research-workspace"), link)
                    self.assertTrue(target.is_file(), link)

    def test_packaged_installer_repeats_without_generating_kit_cache(self):
        command = [sys.executable, "-E", "-s", str(self.kit / "install-workspace.py"),
                   "--kit", str(self.kit), "--project", str(self.project)]
        before = self.snapshot(self.kit)
        for _ in range(2):
            result = subprocess.run(command, cwd=self.base, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.snapshot(self.kit), before)
        self.assertFalse(list(self.kit.rglob("__pycache__")))

    def test_packaged_installer_and_app_survive_source_removal_and_move(self):
        # Extract the release archive, then remove every build input and output.
        extracted = self.base / "extracted-kit"
        with tarfile.open(self.archive) as archive:
            archive.extractall(extracted)
        kit = extracted / "workspace-kit-0.5.0"
        shutil.rmtree(self.source)
        shutil.rmtree(self.output)
        result = subprocess.run([sys.executable, "-E", "-s", "-B", str(kit / "install-workspace.py"), "--kit", str(kit),
                                 "--project", str(self.project), "--name", "隔离项目"],
                                cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.project / "research-contract.md").exists())
        self.assertEqual((self.project / ".workspace/app/monitor.py").read_bytes(), (kit / "workspace/monitor.py").read_bytes())
        shutil.rmtree(extracted)
        moved = self.base / "moved-research"
        self.project.rename(moved)
        records = moved / ".agents/skills/research-workspace/scripts/records.py"
        result = subprocess.run([sys.executable, "-E", "-s", "-B", str(records), "validate", "--project", str(moved)],
                                cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["valid"])
        process = subprocess.Popen([sys.executable, "-E", "-s", "-B", str(moved / ".workspace/app/workspace.py"), "--project", str(moved), "--port", "0"],
                                   cwd=self.base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=10), "Isolated server did not report startup")
            url = process.stdout.readline().strip()
            self.assertTrue(url.startswith("http://127.0.0.1:"), f"Unexpected startup output: {url}")
            with urlopen(url, timeout=5) as response:
                self.assertIn("isolated kit fixture", response.read().decode())
            with urlopen(url + "/api/state", timeout=5) as response:
                state = json.load(response)
            self.assertIsNone(state["error"])
            self.assertEqual(state["files"]["project.json"]["content"]["schema_version"], 3)
            self.assertIn("proposal.json", state["files"])
            self.assertEqual(state["observations"]["items"], [])
        finally:
            process.terminate()
            process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
