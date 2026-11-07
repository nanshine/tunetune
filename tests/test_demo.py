"""Real, dependency-free demo execution in disposable format-3 installed-like trees."""
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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


demo = load("create_demo", ROOT / "scripts/create-demo.py")
records = load("demo_test_records", ROOT / "plugins/tunetune/skills/research-workspace/scripts/records.py")
init = load("demo_test_init", ROOT / "plugins/tunetune/skills/research-workspace/scripts/init.py")


def installed_fixture(root):
    """A project initialized by the real skill initializer, as an Agent would."""
    init.install(root)
    return root


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def file_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="demo-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name).resolve()
        cls.project = installed_fixture(cls.base / "installed project with spaces")
        cls.initial_files = file_bytes(cls.project)
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/create-demo.py"), "--project", str(cls.project)],
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.report = json.loads(result.stdout)
        cls.generated_files = file_bytes(cls.project)

    def test_complete_records_and_exact_file_layout(self):
        self.assertEqual(self.report["experiments"], 10)
        self.assertEqual(self.report["evaluation_runs"], 12)
        self.assertEqual(self.report["evaluation_versions"], ["v1", "v2"])
        self.assertEqual(self.report["deliveries"], ["exp-001", "exp-002", "exp-008"])
        self.assertEqual(self.report["comparison_samples"], 8)
        tree = records.Tree(self.project)
        self.addCleanup(tree.close)
        report = records.validate(tree)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["unfinished"], [])
        project = read_json(self.project / "project.json")
        self.assertEqual(set(project), {"name", "language", "current_evaluation", "deliveries"})
        self.assertEqual(project["current_evaluation"], "v2")
        self.assertEqual(project["deliveries"], demo.DELIVERIES)
        proposal = read_json(self.project / "proposal.json")
        self.assertEqual(set(proposal), {"summary", "goal", "output", "considered", "evaluation", "budget", "stopping", "delivery", "examples", "feasibility", "approaches"})
        self.assertEqual({item["decision"] for item in proposal["considered"]}, {"adopted", "excluded"})
        self.assertEqual({role for approach in proposal["approaches"] for role in approach["roles"]}, {"baseline", "recommended", "reference", "challenge"})
        self.assertIn(demo.NOTICE, proposal["summary"])
        for example in proposal["examples"]:
            self.assertEqual(set(example), {"id", "input", "expected_output"})
        expected = {"project.json", "proposal.json", "resources.json", "data/train.jsonl", "data/comparison.jsonl",
                    "comparison/outputs.jsonl", "comparison/run.log", "src/train.py", "src/infer.py", "src/evaluate.py"}
        for version in ("v1", "v2"):
            expected |= {f"evaluation/{version}/{name}" for name in
                         ("definition.json", "samples.jsonl", "evaluate.py", "infer.py", "calibration.log", "manifest.json")}
        for index in range(1, 11):
            base = f"experiments/exp-{index:03d}"
            expected |= {f"{base}/{name}" for name in ("config.json", "status.json", "analysis.json", "run.log", "model/model.json", "model/invoke.json", "model/manifest.json",
                                                      "snapshot/train.py", "snapshot/infer.py", "snapshot/parameters.json", "snapshot/manifest.json")}
            versions = ("v1", "v2") if index <= 2 else ("v1",) if index <= 5 else ("v2",)
            for version in versions:
                expected |= {f"{base}/evals/eval-{version}/{name}" for name in ("config.json", "status.json", "outputs.jsonl", "run.log", "samples.jsonl")}
        actual = {path for path in self.generated_files if not path.startswith(".workspace/") and path != "AGENTS.md"}
        self.assertEqual(actual, expected)
        self.assertEqual(len(expected), 192)
        self.assertEqual(self.report["files"], {"research": 192, "created": len(self.generated_files.keys() - self.initial_files.keys()),
                                              "total": len(self.generated_files)})
        self.assertEqual(self.report["files"]["created"], 190)
        self.assertEqual({path for path in self.generated_files if path.startswith(".workspace/runtime/")},
                         {".workspace/runtime/records.lock"})
        self.assertFalse(list(self.project.rglob("__pycache__")))
        for path, content in self.initial_files.items():
            if path not in ("project.json", "proposal.json", "resources.json"):
                self.assertEqual(self.generated_files[path], content)

    def test_installed_api_transport_and_actual_resource_observations(self):
        workspace = load("demo_installed_workspace", self.project / ".workspace/app/workspace.py")
        reader = workspace.Reader(self.project)
        inventory_before = (self.project / "resources.json").read_bytes()
        state = reader.snapshot()
        self.assertIsNone(state["error"])
        files = state["files"]
        self.assertEqual(len(files), 84)
        self.assertEqual(len([path for path in files if path.endswith("/model/invoke.json")]), 10)
        self.assertFalse([path for path in files if "/model/" in path and not path.endswith("/invoke.json")])
        self.assertEqual(len([path for path in files if path.endswith("/config.json") and "/evals/" not in path]), 10)
        self.assertEqual(len([path for path in files if path.endswith("/config.json") and "/evals/" in path]), 12)
        self.assertEqual(len(files["comparison/outputs.jsonl"]["content"]), 8)
        self.assertEqual(files["project.json"]["content"]["deliveries"], demo.DELIVERIES)
        inventory = files["resources.json"]["content"]["items"]
        self.assertEqual(len(inventory), 7)
        observations = {item["id"]: item for item in state["observations"]["items"]}
        self.assertEqual(set(observations), {item["id"] for item in inventory})
        self.assertEqual(read_json(self.project / ".workspace/runtime/resources.json"), state["observations"])
        self.assertEqual((self.project / "resources.json").read_bytes(), inventory_before)
        for item in inventory:
            self.assertLessEqual(set(item), {"id", "title", "type", "status", "path", "location", "version", "size", "monitor"})
            observed = observations[item["id"]]
            if item["monitor"]["kind"] == "file":
                path = self.project / item["path"]
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)
                self.assertEqual(observed["state"], "ready")
                self.assertTrue(observed["modified_at"])
                self.assertTrue(observed["size"])
            self.assertNotEqual(item["monitor"]["kind"], "nvidia_gpu")
        self.assertEqual(observations["python"]["state"], "ready")
        self.assertIn(observations["memory"]["state"], ("ready", "unknown"))
        if observations["memory"]["state"] == "ready":
            self.assertTrue(observations["memory"]["size"])
        for version, count in (("v1", 16), ("v2", 24)):
            self.assertEqual(len(files[f"evaluation/{version}/samples.jsonl"]["content"]), count)
            definition = files[f"evaluation/{version}/definition.json"]["content"]
            self.assertEqual(set(definition), {"version", "description", "rubric", "metrics", "command", "no_final_reason"})

    def assert_process_facts(self, path):
        status = read_json(path / "status.json")
        self.assertEqual(status["state"], "succeeded")
        self.assertEqual(status["returncode"], 0)
        self.assertFalse(status["timed_out"])
        self.assertNotIn("error", status)
        self.assertGreater(status["elapsed_seconds"], 0)
        started = datetime.fromisoformat(status["started_at"])
        completed = datetime.fromisoformat(status["completed_at"])
        self.assertIsNotNone(started.utcoffset())
        self.assertIsNotNone(completed.utcoffset())
        self.assertLessEqual(started, completed)
        self.assertEqual(status["config_sha256"], sha(path / "config.json"))
        self.assertTrue((path / "run.log").read_bytes())
        fields = {"state", "updated_at", "started_at", "completed_at", "elapsed_seconds", "returncode", "timed_out", "config_sha256"}
        self.assertEqual(set(status), fields | ({"metrics"} if "evals" in path.parts else {"target"}))

    def test_real_metrics_calibration_and_old_model_retests(self):
        versions = {}
        for path in sorted((self.project / "experiments").glob("*/evals/*")):
            config = read_json(path / "config.json")
            self.assertEqual(set(config), {"id", "evaluation_version", "target_sha256", "evaluation_sha256", "execution"})
            experiment = path.parent.parent.name
            versions.setdefault(experiment, []).append(config)
            status = read_json(path / "status.json")
            outputs = read_rows(path / "outputs.jsonl")
            accuracy = sum(row["output"] == row["reference"] for row in outputs) / len(outputs)
            f1 = []
            for label in demo.LABELS:
                tp = sum(row["output"] == label and row["reference"] == label for row in outputs)
                fp = sum(row["output"] == label and row["reference"] != label for row in outputs)
                fn = sum(row["output"] != label and row["reference"] == label for row in outputs)
                f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
            self.assertEqual(status["metrics"]["accuracy"], accuracy)
            self.assertAlmostEqual(status["metrics"]["macro_f1"], sum(f1) / 4)
            for row in outputs:
                self.assertEqual(set(row), {"sample_id", "input", "output", "reference", "scores"})
                self.assertEqual(row["scores"], {"accuracy": int(row["output"] == row["reference"])})
            replay = subprocess.run(config["execution"]["argv"], cwd=self.project, capture_output=True, text=True, timeout=60, check=True)
            payload = json.loads(replay.stdout)
            self.assertEqual(payload["metrics"], status["metrics"])
            self.assertEqual(payload["outputs"], outputs)
            self.assertEqual(read_json(path / "run.log"), payload)
            evaluation = self.project / "evaluation" / config["evaluation_version"]
            self.assertEqual(config["evaluation_sha256"], sha(evaluation / "manifest.json"))
            self.assertNotEqual(config["evaluation_sha256"], sha(evaluation / "definition.json"))
            self.assertEqual(config["target_sha256"], read_json(path.parent.parent / "status.json")["target"]["sha256"])
            self.assert_process_facts(path)
        for experiment in ("exp-001", "exp-002"):
            self.assertEqual({item["evaluation_version"] for item in versions[experiment]}, {"v1", "v2"})
            self.assertEqual(len({item["target_sha256"] for item in versions[experiment]}), 1)
            self.assertIn("没有再训练", read_json(self.project / "experiments" / experiment / "analysis.json")["summary"])
        for version in ("v1", "v2"):
            package = self.project / "evaluation" / version
            result = subprocess.run([sys.executable, "-B", str(package / "evaluate.py"), "--self-test"],
                                    capture_output=True, text=True, timeout=60, check=True)
            self.assertEqual(json.loads(result.stdout), {"passed": True, "checks": 5})
            self.assertEqual(read_json(package / "calibration.log"), json.loads(result.stdout))

    def test_all_weights_reproduce_from_minimal_frozen_inputs(self):
        signatures = set()
        tree = records.Tree(self.project)
        self.addCleanup(tree.close)
        for index in range(1, 11):
            base = self.project / f"experiments/exp-{index:03d}"
            config = read_json(base / "config.json")
            self.assertEqual(set(config), {"id", "title", "parent_experiment_id", "hypothesis", "method", "model_name", "framework",
                                           "parameters", "inputs", "snapshot_sha256", "execution", "role"})
            self.assertEqual(config["inputs"], [{"path": "data/train.jsonl", "sha256": sha(self.project / "data/train.jsonl")}])
            self.assertEqual(config["snapshot_sha256"], sha(base / "snapshot/manifest.json"))
            model = read_json(base / "model/model.json")
            self.assertEqual(model["parameters"], config["parameters"])
            self.assertEqual(model["fitted"], index != 1)
            self.assertEqual(model["training_rows"], 52)
            self.assertEqual(model["effective_training_rows"], 156 if index in (7, 8) else 52)
            if index != 1:
                self.assertGreater(model["vocabulary_size"], 10)
                self.assertTrue(model["log_likelihood"])
            argv = config["execution"]["argv"][:]
            argv[-1] = str(self.base / f"reproduced-{index}.json")
            subprocess.run(argv, cwd=self.project, check=True, capture_output=True, timeout=60)
            self.assertEqual(Path(argv[-1]).read_bytes(), (base / "model/model.json").read_bytes())
            signatures.add(sha(base / "model/model.json"))
            self.assert_process_facts(base)
            status = read_json(base / "status.json")
            self.assertEqual(status["target"]["path"], f"experiments/exp-{index:03d}/model")
            self.assertEqual(status["target"]["sha256"], sha(base / "model/manifest.json"))
            self.assertEqual(read_json(base / "model/invoke.json")["argv"][-1], "--jsonl")
            analysis = read_json(base / "analysis.json")
            self.assertEqual(set(analysis), {"outcome", "summary"})
            self.assertTrue(analysis["summary"])
            records.verify_inputs(tree, f"experiments/exp-{index:03d}", config)
        self.assertEqual(len(signatures), 10)
        for attempt in (self.project / "experiments").glob("*/evals/*"):
            records.verify_inputs(tree, attempt.relative_to(self.project).as_posix(), read_json(attempt / "config.json"))

    def test_pools_and_train_only_augmentation_are_disjoint(self):
        seen = set()
        for relative in ("data/train.jsonl", "evaluation/v1/samples.jsonl", "evaluation/v2/samples.jsonl", "data/comparison.jsonl"):
            sample_rows = read_rows(self.project / relative)
            pool = {row["input"].casefold() for row in sample_rows}
            self.assertEqual(len(pool), len(sample_rows))
            self.assertFalse(seen & pool)
            seen |= pool
        infer = load("demo_infer", self.project / "experiments/exp-008/snapshot/infer.py")
        with patch.dict(sys.modules, {"infer": infer}):
            train = load("demo_train", self.project / "experiments/exp-008/snapshot/train.py")
        augmented = {row["input"].casefold() for row in train.training_rows(read_rows(self.project / "data/train.jsonl"), True)}
        for relative in ("evaluation/v1/samples.jsonl", "evaluation/v2/samples.jsonl", "data/comparison.jsonl"):
            self.assertFalse(augmented & {row["input"].casefold() for row in read_rows(self.project / relative)})

    def test_chosen_models_same_input_outputs_and_arbitrary_inference(self):
        expected = read_rows(self.project / "comparison/outputs.jsonl")
        for row in expected:
            self.assertEqual(set(row), {"sample_id", "input", "outputs"})
            self.assertEqual(set(row["outputs"]), set(demo.DELIVERIES))
        for experiment in demo.DELIVERIES:
            status = read_json(self.project / "experiments" / experiment / "status.json")
            argv = [sys.executable, "-B", f"experiments/{experiment}/snapshot/infer.py", "--model", status["target"]["path"] + "/model.json"]
            replay = subprocess.run(argv + ["--inputs", "data/comparison.jsonl"], cwd=self.project,
                                    check=True, capture_output=True, text=True, timeout=60)
            values = [json.loads(line) for line in replay.stdout.splitlines()]
            self.assertEqual(len(values), 8)
            for row, output in zip(expected, values):
                self.assertEqual(output["sample_id"], row["sample_id"])
                self.assertEqual(output["input"], row["input"])
                self.assertEqual(output["output"], row["outputs"][experiment])
                self.assertAlmostEqual(sum(output["probabilities"].values()), 1.0)
            arbitrary = subprocess.run(argv + ["--text", "Please polish the telescope before the eclipse"], cwd=self.project,
                                       check=True, capture_output=True, text=True, timeout=60)
            self.assertIn(arbitrary.stdout.strip(), demo.LABELS)

    def test_rerun_and_reexecution_refuse_without_changing_files(self):
        before = file_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "Refusing"):
            demo.generate(self.project)
        for path in ("experiments/exp-001", "experiments/exp-001/evals/eval-v1"):
            result = subprocess.run([sys.executable, "-B", str(self.project / demo.HELPERS / "run.py"),
                                     "--project", str(self.project), "--path", path], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn("use a new ID", result.stderr)
        self.assertEqual(file_bytes(self.project), before)


class DemoSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="demo-safety-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()

    def test_missing_installation_existing_research_and_partial_directories_refused(self):
        empty = self.base / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "Initialize the project"):
            demo.generate(empty)
        self.assertEqual(list(empty.iterdir()), [])
        for directory in ("data", "src", "experiments", "evaluation", "comparison"):
            root = installed_fixture(self.base / directory)
            sentinel = root / directory / "partial-attempt"
            sentinel.mkdir(parents=True)
            before = file_bytes(root)
            with self.assertRaisesRegex(ValueError, "Refusing existing research"):
                demo.generate(root)
            self.assertEqual(file_bytes(root), before)
            self.assertFalse((root / ".workspace/runtime").exists())

    def test_existing_proposal_inventory_delivery_or_incompatible_kit_is_not_overwritten(self):
        cases = [
            ("proposal.json", {"summary": "Existing research"}),
            ("proposal.json", {"feasibility": {"verdict": "conditional", "reason": "Need more data"}}),
            ("resources.json", {"items": [{"id": "real", "title": "Real data", "type": "dataset", "status": "unknown"}]}),
            ("project.json", {"deliveries": ["existing-model"]}),
            ("project.json", {"schema_version": 1}),
            (".workspace/manifest.json", {"version": "0.6.0"}),
        ]
        for index, (name, changes) in enumerate(cases):
            root = installed_fixture(self.base / f"existing-{index}")
            target = root / name
            target.write_bytes(records.encoded({**read_json(target), **changes}))
            before = file_bytes(root)
            with self.assertRaises(ValueError):
                demo.generate(root)
            self.assertEqual(file_bytes(root), before)

    def test_symlink_and_parent_traversal_refusal_does_not_touch_targets(self):
        root = installed_fixture(self.base / "installed")
        link = self.base / "project-link"
        link.symlink_to(root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            demo.generate(link)
        with self.assertRaisesRegex(ValueError, "Parent traversal"):
            demo.generate(root / ".." / "installed")
        external = self.base / "external"
        external.mkdir()
        (root / "data").symlink_to(external, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            demo.generate(root)
        self.assertEqual(list(external.iterdir()), [])
        self.assertEqual(read_json(root / "proposal.json")["summary"], "")

    def test_real_process_failure_and_zero_exit_invalid_outputs_keep_facts(self):
        failures = [
            ("training", "TRAIN_SOURCE", "import sys\nprint('training failed', file=sys.stderr)\nraise SystemExit(7)\n",
             "experiments/exp-001", 7),
            ("evaluation", "EVALUATE_SOURCE", demo.EVALUATE_SOURCE.replace(
                '    model = json.loads(Path(args.model).read_text(encoding="utf-8"))', '    raise SystemExit(9)'),
             "experiments/exp-001/evals/eval-v1", 9),
            ("invalid-output", "EVALUATE_SOURCE", demo.EVALUATE_SOURCE.replace('"outputs": outputs}', '"outputs": outputs[:-1]}'),
             "experiments/exp-001/evals/eval-v1", 0),
        ]
        for name, constant, source, attempt, code in failures:
            with self.subTest(name=name):
                root = installed_fixture(self.base / name)
                # Change source, not subprocess results: the installed runner
                # really executes the failing or malformed payload.
                with patch.object(demo, constant, source):
                    with self.assertRaises((RuntimeError, ValueError)):
                        demo.generate(root)
                status = read_json(root / attempt / "status.json")
                self.assertEqual(status["state"], "failed")
                self.assertEqual(status["returncode"], code)
                self.assertFalse(status["timed_out"])
                self.assertGreater(status["elapsed_seconds"], 0)
                self.assertEqual(status["config_sha256"], sha(root / attempt / "config.json"))
                self.assertNotIn("metrics", status)
                self.assertNotIn("target", status)
                self.assertFalse((root / attempt / "outputs.jsonl").exists())
                self.assertEqual(read_json(root / "project.json")["deliveries"], [])
                self.assertFalse((root / "comparison/outputs.jsonl").exists())
                before = file_bytes(root)
                with self.assertRaisesRegex(ValueError, "Refusing"):
                    demo.generate(root)
                self.assertEqual(file_bytes(root), before)

    def test_interrupted_finalization_preserves_completed_not_succeeded(self):
        root = installed_fixture(self.base / "interrupted")
        original = demo.Demo.run
        completed = {}

        def interrupt(instance, base):
            self.assertEqual(instance.read_json(base + "/status.json")["state"], "pending")
            status = original(instance, base)
            completed[base] = status
            if "/evals/" in base:
                raise KeyboardInterrupt()
            return status

        with patch.object(demo.Demo, "run", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                demo.generate(root)
        experiment = "experiments/exp-001"
        attempt = experiment + "/evals/eval-v1"
        final = read_json(root / experiment / "status.json")
        for key in records.PROCESS:
            if key in completed[experiment]:
                self.assertEqual(final[key], completed[experiment][key])
        self.assertEqual(final["state"], "succeeded")
        self.assertEqual(read_json(root / attempt / "status.json"), completed[attempt])
        self.assertEqual(completed[attempt]["state"], "completed")
        self.assertNotIn("metrics", completed[attempt])
        self.assertFalse((root / attempt / "outputs.jsonl").exists())
        self.assertTrue(read_json(root / attempt / "run.log")["outputs"])
        before = file_bytes(root)
        with self.assertRaisesRegex(ValueError, "Refusing"):
            demo.generate(root)
        self.assertEqual(file_bytes(root), before)


if __name__ == "__main__":
    unittest.main()
