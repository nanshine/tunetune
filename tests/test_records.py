"""Record API tests using disposable, explicitly synthetic research fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/research-workspace/scripts/records.py"
SPEC = importlib.util.spec_from_file_location("records_under_test", SCRIPT)
records = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(records)
STAMP = "2026-01-01T00:00:00Z"


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS /var is a symlink: resolve before passing any root to Tree.
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.tree = records.Tree(self.root)
        self.addCleanup(self.tree.close)
        self.source = self.base / "input.json"

    def raw(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return target

    def put(self, path, value, **kwargs):
        self.source.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return records.write(self.tree, path, self.source, **kwargs)

    def sha(self, path):
        return hashlib.sha256((self.root / path).read_bytes()).hexdigest()

    def goal(self, revision=1):
        return dict(revision=revision, context="Synthetic unittest fixture only",
                    expected_result="No real research performed", examples=[], sources=[])

    def status(self, state):
        return dict(state=state, updated_at=STAMP)

    def fixture(self):
        self.raw("project.json", dict(schema_version=1, name="unit-test", language="en", current_evaluation="v1"))
        self.raw("goal.json", self.goal())
        self.raw("resources.json", dict(items=[]))
        self.raw("candidates.json", dict(items=[]))
        self.raw(".workspace/manifest.json", dict(schema_min=1, schema_max=1))
        definition = dict(version="v1", description="Synthetic test definition", metrics=[
            dict(id="count", label="Fixture count", direction="maximize")], datasets=[])
        source = self.base / "evaluation-source"
        source.mkdir()
        (source / "definition.json").write_bytes(records.encoded(definition))
        records.freeze(self.tree, self.root, source, "evaluation/versions/v1")
        self.raw("inputs/code.py", b"# Test fixture, never executed.\n")
        self.raw("inputs/data.txt", b"synthetic sample\n")
        self.raw("artifacts/fixture.txt", b"synthetic artifact, not a trained model\n")
        execution = dict(argv=["python3", "inputs/code.py"], cwd=".", environment={})
        self.raw("experiments/e1/config.json", dict(
            id="e1", title="Synthetic experiment", parent_experiment_id=None,
            goal_revision=1, evaluation_version="v1", execution=execution,
            fixed_inputs=dict(code=[dict(path="inputs/code.py", sha256=self.sha("inputs/code.py"))],
                              data=[dict(path="inputs/data.txt", sha256=self.sha("inputs/data.txt"))],
                              starting_artifact=None, parameters={}, environment={})))
        self.raw("experiments/e1/status.json", self.status("running"))
        self.raw("experiments/e1/artifacts.json", dict(items=[dict(
            id="a1", path="artifacts/fixture.txt", sha256=self.sha("artifacts/fixture.txt"))]))
        self.raw("assessments/a1/config.json", dict(
            id="a1", experiment_id="e1", artifact_id="a1", evaluation_version="v1",
            artifact_sha256=self.sha("artifacts/fixture.txt"),
            evaluation_sha256=self.sha("evaluation/versions/v1/definition.json"), execution=execution))
        self.raw("assessments/a1/status.json", self.status("running"))

    def assert_error(self, fragment):
        report = records.validate(self.tree)
        self.assertFalse(report["valid"], report)
        self.assertTrue(any(fragment in e for e in report["errors"]), report)
        return report

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=10)

    def test_create_is_exclusive_and_returns_actual_hash(self):
        result = self.put("goal.json", self.goal(), create=True)
        before = self.tree.read("goal.json")
        self.assertEqual(result, dict(path="goal.json", sha256=self.sha("goal.json")))
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.put("goal.json", self.goal(2), create=True)
        self.assertEqual(self.tree.read("goal.json"), before)
        self.assertEqual(list(self.root.rglob(".records-*")), [])

    def test_expected_hash_required_and_conflict_is_lossless(self):
        self.raw("goal.json", self.goal())
        before = self.tree.read("goal.json")
        for expected in (None, "bad", "0" * 64):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                self.put("goal.json", self.goal(2), expected=expected)
            self.assertEqual(self.tree.read("goal.json"), before)
            self.assertFalse((self.root / "history").exists())

    def test_goal_revision_and_history(self):
        self.raw("goal.json", self.goal())
        before = self.tree.read("goal.json")
        for revision in (1, 3):
            with self.assertRaisesRegex(ValueError, "increase by one"):
                self.put("goal.json", self.goal(revision), expected=self.sha("goal.json"))
        self.put("goal.json", self.goal(2), expected=self.sha("goal.json"))
        self.assertEqual(self.tree.read("history/goals/1.json"), before)
        self.put("goal.json", self.goal(3), expected=self.sha("goal.json"))
        self.assertEqual(records.strict(self.tree.read("history/goals/2.json"))["revision"], 2)

    def test_history_conflict_is_lossless(self):
        self.raw("goal.json", self.goal())
        self.raw("history/goals/1.json", self.goal(7))
        before = self.tree.read("goal.json")
        with self.assertRaisesRegex(ValueError, "History conflict"):
            self.put("goal.json", self.goal(2), expected=self.sha("goal.json"))
        self.assertEqual(self.tree.read("goal.json"), before)

    def test_review_and_analysis_preserve_each_history(self):
        for path, history in (("review.md", "history/reviews"),
                              ("experiments/e1/analysis.md", "history/analyses/e1")):
            with self.subTest(path=path):
                self.put(path, b"first\n", create=True)
                self.put(path, b"second\n", expected=self.sha(path))
                self.put(path, b"third\n", expected=self.sha(path))
                self.assertEqual(sorted(p.read_bytes() for p in (self.root / history).glob("*.md")),
                                 [b"first\n", b"second\n"])
                self.assertEqual(self.tree.read(path), b"third\n")

    def test_running_to_each_terminal_then_immutable(self):
        for state in records.FINAL:
            path = f"experiments/{state}/status.json"
            self.put(path, self.status("running"), create=True)
            self.put(path, self.status(state), expected=self.sha(path))
            before = self.tree.read(path)
            with self.assertRaisesRegex(ValueError, "immutable"):
                self.put(path, self.status("running"), expected=self.sha(path))
            self.assertEqual(self.tree.read(path), before)

    def test_assessment_without_result_is_unfinished(self):
        self.fixture()
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(set(report["unfinished"]), {"experiments/e1", "assessments/a1"})
        with self.assertRaisesRegex(ValueError, "Invalid execution state"):
            self.put("assessments/a1/status.json", self.status("succeeded"),
                     expected=self.sha("assessments/a1/status.json"))

    def test_result_takes_priority_and_freezes_assessment(self):
        self.fixture()
        self.put("assessments/a1/result.json", dict(state="failed", metrics={}, completed_at=STAMP), create=True)
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertNotIn("assessments/a1", report["unfinished"])
        self.assertEqual(records.strict(self.tree.read("assessments/a1/status.json"))["state"], "running")
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.put("assessments/a1/status.json", self.status("pending"),
                     expected=self.sha("assessments/a1/status.json"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.put("assessments/a1/result.json", dict(state="cancelled", metrics={}, completed_at=STAMP),
                     expected=self.sha("assessments/a1/result.json"))

    def test_success_requires_outputs_and_known_metrics(self):
        self.fixture()
        result = dict(state="succeeded", metrics={"count": 1}, completed_at=STAMP)
        self.raw("assessments/a1/result.json", result)
        self.assert_error("Successful assessment requires outputs")
        self.raw("assessments/a1/outputs.jsonl", b'{"sample_id":"fixture","input":"test","output":"test"}\n')
        self.assertTrue(records.validate(self.tree)["valid"])
        result["metrics"] = {"unknown": 1}
        self.raw("assessments/a1/result.json", result)
        self.assert_error("Unknown metric IDs")

    def test_freeze_manifest_actual_hashes_and_no_overwrite(self):
        self.fixture()
        path = "experiments/e1/snapshot"
        source = self.base / "snapshot-source"
        source.mkdir()
        (source / "code.py").write_bytes(b"# synthetic snapshot\n")
        (source / "nested").mkdir()
        (source / "nested/data").write_bytes(b"test\n")
        result = records.freeze(self.tree, self.root, source, path)
        manifest = self.tree.read(path + "/manifest.json")
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(manifest).hexdigest())
        self.assertEqual(result["files"], 2)
        for item in records.strict(manifest)["files"]:
            self.assertEqual(item["sha256"], self.sha(path + "/" + item["path"]))
        with self.assertRaises(FileExistsError):
            records.freeze(self.tree, self.root, source, path)
        self.assertEqual(self.tree.read(path + "/manifest.json"), manifest)
        self.assertTrue(records.validate(self.tree)["valid"])
        self.raw(path + "/code.py", b"corrupt\n")
        self.assert_error("Hash mismatch")

    def test_manifest_rejects_unlisted_file(self):
        self.fixture()
        self.raw("evaluation/versions/v1/extra.txt", b"extra")
        self.assert_error("Manifest file set differs")

    def test_freeze_rejects_overlap_and_source_symlinks(self):
        destination = self.root / "experiments/e1/snapshot"
        destination.mkdir(parents=True)
        for source in (destination, self.root, destination / "child"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "overlap"):
                records.freeze(self.tree, self.root, source, "experiments/e1/snapshot")
        source = self.base / "freeze-source"
        source.mkdir()
        (source / "file").write_bytes(b"data")
        alias = self.base / "source-link"
        alias.symlink_to(source, target_is_directory=True)
        with self.assertRaises(OSError):
            records.freeze(self.tree, self.root, alias, "experiments/e2/snapshot")
        (source / "link").symlink_to(source / "file")
        with self.assertRaisesRegex(ValueError, "Not a regular file"):
            records.freeze(self.tree, self.root, source, "experiments/e2/snapshot")
        self.assertFalse((self.root / "experiments/e2/snapshot").exists())

    def test_symlink_project_and_parent_paths_rejected(self):
        alias = self.base / "project-link"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            records.Tree(alias)
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "experiments").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.put("experiments/e1/analysis.md", b"test", create=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_target_read_create_and_update_rejected(self):
        target = self.base / "outside.json"
        target.write_bytes(records.encoded(self.goal()))
        (self.root / "goal.json").symlink_to(target)
        before = target.read_bytes()
        with self.assertRaises(OSError):
            self.tree.read("goal.json")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.put("goal.json", self.goal(2), create=True)
        with self.assertRaises(OSError):
            self.put("goal.json", self.goal(2), expected=hashlib.sha256(before).hexdigest())
        self.assertEqual(target.read_bytes(), before)
        self.assertTrue((self.root / "goal.json").is_symlink())

    def test_symlink_lock_rejected(self):
        target = self.base / "outside.lock"
        target.write_bytes(b"untouched")
        runtime = self.root / ".workspace/runtime"
        runtime.mkdir(parents=True)
        (runtime / "records.lock").symlink_to(target)
        with self.assertRaises(OSError):
            self.put("goal.json", self.goal(), create=True)
        self.assertEqual(target.read_bytes(), b"untouched")
        self.assertFalse((self.root / "goal.json").exists())

    def test_write_source_symlink_must_be_rejected(self):
        self.source.write_bytes(records.encoded(self.goal()))
        alias = self.base / "input-link.json"
        alias.symlink_to(self.source)
        with self.assertRaises((OSError, ValueError)):
            records.write(self.tree, "goal.json", alias, create=True)
        self.assertFalse((self.root / "goal.json").exists())

    def test_relative_traversal_rejected_without_mutation(self):
        for path in ("../goal.json", "experiments/../goal.json", "/goal.json", "./goal.json", "a//b", "a\\b"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.tree.read(path)
                with self.assertRaises(ValueError):
                    self.put(path, self.goal(), create=True)
        with self.assertRaises(ValueError):
            records.freeze(self.tree, self.root, self.base, "experiments/../snapshot")
        self.assertFalse((self.root / "goal.json").exists())

    def test_project_root_dotdot_must_be_rejected(self):
        child = self.root / "child"
        child.mkdir()
        with self.assertRaises((OSError, ValueError)):
            tree = records.Tree(str(child) + "/..")
            tree.close()

    def test_flock_contention_across_processes_and_release(self):
        self.source.write_bytes(records.encoded(self.goal()))
        args = ("write", "--project", str(self.root), "--path", "goal.json",
                "--input", str(self.source), "--create")
        with self.tree.locked():
            result = self.cli(*args)
            self.assertEqual(result.returncode, 1, result)
            self.assertIn("error", json.loads(result.stderr))
            self.assertFalse((self.root / "goal.json").exists())
        self.assertEqual(self.cli(*args).returncode, 0)

    def test_structure_and_strict_json_rejected(self):
        cases = [
            ("goal.json", b"{}"), ("goal.json", b"[]"),
            ("goal.json", b'{"revision":1,"revision":2}'),
            ("goal.json", b'{"revision":NaN}'), ("goal.json", b'{"revision":1e999}'),
            ("goal.json", dict(self.goal(), revision=True)),
            ("goal.json", dict(self.goal(), examples="not a list")),
            ("experiments/e1/status.json", dict(state="running", updated_at="2026-01-01")),
            ("assessments/a1/result.json", dict(state="failed", metrics={"count": True}, completed_at=STAMP)),
            ("assessments/a1/config.json", dict(id="wrong", experiment_id="e1", artifact_id="a1", evaluation_version="v1")),
            ("assessments/a1/outputs.jsonl", b'{"sample_id":"x","input":0,"output":0}\n' * 2),
            ("acceptance/a1/outputs.jsonl", b'{"sample_id":"x","input":0,"output":0}\n'),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value), self.assertRaises((ValueError, TypeError)):
                self.put(path, value, create=True)
            self.assertFalse((self.root / path).exists())

    def test_fixed_input_and_artifact_hashes_verified(self):
        self.fixture()
        for path in ("inputs/code.py", "inputs/data.txt", "artifacts/fixture.txt"):
            with self.subTest(path=path):
                before = self.tree.read(path)
                self.raw(path, b"damaged")
                self.assert_error("Hash mismatch")
                self.raw(path, before)
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_references_and_goal_history_validation(self):
        self.fixture()
        self.put("goal.json", self.goal(2), expected=self.sha("goal.json"))
        self.assertTrue(records.validate(self.tree)["valid"])
        cases = [
            ("project.json", "current_evaluation", "missing", "Current evaluation"),
            ("experiments/e1/config.json", "parent_experiment_id", "e1", "Invalid parent"),
            ("experiments/e1/config.json", "evaluation_version", "missing", "Missing evaluation version"),
            ("assessments/a1/config.json", "experiment_id", "missing", "Missing experiment"),
            ("assessments/a1/config.json", "artifact_id", "missing", "Missing artifact"),
            ("assessments/a1/config.json", "artifact_sha256", "0" * 64, "Artifact reference hash differs"),
            ("assessments/a1/config.json", "evaluation_sha256", "0" * 64, "Hash mismatch"),
        ]
        for path, key, value, error in cases:
            with self.subTest(key=key):
                before = self.tree.read(path)
                obj = records.strict(before)
                obj[key] = value
                self.raw(path, obj)
                self.assert_error(error)
                self.raw(path, before)
        (self.root / "history/goals/1.json").unlink()
        self.assert_error("experiments/e1/config.json: [Errno 2]")

    def test_feedback_staleness_and_handling(self):
        self.fixture()
        self.raw("feedback/incoming/f1.json", dict(
            id="f1", kind="comment", text="Synthetic feedback", target="goal.json",
            target_sha256=self.sha("goal.json"), source="unittest", created_at=STAMP))
        report = records.validate(self.tree)
        self.assertEqual(report["unhandled_feedback"], ["f1"])
        self.assertEqual(report["warnings"], [])
        self.put("goal.json", self.goal(2), expected=self.sha("goal.json"))
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertTrue(any("stale feedback target" in w for w in report["warnings"]))
        for disposition, unhandled in (("adopted", []), ("rejected", []), ("deferred", ["f1"]), ("question", ["f1"])):
            self.raw("feedback/handled/h1.json", dict(id="h1", feedback_id="f1", disposition=disposition,
                                                    reason="Fixture decision", changes=[]))
            self.assertEqual(records.validate(self.tree)["unhandled_feedback"], unhandled)
        self.raw("feedback/handled/h2.json", dict(id="h2", feedback_id="f1", disposition="adopted",
                                                reason="Duplicate fixture decision", changes=[]))
        self.assertEqual(records.validate(self.tree)["unhandled_feedback"], ["f1"])
        self.raw("feedback/handled/missing.json", dict(id="missing", feedback_id="absent", disposition="rejected",
                                                     reason="Fixture", changes=[]))
        self.assert_error("Missing original feedback")

    def test_feedback_response_requires_request(self):
        self.fixture()
        self.raw("feedback/responses/r1.json", dict(id="r1", kind="answer", text="Test", target=None,
                 target_sha256=None, source="unittest", created_at=STAMP, request_id="q1"))
        self.assert_error("Missing feedback request")
        self.raw("feedback/requests/q1.json", dict(id="q1", title="Test", prompt="Test?", options=[]))
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_empty_success_or_orphan_results_are_not_valid(self):
        self.fixture()
        self.raw("assessments/a1/result.json", dict(state="succeeded", metrics={}, completed_at=STAMP))
        self.raw("assessments/a1/outputs.jsonl", b"")
        self.assert_error("Successful assessment requires outputs")
        self.raw("assessments/a1/outputs.jsonl", b'{"sample_id":"x","input":"x","output":"x"}\n')
        self.assert_error("all declared metrics")
        (self.root / "assessments/a1/config.json").unlink()
        self.assert_error("Orphan record")

    def test_corrupt_goal_history_is_reported_not_raised(self):
        self.fixture()
        config = records.strict(self.tree.read("experiments/e1/config.json"))
        config["goal_revision"] = 2
        self.raw("experiments/e1/config.json", config)
        for invalid in (b"null", b"[]", b"{}"):
            self.raw("history/goals/2.json", invalid)
            self.assert_error("experiments/e1/config.json")
            result = self.cli("validate", "--project", str(self.root))
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["valid"])
            self.assertNotIn("Traceback", result.stderr)

    def test_freeze_retains_executable_bits_without_special_permissions(self):
        source = self.base / "executable-source"
        source.mkdir()
        script = source / "run.sh"
        script.write_text("#!/bin/sh\nprintf 'fixture'\n")
        script.chmod(0o4755)
        records.freeze(self.tree, self.root, source, "experiments/e1/snapshot")
        frozen = self.root / "experiments/e1/snapshot/run.sh"
        self.assertEqual(frozen.stat().st_mode & 0o7777, 0o711)
        result = subprocess.run([str(frozen)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "fixture")

    def test_cli_help_and_bad_json_leave_existing_record_untouched(self):
        for args in (("--help",), ("write", "--help"), ("freeze", "--help"), ("validate", "--help"), ("hash", "--help")):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout)
        self.raw("goal.json", self.goal())
        before = self.tree.read("goal.json")
        self.source.write_bytes(b'{"revision":')
        result = self.cli("write", "--project", str(self.root), "--path", "goal.json", "--input",
                          str(self.source), "--expected-sha256", self.sha("goal.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", json.loads(result.stderr))
        self.assertEqual(self.tree.read("goal.json"), before)
        self.assertFalse((self.root / "history").exists())
        self.assertEqual(list(self.root.rglob(".records-*")), [])
        result = self.cli("hash", "--project", str(self.root), "--path", "goal.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["sha256"], self.sha("goal.json"))


if __name__ == "__main__":
    unittest.main()
