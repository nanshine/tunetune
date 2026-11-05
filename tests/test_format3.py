"""Format-3 integration checks with temporary projects and a simulated API adapter."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/research-workspace/scripts"
SPEC = importlib.util.spec_from_file_location("format3_records", SCRIPTS / "records.py")
records = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(records)
with patch.dict(sys.modules, records=records):
    SPEC = importlib.util.spec_from_file_location("format3_runner", SCRIPTS / "run.py")
    runner = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(runner)
STAMP = "2026-11-03T00:00:00Z"


class Format3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.tree = records.Tree(self.root)
        self.addCleanup(self.tree.close)
        self.raw("project.json", dict(schema_version=4, name="Fixture", language="en", current_evaluation=None, deliveries=[]))
        self.raw("proposal.json", dict(summary="Fixture", examples=[]))
        self.raw("resources.json", dict(items=[]))
        self.raw(".workspace/manifest.json", dict(schema_min=4, schema_max=4))

    def raw(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return target

    def sha(self, path):
        return records.digest(self.tree.read(path))

    def write(self, path, value):
        source = self.base / "write.json"
        source.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        exists = self.tree.exists(path)
        return records.write(self.tree, path, source, create=not exists,
                             expected=self.sha(path) if exists else None)

    def freeze(self, destination, files):
        source = self.base / ("source-" + destination.replace("/", "-"))
        source.mkdir()
        for name, value in files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return records.freeze(self.tree, self.root, source, destination)

    def config(self, ident="reference"):
        base = "experiments/" + ident
        snapshot = self.freeze(base + "/snapshot", {"prepare.py": b"print('simulated adapter ready')\n"})
        return dict(id=ident, title="Simulated API reference", parent_experiment_id=None, role="reference",
                    hypothesis="Check the real invocation and score publication path", parameters={}, inputs=[],
                    snapshot_sha256=snapshot["manifest_sha256"],
                    execution=dict(argv=[sys.executable, "-B", base + "/snapshot/prepare.py"], cwd=".", environment={}, timeout_seconds=5))

    def api(self, request=None):
        config = self.config()
        self.write("experiments/reference/config.json", config)
        completed = runner.execute(self.tree, "experiments/reference")
        self.assertEqual(completed["state"], "completed")
        descriptor = dict(provider="simulated", model="fixture-model", revision="fixed-fixture",
                          request={} if request is None else request, credential_env=["TUNETUNE_FIXTURE_KEY"],
                          limitations="A local simulation; no remote weights or paid requests are verified")
        self.raw("experiments/reference/model/api.json", descriptor)
        self.raw("experiments/reference/model/adapter.py", b'''import json, os, pathlib, sys
assert os.environ['TUNETUNE_FIXTURE_KEY'].startswith('fixture-')
row = {'sample_id':'one','input':'example','output':'accepted','scores':{'correct':1}}
pathlib.Path(sys.argv[1]).write_text(json.dumps(row) + '\\n')
print('simulated request completed; key was read only from the environment')
''')
        model = records.manifest(self.tree, "experiments/reference/model")
        target = dict(kind="api", path="experiments/reference/model", sha256=model["manifest_sha256"])
        self.write("experiments/reference/status.json", dict(completed, state="succeeded", target=target))
        return target

    def evaluation(self, target, ident="one", missing=False):
        if not self.tree.exists("evaluation/v1/definition.json"):
            package = self.freeze("evaluation/v1", {
                "definition.json": dict(version="v1", description="Simulated exact match", rubric="Exact text",
                                        metrics=[dict(id="correct", label="Correct", direction="maximize")], command=["python3", "score.py"],
                                        no_final_reason="Synthetic fixture"),
                "samples.jsonl": b'{"sample_id":"one","input":"example"}\n',
                "score.py": b"# Invocation lives in the pinned adapter.\n"})
            evaluation_hash = package["manifest_sha256"]
        else:
            evaluation_hash = self.sha("evaluation/v1/manifest.json")
        base = "experiments/reference/evals/" + ident
        command = ([sys.executable, "-B", "-c", "print('simulated missing output')"] if missing else
                   [sys.executable, "-B", "experiments/reference/model/adapter.py", base + "/outputs.jsonl"])
        config = dict(id=ident, evaluation_version="v1", target_sha256=target["sha256"], evaluation_sha256=evaluation_hash,
                      execution=dict(argv=command, cwd=".", environment={}, timeout_seconds=5))
        self.write(base + "/config.json", config)
        return base

    def test_experiment_plan_is_mutable_and_checks_references(self):
        item = dict(id="e001-embed", title="Embedding head", question="Does semantics help?",
                    expected="Beats e000 on development F1", state="planned", parent="e000-keyword",
                    resource_ids=["encoder"])
        plan = dict(rounds=[dict(round=1, goal="Test semantic routes", budget="2 experiments, 1 hour", items=[item])],
                    ideas=[dict(title="SetFit", reason="Needs more reviewed labels")])
        with self.assertRaisesRegex(ValueError, "Unknown plan item resource"):
            self.write("plan.json", plan)
        self.write("resources.json", dict(items=[dict(id="encoder", title="Encoder", type="model", status="missing")]))
        self.write("plan.json", plan)
        self.assertEqual(records.next_id(self.tree, "lr-head"), {"id": "e002-lr-head"})
        item["state"] = "done"
        with self.assertRaisesRegex(ValueError, "has no experiment"):
            self.write("plan.json", plan)
        item["state"] = "dropped"
        plan["rounds"][0]["conclusion"] = "Dropped after the baseline already met the goal"
        self.write("plan.json", plan)
        plan["rounds"].append(dict(round=3, goal="Skipped number", budget="1", items=[]))
        with self.assertRaisesRegex(ValueError, "numbered"):
            self.write("plan.json", plan)
        self.assertEqual(records.validate(self.tree)["errors"], [])

    def test_responses_bind_to_shown_bytes_and_only_the_panel_writes_them(self):
        self.write("proposal.json", dict(summary="Tag posts", examples=[], goal="Navigation tags",
                                         considered=[dict(family="Embeddings", decision="adopted", reason="Few labels")]))
        shown = self.sha("proposal.json")
        response = records.publish_response(self.tree, "proposal", "approve", shown, "Looks right")
        self.assertEqual(records.read_record(self.tree, f"responses/{response['id']}.json")["note"], "Looks right")
        with self.assertRaisesRegex(ValueError, "Conflict"):
            records.publish_response(self.tree, "proposal", "approve", "0" * 64)
        with self.assertRaisesRegex(ValueError, "only by the person"):
            self.write("responses/r1.json", dict(response, id="r1"))
        self.raw("evaluation/draft/samples.jsonl", b'{"sample_id":"s1","input":"x","reference":["a"],"reference_status":"draft"}\n')
        draft = self.sha("evaluation/draft/samples.jsonl")
        with self.assertRaisesRegex(ValueError, "Unknown reviewed sample"):
            records.publish_response(self.tree, "evaluation_review", "submit", draft, items=[dict(sample_id="s9", verdict="confirm")])
        with self.assertRaisesRegex(ValueError, "needs its reference"):
            records.publish_response(self.tree, "evaluation_review", "submit", draft, items=[dict(sample_id="s1", verdict="correct")])
        records.publish_response(self.tree, "evaluation_review", "submit", draft, items=[dict(sample_id="s1", verdict="correct", reference=["b"])])
        self.assertEqual(records.validate(self.tree)["errors"], [])
        self.raw("comparison/outputs.jsonl", b'{"sample_id":"a","input":"x","outputs":{"e1":["tag"]}}\n')
        outputs = self.sha("comparison/outputs.jsonl")
        for items, message in (([], "at least one"), ([dict(sample_id="a", experiment_id="e2", verdict="bad")], "not shown"),
                               ([dict(sample_id="a", experiment_id="e1", verdict="confirm")], "acceptance verdict"),
                               ([dict(sample_id="a", experiment_id="e1", verdict="good")] * 2, "Duplicate")):
            with self.assertRaisesRegex(ValueError, message):
                records.publish_response(self.tree, "acceptance", "submit", outputs, items=items)
        judged = records.publish_response(self.tree, "acceptance", "submit", outputs,
                                          items=[dict(sample_id="a", experiment_id="e1", verdict="bad", note="Missing the travel tag")])
        self.assertEqual(records.read_record(self.tree, f"responses/{judged['id']}.json")["target"], {"path": "comparison/outputs.jsonl", "sha256": outputs})
        with self.assertRaisesRegex(ValueError, "Invalid source"):
            self.write("proposal.json", dict(summary="x", examples=[], sources=[dict(title="x", url="javascript:alert(1)")]))

    def test_view_state_accumulates_attention_per_view(self):
        first = records.set_view(self.tree, ["proposal"], attention=["proposal:请确认提案"])
        second = records.set_view(self.tree, ["evaluation"], "e001-embed", ["review:22 篇标签待审阅"])
        self.assertEqual(second["revision"], first["revision"] + 1)
        self.assertEqual([n["view"] for n in second["attention"]], ["proposal", "review"])
        self.assertEqual(second["focus"], {"experiment": "e001-embed"})
        self.assertEqual(records.set_view(self.tree, [], clear=True)["attention"], [])
        with self.assertRaisesRegex(ValueError, "view:message"):
            records.set_view(self.tree, [], attention=["nowhere:x"])

    def test_next_id_counts_existing_experiments(self):
        self.assertEqual(records.next_id(self.tree), {"id": "e000"})
        (self.root / "experiments/e007-old").mkdir(parents=True)
        (self.root / "experiments/legacy").mkdir()
        self.assertEqual(records.next_id(self.tree, "prompt"), {"id": "e008-prompt"})
        with self.assertRaisesRegex(ValueError, "Slug"):
            records.next_id(self.tree, "Bad Slug")

    def test_api_reference_runs_with_inherited_credential_and_real_outputs(self):
        target = self.api()
        base = self.evaluation(target)
        secret = "fixture-runtime-only-do-not-record"
        with patch.dict(os.environ, TUNETUNE_FIXTURE_KEY=secret):
            completed = runner.execute(self.tree, base)
        self.assertEqual(completed["state"], "completed")
        outputs = records.read_record(self.tree, base + "/outputs.jsonl")
        self.assertEqual(outputs[0]["output"], "accepted")
        usage = dict(requests=1, input_tokens=1, output_tokens=1, cost=0, currency="USD", latency_seconds=0.01)
        self.write(base + "/status.json", dict(completed, state="succeeded", metrics=dict(correct=1), usage=usage))
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertEqual(records.read_record(self.tree, base + "/status.json")["usage"], usage)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret.encode(), path.read_bytes(), str(path))
        previous = self.tree.read(base + "/status.json")
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.write(base + "/status.json", dict(completed, state="succeeded", metrics=dict(correct=0), usage=usage))
        self.assertEqual(self.tree.read(base + "/status.json"), previous)

    def test_missing_output_never_becomes_success(self):
        target = self.api()
        base = self.evaluation(target, missing=True)
        completed = runner.execute(self.tree, base)
        self.assertEqual(completed["state"], "completed")
        with self.assertRaises((FileNotFoundError, ValueError)):
            self.write(base + "/status.json", dict(completed, state="succeeded", metrics=dict(correct=1)))
        self.assertEqual(records.read_record(self.tree, base + "/status.json")["state"], "completed")
        self.write(base + "/status.json", dict(completed, state="failed", error="Expected output was not produced"))
        self.assertEqual(records.read_record(self.tree, base + "/status.json")["state"], "failed")

    def test_api_is_a_reference_not_a_local_delivery(self):
        self.api()
        project = records.read_record(self.tree, "project.json")
        with self.assertRaisesRegex(ValueError, "Only local"):
            self.write("project.json", dict(project, deliveries=["reference"]))
        config = self.config("local")
        config["role"] = "candidate"
        self.write("experiments/local/config.json", config)
        self.raw("experiments/local/model/model.bin", b"synthetic local weights")
        target = dict(kind="local", path="experiments/local/model/model.bin", sha256=self.sha("experiments/local/model/model.bin"))
        self.write("experiments/local/status.json", dict(state="succeeded", updated_at=STAMP, target=target))
        self.write("project.json", dict(project, deliveries=["local"]))
        self.assertEqual(records.read_record(self.tree, "project.json")["deliveries"], ["local"])

    def test_api_descriptor_refuses_secret_values(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            self.api(request={"headers": {"authorization": "fixture-placeholder"}})
        # The failed success publication leaves the process completed, never silently succeeded.
        self.assertEqual(records.read_record(self.tree, "experiments/reference/status.json")["state"], "completed")

    def test_changed_adapter_invalidates_api_identity_before_evaluation(self):
        target = self.api()
        base = self.evaluation(target)
        self.raw("experiments/reference/model/adapter.py", b"print('changed adapter')\n")
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            runner.execute(self.tree, base)
        self.assertFalse(self.tree.exists(base + "/run.log"))
        self.assertFalse(self.tree.exists(base + "/status.json"))

    def test_resources_and_approaches_share_valid_references(self):
        item = dict(id="semantic-model", title="Semantic model", type="model", status="missing", purpose="Quality comparison",
                    source="https://example.com/model", version="fixed", size="Estimated 100 MB",
                    path="resources/model", preparation="Download after approval; allow 200 MB including cache", access="No data leaves this computer")
        self.write("resources.json", dict(items=[item]))
        proposal = dict(summary="Compare methods", examples=[], approaches=[dict(id="semantic", title="Semantic route",
                        roles=["recommended", "reference"], rationale="Investigate semantic generalization", limitations="Unmeasured",
                        resource_ids=["semantic-model"])])
        self.write("proposal.json", proposal)
        before = self.tree.read("proposal.json")
        proposal["approaches"][0]["resource_ids"] = ["not-present"]
        with self.assertRaisesRegex(ValueError, "Unknown approach resource"):
            self.write("proposal.json", proposal)
        self.assertEqual(self.tree.read("proposal.json"), before)

    def split_config(self, train, reserved):
        config = self.config()
        self.raw("evaluation/split.json", dict(train=train, reserved=reserved))
        config["data_split"] = dict(path="evaluation/split.json", sha256=self.sha("evaluation/split.json"))
        config["inputs"] = train
        return config

    def test_split_verifies_sources_and_rejects_same_content_under_other_name(self):
        self.raw("inputs/train.txt", b"same source")
        self.raw("inputs/held.txt", b"same source")
        train = [dict(path="inputs/train.txt", sha256=self.sha("inputs/train.txt"))]
        held = [dict(path="inputs/held.txt", sha256=self.sha("inputs/held.txt"))]
        config = self.split_config(train, held)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.write("experiments/reference/config.json", config)
        self.assertFalse(self.tree.exists("experiments/reference/config.json"))

    def test_split_pins_content_and_is_checked_again_before_execution(self):
        self.raw("inputs/train.txt", b"train source")
        self.raw("inputs/held.txt", b"held source")
        train = [dict(path="inputs/train.txt", sha256=self.sha("inputs/train.txt"))]
        held = [dict(path="inputs/held.txt", sha256=self.sha("inputs/held.txt"))]
        config = self.split_config(train, held)
        self.write("experiments/reference/config.json", config)
        self.raw("inputs/held.txt", b"changed after configuration")
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            runner.execute(self.tree, "experiments/reference")
        self.assertFalse(self.tree.exists("experiments/reference/run.log"))

    def test_freeze_refuses_secrets_and_caches_before_publication(self):
        for index, name in enumerate((".env", "credentials.json", "service.key", "__pycache__/code.pyc", "cache/data.txt", "node_modules/pkg.js")):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unsafe snapshot"):
                self.freeze(f"experiments/unsafe{index}/snapshot", {name: b"fixture"})
            self.assertFalse(self.tree.exists(f"experiments/unsafe{index}/snapshot"))

    def test_schema_two_write_and_execution_refused_without_mutation(self):
        config = self.config()
        self.write("experiments/reference/config.json", config)
        self.raw("project.json", dict(schema_version=2, name="Old", language="en", current_evaluation=None, deliveries=[]))
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaises(ValueError):
            self.write("proposal.json", dict(summary="Must not apply", examples=[]))
        with self.assertRaises(ValueError):
            runner.execute(self.tree, "experiments/reference")
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
