"""Distribution checks use a tiny static panel fixture, not npm or a frontend build."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener

urlopen = build_opener(ProxyHandler({})).open

ROOT = Path(__file__).resolve().parents[1]


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


builder = load("build_skills", ROOT / "scripts/build-skills.py")
installer = load("skill_init", ROOT / "plugins/tunetune/skills/research-workspace/scripts/init.py")
release = load("check_release", ROOT / "scripts/check-release.py")


class ReleaseTests(unittest.TestCase):
    def test_repository_is_releasable_under_its_own_version(self):
        self.assertEqual(release.problems(), [])
        self.assertEqual(release.problems("v" + release.versions()["package.json"]), [])

    def test_a_tag_that_differs_from_shipped_versions_is_refused(self):
        issues = release.problems("v999.0.0")
        self.assertTrue(any(issue.startswith("package.json: version") for issue in issues))
        self.assertTrue(any("init.py" in issue for issue in issues))
        self.assertEqual(release.problems(release.versions()["package.json"]),
                         [f"Release tags look like v{release.versions()['package.json']}, not {release.versions()['package.json']}"])

    def test_every_distributed_unit_carries_the_license(self):
        license_text = (ROOT / "LICENSE").read_bytes()
        self.assertIn(b"Apache License", license_text)
        bundle = json.loads((ROOT / "package.json").read_text())
        self.assertEqual(bundle["license"], "Apache-2.0")
        for name in builder.SKILLS:
            with self.subTest(skill=name):
                # npx skills and manual copies take one skill folder at a time.
                self.assertEqual((ROOT / builder.SKILLS_DIR / name / "LICENSE.txt").read_bytes(), license_text)
        packed = subprocess.run(["npm", "pack", "--dry-run", "--json"], cwd=ROOT, capture_output=True, text=True)
        if packed.returncode == 0:
            files = {entry["path"] for entry in json.loads(packed.stdout)[0]["files"]}
            self.assertLessEqual({"LICENSE", "NOTICE", "plugins/tunetune/skills/run-experiments/LICENSE.txt"}, files)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        shutil.copytree(ROOT / builder.SKILLS_DIR, self.source / builder.SKILLS_DIR, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.skill = self.source / builder.SKILLS_DIR / "research-workspace"
        panel = self.skill / "assets/panel"
        shutil.rmtree(panel)
        (panel / "assets").mkdir(parents=True)
        (panel / "index.html").write_text("<!doctype html><title>isolated skill fixture</title>", encoding="utf-8")
        (panel / "assets/app.js").write_text("console.log('fixture');", encoding="utf-8")
        builder.build(self.source)
        self.project = self.base / "research"

    def rewrite_manifest(self, change):
        path = self.skill / "manifest.json"
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))

    def install(self, **kwargs):
        return installer.install(self.project, skill=self.skill, **kwargs)

    def snapshot(self, directory):
        return {path.relative_to(directory).as_posix(): path.read_bytes()
                for path in directory.rglob("*") if path.is_file()}

    def test_manifest_pins_exactly_the_copied_payload(self):
        manifest, _, payload = installer.verify_skill(self.skill)
        self.assertEqual(manifest["version"], "0.7.0")
        self.assertEqual(set(manifest), {"version", "files"})
        self.assertEqual(builder.TEMPLATES, installer.TEMPLATES)
        self.assertEqual(builder.APP_SCRIPTS, installer.APP_SCRIPTS)
        self.assertEqual(set(builder.SKILLS), {"research-workspace", "tunetune-init", "build-evaluation", "run-experiments"})
        self.assertEqual(set(payload), {f"scripts/{name}" for name in installer.APP_SCRIPTS}
                         | {f"assets/templates/{name}" for name in installer.TEMPLATES}
                         | {"assets/panel/index.html", "assets/panel/assets/app.js"})
        self.assertIn(b"references/records.md", payload["assets/templates/AGENTS.md"])
        for entry in manifest["files"]:
            self.assertEqual(entry["sha256"], hashlib.sha256((self.skill / entry["path"]).read_bytes()).hexdigest())

    def test_committed_manifest_is_current(self):
        self.assertTrue(builder.check(ROOT), "Rebuild the panel and run scripts/build-skills.py")

    def test_versions_and_plugin_manifests_agree(self):
        package = json.loads((ROOT / "workspace/package.json").read_text())
        # The DeepSeek Harness bundle at the repository root ships the same skills.
        bundle = json.loads((ROOT / "package.json").read_text())
        self.assertEqual({builder.VERSION, installer.VERSION, package["version"], bundle["version"]}, {"0.7.0"})
        plugin_root = ROOT / "plugins/tunetune"
        for path in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            with self.subTest(path=path):
                plugin = json.loads((plugin_root / path).read_text())
                self.assertEqual((plugin["name"], plugin["version"], plugin["skills"]), ("tunetune", "0.7.0", "./skills/"))
        # Plugin installers copy the whole plugin root, so it must hold the skills and nothing else.
        self.assertEqual({path.name for path in plugin_root.iterdir() if path.name != ".DS_Store"}, {".claude-plugin", ".codex-plugin", "skills"})
        self.assertFalse(any(path.is_symlink() for path in plugin_root.rglob("*")))
        claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual([(item["name"], item["source"]) for item in claude["plugins"]], [("tunetune", "./plugins/tunetune")])
        self.assertEqual([(item["name"], item["source"]) for item in codex["plugins"]],
                         [("tunetune", {"source": "local", "path": "./plugins/tunetune"})])
        self.assertEqual({path.name for path in (ROOT / builder.SKILLS_DIR).iterdir() if (path / "SKILL.md").is_file()}, set(builder.SKILLS))

    def test_builder_requires_shared_tools_before_writing(self):
        before = (self.skill / "manifest.json").read_bytes()
        for relative in ("references/records.md", "references/tools.md", "scripts/init.py", "scripts/records.py",
                         "scripts/run.py", "scripts/monitor.py", "scripts/workspace.py", "assets/panel/index.html"):
            with self.subTest(path=relative):
                path = self.skill / relative
                data = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, path.name):
                    builder.build(self.source)
                self.assertEqual((self.skill / "manifest.json").read_bytes(), before)
                path.write_bytes(data)

    def test_builder_refuses_stale_templates_maps_and_symlinks(self):
        for name in ("research-contract.md", "goal.json"):
            with self.subTest(template=name):
                (self.skill / "assets/templates" / name).write_text("stale template")
                with self.assertRaisesRegex(ValueError, "Templates must be exactly"):
                    builder.build(self.source)
                (self.skill / "assets/templates" / name).unlink()
        (self.skill / "assets/panel/leak.js.map").write_text("source map")
        with self.assertRaisesRegex(ValueError, "Unexpected built asset"):
            builder.build(self.source)
        (self.skill / "assets/panel/leak.js.map").unlink()
        external = self.base / "external"
        external.mkdir()
        external_file = external / "payload.md"
        external_file.write_text("external content")
        cases = (
            ("plugins/tunetune/skills/tunetune-init", external),
            ("plugins/tunetune/skills/tunetune-init/SKILL.md", external_file),
            ("plugins/tunetune/skills/research-workspace/references/records.md", external_file),
            ("plugins/tunetune/skills/research-workspace/scripts/records.py", external_file),
            ("plugins/tunetune/skills/research-workspace/assets/panel/leak.js", external_file),
            ("plugins/tunetune/skills/run-experiments/references/linked.json", external_file),
            ("plugins/tunetune/skills/build-evaluation/evals/linked.json", external_file),
            ("plugins/tunetune/skills/tunetune-init/scripts/dangling.py", self.base / "missing-target"),
        )
        before = (self.skill / "manifest.json").read_bytes()
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
                        builder.build(self.source)
                    self.assertEqual((self.skill / "manifest.json").read_bytes(), before)
                finally:
                    path.unlink()
                    if backup.exists():
                        backup.rename(path)

    def test_check_detects_a_stale_manifest(self):
        self.assertTrue(builder.check(self.source))
        (self.skill / "assets/panel/assets/app.js").write_text("console.log('rebuilt');")
        self.assertFalse(builder.check(self.source))

    def test_minimal_install(self):
        self.assertGreater(self.install(name="实际研究"), 0)
        self.assertEqual(json.loads((self.project / "project.json").read_text())["name"], "实际研究")
        self.assertEqual({path.name for path in self.project.iterdir()}, set(installer.TEMPLATES) | {".workspace"})
        self.assertFalse((self.project / ".workspace/runtime").exists())
        for name in installer.APP_SCRIPTS:
            self.assertEqual((self.project / ".workspace/app" / name).read_bytes(), (self.skill / "scripts" / name).read_bytes())
        self.assertFalse((self.project / ".workspace/app/init.py").exists())
        self.assertEqual((self.project / ".workspace/app/assets/assets/app.js").read_bytes(),
                         (self.skill / "assets/panel/assets/app.js").read_bytes())
        self.assertEqual((self.project / ".workspace/manifest.json").read_bytes(), (self.skill / "manifest.json").read_bytes())
        required_parents = {parent for path in self.project.rglob("*") if path.is_file()
                            for parent in path.parents if parent.is_relative_to(self.project) and parent != self.project}
        self.assertEqual({path for path in self.project.rglob("*") if path.is_dir()}, required_parents)

    def test_template_defaults(self):
        self.install()
        expected = {
            "project.json": {"name": "未命名研究", "language": "zh-CN",
                             "current_evaluation": None, "deliveries": []},
            "proposal.json": {"summary": "", "examples": []},
            "resources.json": {"items": []},
        }
        for name, value in expected.items():
            self.assertEqual(json.loads((self.project / name).read_text()), value)

    def test_conversation_language_sets_project_language_and_default_name(self):
        self.install(language="en")
        self.assertEqual(json.loads((self.project / "project.json").read_text())["language"], "en")
        self.assertEqual(json.loads((self.project / "project.json").read_text())["name"], "Untitled research")
        other = self.base / "chinese"
        installer.install(other, skill=self.skill, name="博客标签", language="zh-TW")
        self.assertEqual({key: json.loads((other / "project.json").read_text())[key] for key in ("name", "language")},
                         {"name": "博客标签", "language": "zh-TW"})
        for language in ("", "english language", "e", "en_US", "../x"):
            with self.subTest(language=language), self.assertRaisesRegex(ValueError, "Language must be a tag"):
                installer.install(self.base / "refused", skill=self.skill, language=language)
        self.assertFalse((self.base / "refused").exists())

    def test_repeated_install_preserves_current_research(self):
        self.install(name="原名称")
        proposal = self.project / "proposal.json"
        value = json.loads(proposal.read_text())
        value["summary"] = "用户已经编辑"
        value["goal"] = "Use local data only."
        value["examples"] = [{"id": "sample1", "input": {"text": "hello"}, "expected_output": "greeting"}]
        value["feasibility"] = {"verdict": "conditional", "reason": "Need independent examples."}
        proposal.write_text(json.dumps(value, ensure_ascii=False))
        (self.project / "AGENTS.md").write_text("Existing project instructions")
        (self.project / "experiments/e1").mkdir(parents=True)
        (self.project / "experiments/e1/analysis.json").write_text('{"outcome":"baseline","summary":"Measured reference"}')
        (self.project / "project.json").write_text(json.dumps({"name": "原名称", "language": "zh-CN",
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

    def test_older_project_is_refused_without_writes(self):
        self.project.mkdir()
        (self.project / "project.json").write_text(json.dumps({
            "schema_version": 1, "name": "Previous study", "language": "en", "current_evaluation": None, "deliveries": []}))
        before = self.snapshot(self.project)
        with self.assertRaisesRegex(ValueError, "Unknown fields: schema_version"):
            self.install()
        self.assertEqual(before, self.snapshot(self.project))
        self.assertEqual({path.name for path in self.project.iterdir()}, {"project.json"})

    def test_only_missing_files_are_repaired(self):
        self.install()
        missing = ("resources.json", ".workspace/app/assets/index.html", "AGENTS.md",
                   ".workspace/app/monitor.py", ".workspace/app/records.py")
        originals = {name: (self.project / name).read_bytes() for name in missing}
        for name in missing:
            (self.project / name).unlink()
        before = self.snapshot(self.project)
        self.assertEqual(self.install(), len(missing))
        for name, data in {**before, **originals}.items():
            self.assertEqual((self.project / name).read_bytes(), data)
        self.assertEqual(self.install(), 0)

    def test_guide_stays_in_the_skill_without_a_project_copy(self):
        self.project.mkdir()
        instructions = b"Existing engineering instructions; preserve verbatim\n"
        (self.project / "AGENTS.md").write_bytes(instructions)
        self.install()
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), instructions)
        self.assertEqual([path for path in self.project.rglob("*.md") if path.name != "AGENTS.md"], [])

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
        (self.skill / "assets/panel/index.html").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            self.install()
        self.assertFalse(self.project.exists())

    def test_unlisted_assets_are_refused_but_other_skill_files_are_not_copied(self):
        for relative in ("assets/panel/stale.js", "assets/templates/notes.md"):
            with self.subTest(path=relative):
                path = self.skill / relative
                path.write_text("unexpected")
                with self.assertRaisesRegex(ValueError, "Unexpected skill asset"):
                    self.install()
                path.unlink()
        self.assertFalse(self.project.exists())
        (self.skill / "notes.md").write_text("maintainer note")
        self.install()
        self.assertFalse(any(path.name == "notes.md" for path in self.project.rglob("*")))

    def test_manifest_traversal_and_absolute_paths_are_refused(self):
        original = (self.skill / "manifest.json").read_bytes()
        for path in ("../escape", "/tmp/escape", "assets/../escape", "assets//panel/x", "./x", "C:/escape", "assets\\escape"):
            with self.subTest(path=path):
                (self.skill / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest["files"].append({"path": path, "sha256": "0" * 64}))
                with self.assertRaisesRegex(ValueError, "Unsafe manifest path"):
                    self.install()
        self.assertFalse(self.project.exists())

    def test_duplicate_missing_and_unlisted_manifest_entries_are_refused(self):
        original = (self.skill / "manifest.json").read_bytes()
        self.rewrite_manifest(lambda manifest: manifest["files"].append(manifest["files"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate manifest"):
            self.install()
        for relative in ("scripts/records.py", "scripts/monitor.py", "assets/templates/AGENTS.md", "assets/panel/index.html"):
            with self.subTest(missing=relative):
                (self.skill / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest.update(
                    files=[item for item in manifest["files"] if item["path"] != relative]))
                with self.assertRaisesRegex(ValueError, "missing required|Unexpected skill asset"):
                    self.install()
        for relative in ("SKILL.md", "references/records.md", "scripts/init.py", "assets/templates/notes.md", "assets/other.js"):
            with self.subTest(unlisted=relative):
                (self.skill / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest["files"].append({"path": relative, "sha256": "0" * 64}))
                with self.assertRaisesRegex(ValueError, "Unexpected manifest file"):
                    self.install()
        self.assertFalse(self.project.exists())

    def test_tool_version_is_exact(self):
        original = (self.skill / "manifest.json").read_bytes()
        for version in ("0.6.0", "0.7.1", None, 7):
            with self.subTest(version=version):
                (self.skill / "manifest.json").write_bytes(original)
                self.rewrite_manifest(lambda manifest: manifest.update(version=version))
                with self.assertRaisesRegex(ValueError, "Unsupported tool version"):
                    self.install()
                self.assertFalse(self.project.exists())

    def test_symlink_payload_is_refused(self):
        path = self.skill / "assets/panel/index.html"
        external = self.base / "outside.html"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.install()
        self.assertFalse(self.project.exists())

    def test_skill_reached_through_an_installer_link_is_accepted(self):
        # Skill installers commonly link one canonical copy into each application's directory.
        linked = self.base / "agent-skills/research-workspace"
        linked.parent.mkdir()
        linked.symlink_to(self.skill, target_is_directory=True)
        self.assertGreater(installer.install(self.project, skill=linked), 0)
        self.assertEqual((self.project / ".workspace/app/run.py").read_bytes(), (self.skill / "scripts/run.py").read_bytes())

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

    def test_project_inside_the_skill_is_refused(self):
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            installer.install(self.skill / "study", skill=self.skill)
        self.assertFalse((self.skill / "study").exists())

    def test_proposal_directory_collision_is_preflighted(self):
        (self.project / "proposal.json").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Conflicting template path"):
            self.install()
        self.assertEqual({path.name for path in self.project.iterdir()}, {"proposal.json"})

    def test_malformed_or_conflicting_business_files_are_refused(self):
        self.project.mkdir()
        project = {"name": "Research", "language": "en", "current_evaluation": None, "deliveries": []}
        proposal = {"summary": "", "examples": []}
        resource = {"id": "r1", "title": "Data", "type": "dataset", "status": "unknown"}
        cases = [("project.json", "[]"), ("project.json", "not json"),
                 ("project.json", '{"name":"a","name":"a"}'), ("project.json", '{"name":"Research"}'), ("project.json", json.dumps({**project, "schema_version": 3})),
                 ("project.json", json.dumps({**project, "deliveries": ["../escape"]})),
                 ("project.json", json.dumps({**project, "deliveries": ["e1", "e1"]})),
                 ("project.json", json.dumps({**project, "current_evaluation": "../escape"})),
                 ("project.json", json.dumps({**project, "current_evaluation": "draft"})),
                 ("proposal.json", '{"unrelated":true}'),
                 ("proposal.json", json.dumps({**proposal, "revision": 1})),
                 ("proposal.json", json.dumps({**proposal, "confirmation": {}})),
                 ("proposal.json", json.dumps({**proposal, "sections": [{"title": "old format"}]})),
                 ("proposal.json", json.dumps({**proposal, "sources": [{"title": "x", "url": "javascript:alert(1)"}]})),
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
                         set(installer.TEMPLATES) | {".workspace", "evaluation", "data"})

    def test_required_parent_collision_is_preflighted(self):
        self.project.mkdir()
        (self.project / ".workspace").write_text("existing file")
        with self.assertRaisesRegex(ValueError, "File occupies required directory"):
            self.install()
        self.assertEqual(self.snapshot(self.project), {".workspace": b"existing file"})

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

    def test_updated_skill_and_modified_app_are_refused(self):
        self.install()
        (self.project / "proposal.json").unlink()
        # A later skill update must not replace the tools this project's evidence was produced with.
        (self.skill / "scripts/run.py").write_bytes((self.skill / "scripts/run.py").read_bytes() + b"\n# updated\n")
        builder.build(self.source)
        with self.assertRaisesRegex(ValueError, "upgrades are not supported"):
            self.install()
        self.assertFalse((self.project / "proposal.json").exists())
        self.assertNotIn(b"# updated", (self.project / ".workspace/app/run.py").read_bytes())
        shutil.copyfile(self.project / ".workspace/app/run.py", self.skill / "scripts/run.py")
        builder.build(self.source)
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

    def test_copied_skills_run_and_sibling_references_resolve_without_source(self):
        # What a skill installer delivers: the four folders, copied into an application's directory.
        skills = self.base / "home/.agents/skills"
        skills.mkdir(parents=True)
        for name in builder.SKILLS:
            shutil.copytree(self.source / builder.SKILLS_DIR / name, skills / name)
        shutil.rmtree(self.source)
        for name in ("init.py", "records.py", "run.py", "scout.py"):
            script = skills / "research-workspace/scripts" / name
            result = subprocess.run([sys.executable, "-E", "-s", "-B", str(script), "--help"],
                                    cwd=self.base, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout.lower())
        for name in ("tunetune-init", "build-evaluation", "run-experiments"):
            with self.subTest(skill=name):
                skill = skills / name / "SKILL.md"
                links = re.findall(r"\.\./research-workspace/[A-Za-z0-9_./-]+", skill.read_text(encoding="utf-8"))
                self.assertTrue(links, f"{name} must reference its sibling base skill")
                for link in links:
                    target = (skill.parent / link).resolve()
                    self.assertTrue(target.is_relative_to(skills / "research-workspace"), link)
                    self.assertTrue(target.is_file(), link)

    def test_initializer_cli_repeats_without_writing_into_the_skill(self):
        command = [sys.executable, "-E", "-s", str(self.skill / "scripts/init.py"), "--project", str(self.project)]
        before = self.snapshot(self.skill)
        for expected in ("Added", "already initialized"):
            result = subprocess.run(command, cwd=self.base, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(expected, result.stdout)
            self.assertEqual(self.snapshot(self.skill), before)
        self.assertFalse(list(self.skill.rglob("__pycache__")))

    def test_pinned_project_survives_skill_removal_and_move(self):
        result = subprocess.run([sys.executable, "-E", "-s", "-B", str(self.skill / "scripts/init.py"),
                                 "--project", str(self.project), "--name", "隔离项目"],
                                cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        shutil.rmtree(self.source)
        moved = self.base / "moved-research"
        self.project.rename(moved)
        records = moved / ".workspace/app/records.py"
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
                self.assertIn("isolated skill fixture", response.read().decode())
            with urlopen(url + "/api/state", timeout=5) as response:
                state = json.load(response)
            self.assertIsNone(state["error"])
            self.assertEqual(state["files"]["project.json"]["content"]["name"], "隔离项目")
            self.assertEqual(state["observations"]["items"], [])
        finally:
            process.terminate()
            process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
