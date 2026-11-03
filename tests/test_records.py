"""Format-2 record API tests using disposable synthetic research fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/research-workspace/scripts/records.py"
SPEC = importlib.util.spec_from_file_location("records_under_test", SCRIPT)
records = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(records)
STAMP = "2026-01-01T00:00:00Z"


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.tree = records.Tree(self.root)
        self.addCleanup(self.tree.close)
        self.source = self.base / "input.json"
        self.raw("project.json", dict(schema_version=3, name="Fixture", language="en", current_evaluation=None, deliveries=[]))
        self.raw("proposal.json", self.proposal())
        self.raw("resources.json", dict(items=[]))
        self.raw(".workspace/manifest.json", dict(schema_min=3, schema_max=3))

    def raw(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return target

    def put(self, path, value, **kwargs):
        self.source.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return records.write(self.tree, path, self.source, **kwargs)

    def sha(self, path):
        return records.digest(self.tree.read(path))

    def proposal(self, summary="Synthetic unittest fixture only"):
        return dict(summary=summary, sections=[], examples=[])

    def status(self, state, **details):
        return dict(state=state, updated_at=STAMP) | details

    def definition(self, version="v1"):
        return dict(version=version, description="Synthetic checks", rubric="Exact match", metrics=[
            dict(id="count", label="Fixture count", direction="maximize")], command=["python3", "score.py"])

    def package(self, path, files):
        source = self.base / ("package-" + path.replace("/", "-"))
        source.mkdir()
        for name, value in files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return records.freeze(self.tree, self.root, source, path)

    def experiment(self, ident="e1"):
        base = f"experiments/{ident}"
        snapshot = self.package(base + "/snapshot", {"code.py": b"# synthetic code\n"})
        self.raw("inputs/data.txt", b"synthetic data\n")
        config = dict(id=ident, title="Synthetic experiment", parent_experiment_id=None, hypothesis="Test a rule",
                      parameters={}, inputs=[dict(path="inputs/data.txt", sha256=self.sha("inputs/data.txt"))],
                      snapshot_sha256=snapshot["manifest_sha256"],
                      execution=dict(argv=["python3", base + "/snapshot/code.py"], cwd=".", environment={}, timeout_seconds=5))
        self.put(base + "/config.json", config, create=True)
        return config

    def model(self, ident="e1"):
        base = f"experiments/{ident}"
        self.raw(base + "/model/rule.txt", b"synthetic rule")
        status = self.status("succeeded", target=dict(kind="local", path=base + "/model/rule.txt", sha256=self.sha(base + "/model/rule.txt")))
        self.put(base + "/status.json", status, create=True)
        return status

    def fixture(self):
        evaluation = self.package("evaluation/v1", {
            "definition.json": self.definition(), "score.py": b"# synthetic scorer\n",
            "samples.jsonl": b'{"sample_id":"one","input":{"text":"test"},"reference":"answer","split":"test"}\n'})
        self.experiment()
        model = self.model()
        config = dict(id="r1", evaluation_version="v1", target_sha256=model["target"]["sha256"],
                      evaluation_sha256=evaluation["manifest_sha256"],
                      execution=dict(argv=["python3", "evaluation/v1/score.py"], cwd=".", environment={}, timeout_seconds=5))
        self.put("experiments/e1/evals/r1/config.json", config, create=True)
        project = records.read_record(self.tree, "project.json")
        self.put("project.json", dict(project, current_evaluation="v1", deliveries=["e1"]), expected=self.sha("project.json"))

    def outputs(self):
        return b'{"sample_id":"one","input":{"text":"test"},"output":"answer","reference":"answer","scores":{"count":1}}\n'

    def assert_error(self, fragment):
        report = records.validate(self.tree)
        self.assertFalse(report["valid"], report)
        self.assertTrue(any(fragment in e for e in report["errors"]), report)
        return report

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, timeout=10)

    def test_create_is_exclusive_and_atomic(self):
        path = "comparison/outputs.jsonl"
        result = self.put(path, b"", create=True)
        self.assertEqual(result, dict(path=path, sha256=self.sha(path)))
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.put(path, b"", create=True)
        self.assertEqual(self.tree.read(path), b"")
        self.assertEqual(list(self.root.rglob(".records-*")), [])

    def test_cas_mutable_records_replace_without_history(self):
        self.experiment()
        records_to_update = {
            "proposal.json": self.proposal("Revised"),
            "resources.json": dict(items=[]),
            "project.json": records.read_record(self.tree, "project.json"),
            "experiments/e1/analysis.json": dict(outcome="inconclusive", summary="More evidence needed"),
            "comparison/outputs.jsonl": b'{"sample_id":"one","input":"test","outputs":{"e1":"output"}}\n',
        }
        for path, value in records_to_update.items():
            if not self.tree.exists(path):
                self.put(path, value, create=True)
            before = self.tree.read(path)
            for expected in (None, "bad", "0" * 64):
                with self.subTest(path=path, expected=expected), self.assertRaises(ValueError):
                    self.put(path, value, expected=expected)
                self.assertEqual(self.tree.read(path), before)
            self.put(path, value, expected=self.sha(path))
        self.assertFalse((self.root / "history").exists())
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_all_final_states_and_configs_are_immutable(self):
        for state in records.FINAL:
            self.experiment(state)
            path = f"experiments/{state}/status.json"
            if state == "succeeded":
                self.model(state)
            else:
                self.put(path, self.status("running"), create=True)
                self.put(path, self.status(state), expected=self.sha(path))
            before = self.tree.read(path)
            with self.assertRaisesRegex(ValueError, "immutable"):
                self.put(path, self.status("running"), expected=self.sha(path))
            self.assertEqual(self.tree.read(path), before)
        path = "experiments/failed/config.json"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.put(path, records.read_record(self.tree, path), expected=self.sha(path))

    def test_finalization_preserves_process_facts_and_measurements(self):
        self.experiment()
        path = "experiments/e1/status.json"
        facts = dict(started_at=STAMP, completed_at=STAMP, returncode=0, timed_out=False, elapsed_seconds=0.5,
                     config_sha256=self.sha("experiments/e1/config.json"))
        self.put(path, self.status("completed", **facts), create=True)
        for key in facts:
            changed = dict(facts)
            del changed[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Preserve recorded fact"):
                self.put(path, self.status("cancelled", **changed), expected=self.sha(path))
        with self.assertRaisesRegex(ValueError, "backwards"):
            self.put(path, self.status("running", **facts), expected=self.sha(path))
        self.raw("experiments/e1/model/file", b"model")
        self.put(path, self.status("succeeded", **facts, target=dict(kind="local", path="experiments/e1/model/file",
                                  sha256=self.sha("experiments/e1/model/file"))), expected=self.sha(path))
        self.assertEqual({k: records.read_record(self.tree, path)[k] for k in facts}, facts)

    def test_success_requires_verified_model_and_declared_evaluation_outputs(self):
        self.fixture()
        path = "experiments/e1/evals/r1/status.json"
        self.put(path, self.status("completed"), create=True)
        for metrics in ({}, {"unknown": 1}):
            with self.assertRaises(ValueError):
                self.put(path, self.status("succeeded", metrics=metrics), expected=self.sha(path))
        with self.assertRaises((ValueError, OSError)):
            self.put(path, self.status("succeeded", metrics={"count": 1}), expected=self.sha(path))
        output_path = path.replace("status.json", "outputs.jsonl")
        self.put(output_path, b"", create=True)
        with self.assertRaisesRegex(ValueError, "requires outputs"):
            self.put(path, self.status("succeeded", metrics={"count": 1}), expected=self.sha(path))
        (self.root / output_path).unlink()
        self.put(output_path, self.outputs(), create=True)
        self.put(path, self.status("succeeded", metrics={"count": 1}), expected=self.sha(path))
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["unfinished"], [])
        for target in (path, output_path):
            with self.assertRaisesRegex(ValueError, "immutable"):
                self.put(target, self.tree.read(target), expected=self.sha(target))
        self.raw(output_path, b"")
        self.assert_error("requires outputs")

    def test_outputs_validate_samples_references_scores_and_coverage(self):
        self.fixture()
        path = "experiments/e1/evals/r1/outputs.jsonl"
        row = json.loads(self.outputs())
        for changes in ({"sample_id": "missing"}, {"input": "changed"}, {"reference": "wrong"},
                        {"scores": {"unknown": 1}}, {"scores": {"count": True}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.put(path, json.dumps(dict(row, **changes)).encode(), create=True)
        self.assertFalse(self.tree.exists(path))
        self.raw(path, self.outputs())
        (self.root / "experiments/e1/evals/r1/config.json").unlink()
        self.assert_error("experiments/e1/evals/r1/outputs.jsonl")

    def test_output_json_equality_preserves_boolean_types_and_nested_key_order(self):
        self.fixture()
        samples = [dict(sample_id="one", input={"flag": True}, reference=False),
                   dict(sample_id="two", input={"nested": [{"a": True, "b": [None, 2]}], "text": "test"},
                        reference={"a": False, "b": {"x": 1, "y": "yes"}})]
        def jsonl(rows):
            return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
        package = self.package("evaluation/v2", {"definition.json": self.definition("v2"),
                                                 "samples.jsonl": jsonl(samples)})
        base = "experiments/e1/evals/r1"
        config = records.read_record(self.tree, base + "/config.json")
        self.raw(base + "/config.json", dict(config, evaluation_version="v2", evaluation_sha256=package["manifest_sha256"]))
        rows = [dict(samples[0], output="answer"),
                dict(sample_id="two", input={"text": "test", "nested": [{"b": [None, 2], "a": True}]},
                     reference={"b": {"y": "yes", "x": 1}, "a": False}, output="answer")]
        output_path, status_path = base + "/outputs.jsonl", base + "/status.json"
        completed = self.status("completed")
        succeeded = self.status("succeeded", metrics={"count": 2})
        self.put(status_path, completed, create=True)
        for index, field, value in ((0, "input", {"flag": 1}), (0, "reference", 0),
                                    (1, "input", {"text": "test", "nested": [{"b": [None, 2], "a": 1}]}),
                                    (1, "reference", {"b": {"y": "yes", "x": True}, "a": False})):
            with self.subTest(index=index, field=field):
                bad = [dict(row) for row in rows]
                bad[index][field] = value
                with self.assertRaisesRegex(ValueError, f"Output {field} differs"):
                    self.put(output_path, jsonl(bad), create=True)
                self.assertFalse(self.tree.exists(output_path))
                self.raw(output_path, jsonl(bad))
                before = self.tree.read(status_path)
                with self.assertRaisesRegex(ValueError, f"Output {field} differs"):
                    self.put(status_path, succeeded, expected=self.sha(status_path))
                self.assertEqual(self.tree.read(status_path), before)
                self.raw(status_path, succeeded)
                report = self.assert_error(f"Output {field} differs")
                self.assertTrue(any(e.startswith(status_path + ":") for e in report["errors"]), report)
                self.raw(status_path, completed)
                (self.root / output_path).unlink()
        self.put(output_path, jsonl(rows), create=True)
        self.put(status_path, succeeded, expected=self.sha(status_path))
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)

    def test_failed_evaluation_freezes_measurements_even_if_outputs_missing(self):
        self.fixture()
        path = "experiments/e1/evals/r1/status.json"
        self.put(path, self.status("failed", returncode=7), create=True)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.put(path.replace("status.json", "outputs.jsonl"), self.outputs(), create=True)
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_partial_coverage_cannot_succeed_and_recorded_metrics_cannot_change(self):
        self.fixture()
        package = self.package("evaluation/v2", {"definition.json": self.definition("v2"),
            "samples.jsonl": self.tree.read("evaluation/v1/samples.jsonl") + b'{"sample_id":"two","input":0}\n'})
        base = "experiments/e1/evals/r1"
        config = records.read_record(self.tree, base + "/config.json")
        self.raw(base + "/config.json", dict(config, evaluation_version="v2", evaluation_sha256=package["manifest_sha256"]))
        self.put(base + "/outputs.jsonl", self.outputs(), create=True)
        self.put(base + "/status.json", self.status("completed", metrics={"count": 1}), create=True)
        with self.assertRaisesRegex(ValueError, "all samples"):
            self.put(base + "/status.json", self.status("succeeded", metrics={"count": 1}), expected=self.sha(base + "/status.json"))
        with self.assertRaisesRegex(ValueError, "Preserve recorded fact: metrics"):
            self.put(base + "/status.json", self.status("failed", metrics={"count": 2}), expected=self.sha(base + "/status.json"))

    def test_models_files_and_directories_must_remain_inside_own_experiment(self):
        self.experiment()
        path = "experiments/e1/status.json"
        for model_path in ("elsewhere/file", "experiments/e2/model/file", "experiments/e1/modelish/file", "../model"):
            with self.subTest(path=model_path), self.assertRaises(ValueError):
                self.put(path, self.status("succeeded", target=dict(kind="local", path=model_path, sha256="0" * 64)), create=True)
        with self.assertRaisesRegex(ValueError, "requires a model"):
            self.put(path, self.status("succeeded"), create=True)
        self.raw("experiments/e1/model/sub/weights", b"weights")
        with self.assertRaises(OSError):
            self.put(path, self.status("succeeded", target=dict(kind="local", path="experiments/e1/model", sha256="0" * 64)), create=True)
        result = self.cli("manifest", "--project", str(self.root), "--path", "experiments/e1/model")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = json.loads(result.stdout)
        self.assertEqual(result["manifest_sha256"], self.sha("experiments/e1/model/manifest.json"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            records.manifest(self.tree, "experiments/e1/model/sub")
        self.put(path, self.status("succeeded", target=dict(kind="local", path="experiments/e1/model", sha256=result["manifest_sha256"])), create=True)
        with self.assertRaisesRegex(ValueError, "already exists"):
            records.manifest(self.tree, "experiments/e1/model")
        with self.assertRaisesRegex(ValueError, "Final models are immutable"):
            records.manifest(self.tree, "experiments/e1/model/sub")
        self.assertFalse(self.tree.exists("experiments/e1/model/sub/manifest.json"))
        self.raw("experiments/e1/model/extra", b"unlisted")
        self.assert_error("Manifest file set differs")

    def test_delivery_and_comparison_references(self):
        self.experiment()
        project = records.read_record(self.tree, "project.json")
        for deliveries in (["missing"], ["e1"]):
            with self.assertRaises((ValueError, OSError)):
                self.put("project.json", dict(project, deliveries=deliveries), expected=self.sha("project.json"))
        self.model()
        self.put("project.json", dict(project, deliveries=["e1"]), expected=self.sha("project.json"))
        path = "comparison/outputs.jsonl"
        for output in ([], {"missing": "text"}, {"../e1": "text"}, {"e1": None}):
            with self.subTest(output=output), self.assertRaises((ValueError, OSError)):
                self.put(path, json.dumps(dict(sample_id="one", input="x", outputs=output)).encode(), create=True)
        self.put(path, b'{"sample_id":"one","input":"x","outputs":{"e1":""}}\n{"sample_id":"two","input":0,"outputs":{}}\n', create=True)
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_configs_and_parent_cycles_validate_references(self):
        self.fixture()
        self.experiment("e2")
        cases = [
            ("experiments/e1/config.json", "parent_experiment_id", "e1"),
            ("experiments/e1/config.json", "parent_experiment_id", "missing"),
            ("experiments/e1/config.json", "snapshot_sha256", "0" * 64),
            ("experiments/e1/evals/r1/config.json", "target_sha256", "0" * 64),
            ("experiments/e1/evals/r1/config.json", "evaluation_sha256", self.sha("evaluation/v1/definition.json")),
            ("experiments/e1/evals/r1/config.json", "evaluation_version", "missing"),
        ]
        for path, key, value in cases:
            before = self.tree.read(path)
            self.raw(path, dict(records.strict(before), **{key: value}))
            self.assert_error(path)
            self.raw(path, before)
        for ident, parent in (("e1", "e2"), ("e2", "e1")):
            path = f"experiments/{ident}/config.json"
            self.raw(path, dict(records.read_record(self.tree, path), parent_experiment_id=parent))
        self.assert_error("ancestry cycle")

    def test_input_and_model_hashes_and_directory_inputs_verified(self):
        self.fixture()
        for path in ("inputs/data.txt", "experiments/e1/snapshot/code.py", "experiments/e1/model/rule.txt", "evaluation/v1/score.py"):
            before = self.tree.read(path)
            self.raw(path, b"corrupt")
            self.assert_error("Hash mismatch")
            self.raw(path, before)
        records.verify_path_hash(self.tree, "evaluation/v1", self.sha("evaluation/v1/manifest.json"))
        with self.assertRaises(ValueError):
            records.verify_path_hash(self.tree, "evaluation/v1", "bad")

    def test_freeze_manifest_byte_hashes_executable_bits_and_exclusive_publication(self):
        source = self.base / "freeze-source"
        source.mkdir()
        script = source / "code.sh"
        script.write_text("#!/bin/sh\nprintf fixture\n")
        script.chmod(0o4755)
        path = "experiments/e1/snapshot"
        result = records.freeze(self.tree, self.root, source, path)
        self.assertEqual(result["manifest_sha256"], self.sha(path + "/manifest.json"))
        self.assertEqual((self.root / path / "code.sh").stat().st_mode & 0o7777, 0o711)
        self.assertEqual(subprocess.run([str(self.root / path / "code.sh")], capture_output=True).stdout, b"fixture")
        with self.assertRaises(FileExistsError):
            records.freeze(self.tree, self.root, source, path)
        records.verify_manifest(self.tree, path)
        self.raw(path + "/extra", b"extra")
        with self.assertRaisesRegex(ValueError, "file set differs"):
            records.verify_manifest(self.tree, path)

    def test_incomplete_freeze_has_no_manifest_and_cannot_be_reused(self):
        source = self.base / "freeze-source"
        source.mkdir()
        (source / "code.py").write_text("# fixture\n")
        with patch.object(self.tree, "publish", side_effect=OSError("Synthetic interruption")):
            with self.assertRaises(OSError):
                records.freeze(self.tree, self.root, source, "experiments/e1/snapshot")
        self.assertFalse(self.tree.exists("experiments/e1/snapshot/manifest.json"))
        with self.assertRaises(FileExistsError):
            records.freeze(self.tree, self.root, source, "experiments/e1/snapshot")

    def test_evaluation_requires_fixed_samples_and_freezes_them(self):
        self.fixture()
        for files in ({"definition.json": self.definition("v2")},
                      {"definition.json": self.definition("wrong"), "samples.jsonl": b""}):
            source = self.base / "invalid-evaluation"
            source.mkdir(exist_ok=True)
            for name, value in files.items():
                (source / name).write_bytes(value if isinstance(value, bytes) else records.encoded(value))
            with self.assertRaises(ValueError):
                records.freeze(self.tree, self.root, source, "evaluation/v2")
            self.assertFalse(self.tree.exists("evaluation/v2"))
        for leaf in ("definition.json", "samples.jsonl"):
            path = "evaluation/v1/" + leaf
            with self.assertRaisesRegex(ValueError, "immutable"):
                self.put(path, self.tree.read(path), expected=self.sha(path))
        self.put("evaluation/draft/definition.json", self.definition("v2"), create=True)
        self.put("evaluation/draft/samples.jsonl", b"", create=True)
        self.put("evaluation/draft/samples.jsonl", b'{"sample_id":"x","input":[] }\n', expected=self.sha("evaluation/draft/samples.jsonl"))
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_manifest_rejects_bad_shape_paths_duplicates_and_symlinks(self):
        self.fixture()
        path = "evaluation/v1/manifest.json"
        original = records.read_record(self.tree, "evaluation/v1/definition.json")
        entry = dict(path="definition.json", sha256=self.sha("evaluation/v1/definition.json"))
        for value in ({"files": []}, {"files": [entry, entry]}, {"files": [dict(entry, path="../outside")]},
                      {"files": [dict(entry, sha256="bad")]}, {"files": [dict(entry, path="manifest.json")]}, []):
            self.raw(path, value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                records.verify_manifest(self.tree, "evaluation/v1")
        self.assertEqual(records.read_record(self.tree, "evaluation/v1/definition.json"), original)

    def test_proposal_resources_and_monitor_contract(self):
        self.put("proposal.json", dict(self.proposal(), sections=[dict(title="Use", body="Daily")],
                 examples=[dict(id="x", input={"text": "test"}, expected_output="result")],
                 feasibility=dict(verdict="conditional", reason="Need data")), expected=self.sha("proposal.json"))
        resource = dict(id="data", title="Data", type="dataset", status="unknown")
        for status in ("ready", "missing", "changed", "busy", "unknown"):
            self.put("resources.json", dict(items=[dict(resource, status=status)]), expected=self.sha("resources.json"))
        for kind in ("file", "memory", "nvidia_gpu", "python"):
            records.shape("resources.json", records.encoded(dict(items=[dict(resource, monitor=dict(kind=kind, index=0))])))
        for changes in ({"status": "available"}, {"path": "../x"}, {"path": "data", "location": "remote"},
                        {"location": ""}, {"size": 1}, {"monitor": {"kind": "shell"}},
                        {"monitor": {"kind": "file", "command": "touch file"}},
                        {"monitor": {"kind": "python", "index": True}}, {"monitor": {"kind": "memory", "index": -1}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.put("resources.json", dict(items=[dict(resource, **changes)]), expected=self.sha("resources.json"))
        self.put("resources.json", dict(items=[dict(resource, location="https://example.org/not-read")]), expected=self.sha("resources.json"))
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_strict_json_types_and_obsolete_fields_rejected(self):
        self.experiment()
        config = records.read_record(self.tree, "experiments/e1/config.json")
        cases = [
            ("proposal.json", b'[]'), ("proposal.json", b'{"summary":1,"summary":2}'),
            ("proposal.json", b'{"summary":NaN}'), ("proposal.json", b'{"summary":1e999}'),
            ("proposal.json", self.proposal() | {"revision": 1}),
            ("proposal.json", self.proposal() | {"confirmation": {}}),
            ("experiments/e1/config.json", dict(config, id="wrong")),
            ("experiments/e1/config.json", dict(config, model="old field")),
            ("experiments/e1/config.json", dict(config, parameters=[])),
            ("experiments/e1/config.json", dict(config, inputs=[dict(location="external", sha256="0" * 64)])),
            ("experiments/e1/status.json", self.status("running", updated_at="2026-01-01")),
            ("experiments/e1/status.json", self.status("succeeded", returncode=7)),
            ("experiments/e1/status.json", self.status("completed", timed_out=True)),
            ("experiments/e1/status.json", self.status("failed", returncode=True)),
            ("experiments/e1/status.json", self.status("failed", elapsed_seconds=-1)),
            ("evaluation/v1/definition.json", dict(self.definition(), datasets=[])),
            ("evaluation/draft/samples.jsonl", b'{"sample_id":"x","input":0}\n' * 2),
            ("comparison/outputs.jsonl", b'{"sample_id":"x","input":0,"outputs":{"e1":"a","e1":"b"}}'),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                records.shape(path, value if isinstance(value, bytes) else records.encoded(value))
        for timeout in (None, 0, -1, True, "10", 10 ** 400):
            with self.assertRaises(ValueError):
                records.shape("experiments/e1/config.json", records.encoded(dict(config, execution=dict(config["execution"], timeout_seconds=timeout))))
        for execution in (dict(config["execution"], argv=[""]), dict(config["execution"], cwd="../outside"),
                          dict(config["execution"], environment={"X": 1}), dict(config["execution"], environment={"X=Y": "z"})):
            with self.assertRaises(ValueError):
                records.shape("experiments/e1/config.json", records.encoded(dict(config, execution=execution)))
        utf16 = records.encoded(self.proposal()).decode().encode("utf-16")
        with self.assertRaises(ValueError):
            records.shape("proposal.json", utf16)

    def test_incompatible_project_and_legacy_paths_rejected_without_migration(self):
        project = records.read_record(self.tree, "project.json")
        self.raw("project.json", dict(project, schema_version=1))
        self.assert_error("Unsupported schema_version")
        with self.assertRaisesRegex(ValueError, "Unsupported schema_version"):
            self.put("proposal.json", self.proposal("changed"), expected=self.sha("proposal.json"))
        for path in ("goal.json", "review.md", "candidates.json", "workspace.json", "feedback/incoming/f1.json",
                     "assessments/a1/config.json", "acceptance/a1/outputs.jsonl", "releases/r1.json",
                     "experiments/e1/receipt.json", "experiments/e1/result.json", "experiments/e1/artifacts.json",
                     "experiments/e1/judgment.json", "experiments/e1/analysis.md", "evaluation/versions/v1/definition.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.put(path, b"{}", create=True)
        self.assertFalse((self.root / "history").exists())

    def test_installed_metadata_rejects_all_mutators_before_any_project_change(self):
        source = self.base / "freeze-source"
        source.mkdir()
        (source / "code.py").write_bytes(b"# fixture\n")
        self.raw("experiments/e1/model/weights", b"fixture")
        for metadata in (dict(schema_min=2, schema_max=2), dict(schema_min=1, schema_max=3),
                         dict(schema_min=3, schema_max=4), dict(schema_min=True, schema_max=3),
                         dict(schema_min=3.0, schema_max=3), dict(schema_min=3)):
            with self.subTest(metadata=metadata):
                self.raw(".workspace/manifest.json", metadata)
                before = {p.relative_to(self.root): p.read_bytes() if p.is_file() else None
                          for p in self.root.rglob("*")}
                for operation in (
                    lambda: self.put("proposal.json", self.proposal("changed"), expected=self.sha("proposal.json")),
                    lambda: self.put("comparison/outputs.jsonl", b"", create=True),
                    lambda: records.freeze(self.tree, self.root, source, "experiments/e1/snapshot"),
                    lambda: records.manifest(self.tree, "experiments/e1/model"),
                ):
                    with self.assertRaisesRegex(ValueError, "Incompatible kit schema range"):
                        operation()
                    after = {p.relative_to(self.root): p.read_bytes() if p.is_file() else None
                             for p in self.root.rglob("*")}
                    self.assertEqual(after, before)
                self.assert_error("Incompatible kit schema range")
        self.assertFalse(self.tree.exists(".workspace/runtime"))

    def test_uninstalled_fresh_project_can_write_and_freeze(self):
        (self.root / ".workspace/manifest.json").unlink()
        self.put("proposal.json", self.proposal("changed"), expected=self.sha("proposal.json"))
        self.package("experiments/e1/snapshot", {"code.py": b"# fixture\n"})
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertIn("Missing workspace manifest", report["warnings"][0])

    def test_tree_symlink_root_parent_target_source_and_lock_safety(self):
        alias = self.base / "project-link"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            records.Tree(alias)
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "experiments").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.put("experiments/e1/analysis.json", dict(outcome="keep", summary="test"), create=True)
        target = outside / "proposal.json"
        target.write_bytes(records.encoded(self.proposal()))
        (self.root / "proposal.json").unlink()
        (self.root / "proposal.json").symlink_to(target)
        with self.assertRaises(OSError):
            self.tree.read("proposal.json")
        with self.assertRaises(ValueError):
            self.put("proposal.json", self.proposal(), create=True)
        with self.assertRaises(OSError):
            self.put("proposal.json", self.proposal(), expected=records.digest(target.read_bytes()))
        self.assertEqual(target.read_bytes(), records.encoded(self.proposal()))
        self.source.write_bytes(records.encoded(self.proposal()))
        source_alias = self.base / "source-link"
        source_alias.symlink_to(self.source)
        with self.assertRaises(OSError):
            records.write(self.tree, "proposal.json", source_alias, create=True)
        (self.root / "proposal.json").unlink()
        lock = self.root / ".workspace/runtime/records.lock"
        lock.unlink()
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            self.put("proposal.json", self.proposal(), create=True)
        self.assertEqual(list(outside.iterdir()), [target])

    def test_freeze_rejects_overlap_symlinks_and_special_files(self):
        destination = self.root / "experiments/e1/snapshot"
        destination.mkdir(parents=True)
        for source in (destination, self.root, destination / "child"):
            with self.assertRaisesRegex(ValueError, "overlap"):
                records.freeze(self.tree, self.root, source, "experiments/e1/snapshot")
        source = self.base / "unsafe-source"
        source.mkdir()
        (source / "file").write_bytes(b"data")
        alias = self.base / "source-alias"
        alias.symlink_to(source, target_is_directory=True)
        with self.assertRaises(OSError):
            records.freeze(self.tree, self.root, alias, "experiments/e2/snapshot")
        (source / "link").symlink_to(source / "file")
        with self.assertRaises(ValueError):
            records.freeze(self.tree, self.root, source, "experiments/e2/snapshot")
        (source / "link").unlink()
        os.mkfifo(source / "pipe")
        with self.assertRaises(ValueError):
            records.freeze(self.tree, self.root, source, "experiments/e2/snapshot")
        self.assertFalse(self.tree.exists("experiments/e2/snapshot"))
        os.mkfifo(self.root / "pipe")
        with self.assertRaises(ValueError):
            self.tree.read("pipe")

    def test_traversal_and_unsafe_segments_rejected_without_mutation(self):
        for path in ("../proposal.json", "experiments/../proposal.json", "/proposal.json", "./proposal.json", "a//b", "a\\b", "a:b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.tree.read(path)
            with self.assertRaises(ValueError):
                self.put(path, self.proposal(), create=True)
        child = self.root / "child"
        child.mkdir()
        with self.assertRaises(ValueError):
            records.Tree(str(child) + "/..")
        with self.assertRaises(ValueError):
            with self.tree.directory([".."]):
                pass

    def test_resource_local_symlinks_rejected_external_locations_not_read(self):
        (self.root / "alias").symlink_to(self.base, target_is_directory=True)
        self.raw("resources.json", dict(items=[dict(id="x", title="x", type="file", status="unknown", path="alias")]))
        self.assert_error("Resource path")
        self.raw("resources.json", dict(items=[dict(id="x", title="x", type="file", status="unknown", location=str(self.base))]))
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_flock_contention_across_processes_and_release(self):
        self.source.write_bytes(records.encoded(self.proposal("updated")))
        args = ("write", "--project", str(self.root), "--path", "proposal.json", "--input", str(self.source),
                "--expected-sha256", self.sha("proposal.json"))
        with self.tree.locked():
            result = self.cli(*args)
            self.assertEqual(result.returncode, 1)
            self.assertIn("error", json.loads(result.stderr))
        self.assertEqual(self.cli(*args).returncode, 0)

    def test_atomic_replace_failure_leaves_previous_bytes_and_no_temporary(self):
        before = self.tree.read("proposal.json")
        with patch.object(records.os, "replace", side_effect=OSError("Synthetic publication failure")):
            with self.assertRaises(OSError):
                self.put("proposal.json", self.proposal("new"), expected=self.sha("proposal.json"))
        self.assertEqual(self.tree.read("proposal.json"), before)
        self.assertEqual(list(self.root.rglob(".records-*")), [])

    def test_cli_validation_hash_help_and_bad_json(self):
        for args in (("--help",), ("write", "--help"), ("freeze", "--help"), ("validate", "--help"), ("manifest", "--help")):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.fixture()
        result = self.cli("validate", "--project", str(self.root))
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"valid", "errors", "warnings", "unfinished"})
        self.assertEqual(report["unfinished"], ["experiments/e1/evals/r1"])
        self.source.write_bytes(b'{"summary":')
        before = self.tree.read("proposal.json")
        result = self.cli("write", "--project", str(self.root), "--path", "proposal.json", "--input", str(self.source),
                          "--expected-sha256", self.sha("proposal.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", json.loads(result.stderr))
        self.assertEqual(self.tree.read("proposal.json"), before)
        result = self.cli("hash", "--project", str(self.root), "--path", "proposal.json")
        self.assertEqual(json.loads(result.stdout)["sha256"], self.sha("proposal.json"))
        self.raw(".workspace/manifest.json", dict(schema_min=1, schema_max=1))
        self.assert_error("Incompatible kit schema range")
        self.raw("experiments/e1/evals/r1/config.json", b"null")
        result = self.cli("validate", "--project", str(self.root))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
