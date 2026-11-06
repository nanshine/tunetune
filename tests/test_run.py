"""Run only synthetic commands in disposable projects; never train a real model."""
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/tunetune/skills/research-workspace/scripts"
SPEC = importlib.util.spec_from_file_location("records", SCRIPTS / "records.py")
records = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(records)
with patch.dict(sys.modules, records=records):
    SPEC = importlib.util.spec_from_file_location("runner_under_test", SCRIPTS / "run.py")
    runner = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(runner)
STAMP = "2026-01-01T00:00:00Z"
EVAL = "experiments/e1/evals/r1"


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.tree = records.Tree(self.root)
        self.addCleanup(self.tree.close)
        self.raw("project.json", dict(schema_version=4, name="Synthetic", language="en", current_evaluation=None, deliveries=[]))
        self.raw("proposal.json", dict(summary="Fixture", examples=[]))
        self.raw("resources.json", dict(items=[]))
        source = self.base / "evaluation"
        source.mkdir()
        (source / "definition.json").write_bytes(records.encoded(dict(version="v1", description="Fixture", rubric="Count",
            metrics=[dict(id="count", label="Count", direction="maximize")], command=[sys.executable, "evaluation/v1/evaluate.py"],
            no_final_reason="Synthetic fixture")))
        (source / "samples.jsonl").write_bytes(b'{"sample_id":"one","input":"synthetic"}\n')
        (source / "evaluate.py").write_text("print('evaluated fixture')\n")
        self.evaluation_hash = records.freeze(self.tree, self.root, source, "evaluation/v1")["manifest_sha256"]
        self.raw("data/train.txt", b"synthetic only\n")
        self.prepare()

    def raw(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return target

    def sha(self, path):
        return records.digest(self.tree.read(path))

    def publish(self, path, value, create=True):
        source = self.base / "input.json"
        source.write_bytes(value if isinstance(value, bytes) else records.encoded(value))
        return records.write(self.tree, path, source, create=create, expected=None if create else self.sha(path))

    def prepare(self, code="print('synthetic command')\n", ident="e1", timeout=5):
        path = f"experiments/{ident}"
        source = self.base / ("snapshot-" + ident)
        source.mkdir()
        (source / "train.py").write_text(code)
        snapshot = records.freeze(self.tree, self.root, source, path + "/snapshot")
        config = dict(id=ident, title="Fixture", parent_experiment_id=None, hypothesis="Test rule", parameters={},
                      snapshot_sha256=snapshot["manifest_sha256"],
                      inputs=[dict(path="data/train.txt", sha256=self.sha("data/train.txt"))],
                      execution=dict(argv=[sys.executable, "-B", path + "/snapshot/train.py"], cwd=".", environment={}, timeout_seconds=timeout))
        self.publish(path + "/config.json", config)
        return config

    def evaluation(self):
        self.raw("experiments/e1/model/rule.txt", b"synthetic model")
        model_hash = self.sha("experiments/e1/model/rule.txt")
        path = "experiments/e1/status.json"
        previous = records.read_record(self.tree, path) if self.tree.exists(path) else {}
        self.publish(path, dict(previous, state="succeeded", updated_at=STAMP, target=dict(kind="local", path="experiments/e1/model/rule.txt",
                                sha256=model_hash)), create=not self.tree.exists(path))
        config = dict(id="r1", evaluation_version="v1", target_sha256=model_hash, evaluation_sha256=self.evaluation_hash,
                      execution=dict(argv=[sys.executable, "-B", "evaluation/v1/evaluate.py"], cwd=".", environment={}, timeout_seconds=5))
        self.publish(EVAL + "/config.json", config)
        return config

    def cli(self, path="experiments/e1"):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "run.py"), "--project", str(self.root), "--path", path],
                              capture_output=True, text=True, timeout=10)

    def assert_unstarted(self, path="experiments/e1"):
        self.assertFalse(self.tree.exists(path + "/run.log"))
        self.assertFalse(self.tree.exists(path + "/status.json"))

    def test_zero_exit_records_completed_status_not_scientific_success(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status, records.read_record(self.tree, "experiments/e1/status.json"))
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["returncode"], 0)
        self.assertFalse(status["timed_out"])
        self.assertGreaterEqual(status["elapsed_seconds"], 0)
        self.assertEqual(status["config_sha256"], self.sha("experiments/e1/config.json"))
        self.assertEqual(self.tree.read("experiments/e1/run.log"), b"synthetic command\n")
        for leaf in ("receipt.json", "result.json", "artifacts.json", "train.log"):
            self.assertFalse(self.tree.exists("experiments/e1/" + leaf))
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["unfinished"], ["experiments/e1"])
        before = self.tree.read("experiments/e1/status.json")
        self.assertEqual(self.cli().returncode, 1)
        self.assertEqual(self.tree.read("experiments/e1/status.json"), before)

    def test_argv_literal_environment_overlay_and_descriptor_cwd(self):
        config = self.prepare("import os,sys,json; print(json.dumps([os.getcwd(),sys.argv[1:],os.environ['FIXTURE']]))\n", "e2")
        config["execution"].update(cwd="experiments/e2", environment={"FIXTURE": "test"},
                                   argv=[sys.executable, "-B", "snapshot/train.py", "a b", "; touch INJECTED", "$(touch INJECTED)"])
        self.raw("experiments/e2/config.json", config)
        status = runner.execute(self.tree, "experiments/e2")
        self.assertEqual(status["returncode"], 0)
        cwd, args, env = json.loads(self.tree.read("experiments/e2/run.log"))
        self.assertEqual(cwd, str(self.root / "experiments/e2"))
        self.assertEqual(args, ["a b", "; touch INJECTED", "$(touch INJECTED)"])
        self.assertEqual(env, "test")
        self.assertEqual(list(self.root.rglob("INJECTED")), [])

    def test_failure_is_terminal_with_all_process_facts(self):
        self.prepare("import sys; print('real failure', file=sys.stderr); sys.exit(7)\n", "fail")
        result = self.cli("experiments/fail")
        self.assertEqual(result.returncode, 1)
        status = json.loads(result.stdout)
        self.assertEqual(status["returncode"], 7)
        self.assertEqual(status["state"], "failed")
        self.assertTrue(set(records.PROCESS) - {"error"} <= set(status))
        self.assertIn(b"real failure", self.tree.read("experiments/fail/run.log"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.publish("experiments/fail/status.json", dict(status, state="cancelled"), create=False)

    def test_nested_evaluation_process_states_for_both_exit_codes(self):
        config = self.evaluation()
        result = self.cli(EVAL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "completed")
        config["id"] = "r2"
        config["execution"]["argv"] = [sys.executable, "-c", "raise SystemExit(4)"]
        self.publish("experiments/e1/evals/r2/config.json", config)
        status = runner.execute(self.tree, "experiments/e1/evals/r2")
        self.assertEqual(status["returncode"], 4)
        self.assertEqual(status["state"], "failed")
        self.assertNotIn("metrics", status)
        self.assertTrue(records.validate(self.tree)["valid"])

    def test_payload_completion_kills_same_group_workers_for_failure_and_success(self):
        for exit_code in (17, 0):
            with self.subTest(exit_code=exit_code):
                ident = f"workers-{exit_code}"
                fifo = self.base / f"{ident}.fifo"
                os.mkfifo(fifo)
                # EOF proves worker termination without PID polling; the alarm
                # bounds the fixture's lifetime if this regression ever fails.
                worker = ("import os,signal\n"
                          "signal.alarm(5)\n"
                          f"fd=os.open({str(fifo)!r}, os.O_WRONLY)\n"
                          "os.write(fd, b'ready')\n"
                          "print(os.getpid(), os.getpgrp(), flush=True)\n"
                          "signal.pause()\n")
                code = ("import os,subprocess,sys\n"
                        f"p=subprocess.Popen([sys.executable,'-c',{worker!r}], stdout=subprocess.PIPE)\n"
                        "print(p.stdout.readline().decode().strip(), flush=True)\n"
                        "print(os.getpid(), os.getpgrp(), flush=True)\n"
                        "print('{\"returncode\": 99, \"error\": \"not control data\"}', flush=True)\n"
                        f"sys.exit({exit_code})\n")
                self.prepare(code, ident)
                with os.fdopen(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK), "rb", buffering=0) as probe:
                    with selectors.SelectSelector() as selector:
                        selector.register(probe, selectors.EVENT_READ)
                        with patch.object(runner.os, "killpg", wraps=os.killpg) as kill:
                            status = runner.execute(self.tree, f"experiments/{ident}")
                        self.assertEqual(status["returncode"], exit_code)
                        self.assertFalse(status["timed_out"])
                        self.assertNotIn("error", status)
                        lines = self.tree.read(f"experiments/{ident}/run.log").splitlines()
                        worker_pid, worker_group = map(int, lines[0].split())
                        payload_pid, group = map(int, lines[1].split())
                        self.assertEqual(worker_group, group)
                        self.assertNotIn(group, (worker_pid, payload_pid, os.getpgrp()))
                        kill.assert_called_once_with(group, signal.SIGKILL)
                        self.assertTrue(selector.select(2), "Worker did not signal readiness")
                        self.assertEqual(os.read(probe.fileno(), 1024), b"ready")
                        self.assertTrue(selector.select(2), "Worker survived payload completion")
                        self.assertEqual(os.read(probe.fileno(), 1024), b"")
                self.assertEqual(status["state"], "failed" if exit_code else "completed")

    def test_timeout_kills_only_its_own_process_group_including_children(self):
        code = ("import os,subprocess,sys,time\n"
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
                "print(os.getpgrp(), p.pid, flush=True)\ntime.sleep(60)\n")
        self.prepare(code, "timeout", timeout=0.5)
        started = time.monotonic()
        with patch.object(runner.os, "killpg", wraps=os.killpg) as kill:
            result = runner.execute(self.tree, "experiments/timeout")
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["returncode"], -signal.SIGKILL)
        leader, child = map(int, self.tree.read("experiments/timeout/run.log").split())
        kill.assert_called_once_with(leader, signal.SIGKILL)
        self.assertNotEqual(leader, os.getpgrp())
        status = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True).stdout.strip()
        self.assertTrue(not status or status.startswith("Z"), status)
        self.assertEqual(result["state"], "failed")

    def test_missing_bad_timeout_environment_and_required_inputs_refuse(self):
        original = records.read_record(self.tree, "experiments/e1/config.json")
        for value in (None, 0, -1, True, "10", 10 ** 400):
            config = records.strict(records.encoded(original))
            if value is None:
                del config["execution"]["timeout_seconds"]
            else:
                config["execution"]["timeout_seconds"] = value
            self.raw("experiments/e1/config.json", config)
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.execute(self.tree, "experiments/e1")
            self.assert_unstarted()
        for key in ("snapshot_sha256", "inputs", "execution", "parameters", "hypothesis"):
            config = dict(original)
            del config[key]
            self.raw("experiments/e1/config.json", config)
            with self.assertRaises(ValueError):
                runner.execute(self.tree, "experiments/e1")
            self.assert_unstarted()
        for inputs in ([dict(location="https://example.org/data", sha256="0" * 64)], [dict(path="data/train.txt", sha256="bad")]):
            self.raw("experiments/e1/config.json", dict(original, inputs=inputs))
            with self.assertRaises(ValueError):
                runner.execute(self.tree, "experiments/e1")
            self.assert_unstarted()

    def test_mutated_inputs_missing_manifests_and_changed_pins_refuse(self):
        for path in ("data/train.txt", "experiments/e1/snapshot/train.py", "experiments/e1/snapshot/manifest.json"):
            before = self.tree.read(path)
            self.raw(path, b"corrupt")
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.execute(self.tree, "experiments/e1")
            self.assert_unstarted()
            (self.root / path).unlink()
            with self.assertRaises((ValueError, OSError)):
                runner.execute(self.tree, "experiments/e1")
            self.assert_unstarted()
            self.raw(path, before)
        self.raw("experiments/e1/snapshot/extra.py", b"unlisted")
        with self.assertRaisesRegex(ValueError, "Manifest file set differs"):
            runner.execute(self.tree, "experiments/e1")
        self.assert_unstarted()

    def test_evaluation_checks_full_manifest_model_and_extra_inputs(self):
        config = self.evaluation()
        for key in ("target_sha256", "evaluation_sha256"):
            self.raw(EVAL + "/config.json", dict(config, **{key: "0" * 64}))
            with self.assertRaises(ValueError):
                runner.execute(self.tree, EVAL)
            self.assert_unstarted(EVAL)
        self.raw(EVAL + "/config.json", config)
        for path in ("evaluation/v1/definition.json", "evaluation/v1/evaluate.py", "evaluation/v1/manifest.json",
                     "evaluation/v1/samples.jsonl", "experiments/e1/model/rule.txt"):
            before = self.tree.read(path)
            self.raw(path, b"corrupt")
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.execute(self.tree, EVAL)
            self.assert_unstarted(EVAL)
            self.raw(path, before)
        self.raw(EVAL + "/config.json", dict(config, inputs=[dict(path="data/train.txt", sha256="0" * 64)]))
        with self.assertRaises(ValueError):
            runner.execute(self.tree, EVAL)
        self.assert_unstarted(EVAL)

    def test_explicit_finalization_preserves_process_status_and_selects_model(self):
        experiment = runner.execute(self.tree, "experiments/e1")
        self.assertEqual(experiment["state"], "completed")
        self.evaluation()
        status = runner.execute(self.tree, EVAL)
        self.publish(EVAL + "/outputs.jsonl", b'{"sample_id":"one","input":"synthetic","output":"evaluated fixture"}\n')
        self.publish(EVAL + "/status.json", dict(status, state="succeeded", metrics={"count": 1}), create=False)
        for key in records.PROCESS:
            if key in experiment:
                self.assertEqual(records.read_record(self.tree, "experiments/e1/status.json")[key], experiment[key])
            if key in status:
                self.assertEqual(records.read_record(self.tree, EVAL + "/status.json")[key], status[key])
        project = records.read_record(self.tree, "project.json")
        self.publish("project.json", dict(project, deliveries=["e1"]), create=False)
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["unfinished"], [])
        with self.assertRaises(ValueError):
            runner.execute(self.tree, EVAL)

    def test_conventional_locations_and_finalize_publish_model_then_measurement(self):
        self.prepare("import json,os; from pathlib import Path\n"
                     "out=Path(os.environ['TUNETUNE_OUTPUT']); (out/'weights.txt').write_text('w')\n"
                     "(out/'invoke.json').write_text(json.dumps({'argv':['python3','predict.py']}))\n"
                     "print(json.dumps({k:os.environ[k] for k in ('TUNETUNE_PROJECT','TUNETUNE_ATTEMPT')}))\n", "e3")
        with self.assertRaisesRegex(ValueError, "completed"):
            records.finalize(self.tree, "experiments/e3")
        self.assertEqual(runner.execute(self.tree, "experiments/e3")["state"], "completed")
        self.assertEqual(json.loads(self.tree.read("experiments/e3/run.log")),
                         {"TUNETUNE_PROJECT": str(self.root), "TUNETUNE_ATTEMPT": str(self.root / "experiments/e3")})
        status = records.finalize(self.tree, "experiments/e3")
        self.assertEqual(status["state"], "succeeded")
        self.assertEqual(status["target"], dict(kind="local", path="experiments/e3/model",
                                                sha256=self.sha("experiments/e3/model/manifest.json")))
        self.assertEqual(status["returncode"], 0)
        self.raw("tools/score.py", b"import json,os; from pathlib import Path\n"
                 b"out=Path(os.environ['TUNETUNE_OUTPUT'])\n"
                 b"assert (Path(os.environ['TUNETUNE_TARGET'])/'invoke.json').exists()\n"
                 b"assert (Path(os.environ['TUNETUNE_EVALUATION'])/'samples.jsonl').exists()\n"
                 b"(out/'outputs.jsonl').write_text(json.dumps({'sample_id':'one','output':'yes','scores':{'count':1}})+'\\n')\n"
                 b"(out/'metrics.json').write_text(json.dumps({'count':1}))\n")
        path = "experiments/e3/evals/r1"
        self.publish(path + "/config.json", dict(id="r1", evaluation_version="v1", target_sha256=status["target"]["sha256"],
                     evaluation_sha256=self.evaluation_hash,
                     execution=dict(argv=[sys.executable, "-B", "tools/score.py"], cwd=".", environment={"TUNETUNE_OUTPUT": "ignored"}, timeout_seconds=5)))
        self.assertEqual(runner.execute(self.tree, path)["state"], "completed", self.tree.read(path + "/run.log"))
        result = records.finalize(self.tree, path)
        self.assertEqual(result["metrics"], {"count": 1})
        self.assertEqual(records.read_record(self.tree, path + "/outputs.jsonl"),
                         [{"sample_id": "one", "input": "synthetic", "output": "yes", "scores": {"count": 1}}])
        self.assertTrue(records.validate(self.tree)["valid"])
        with self.assertRaisesRegex(ValueError, "completed"):
            records.finalize(self.tree, path)
        project = records.read_record(self.tree, "project.json")
        self.publish("project.json", dict(project, deliveries=["e3"]), create=False)
        self.assertFalse([w for w in records.validate(self.tree)["warnings"] if "invoke" in w])
        self.evaluation()
        self.publish("project.json", dict(project, deliveries=["e3", "e1"]), create=False)
        self.assertEqual([w for w in records.validate(self.tree)["warnings"] if "invoke" in w],
                         ["Delivery e1 has no invoke.json entry point"])

    def packaged(self, ident, body):
        self.prepare("import json,os,sys; from pathlib import Path\n"
                     "(Path(os.environ['TUNETUNE_OUTPUT'])/'invoke.json').write_text(json.dumps("
                     f"{{'argv':[sys.executable,'-B','experiments/{ident}/model/predict.py']}}))\n", ident)
        runner.execute(self.tree, f"experiments/{ident}")
        self.raw(f"experiments/{ident}/model/predict.py",
                 ("import json,sys\nrows=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]\n" + body).encode())
        records.finalize(self.tree, f"experiments/{ident}")

    LONG = "A synthetic final-check article that the method must never have read while being designed."

    def split_evaluation(self, version="v2", **definition):
        source = self.base / ("evaluation-" + version)
        source.mkdir()
        (source / "definition.json").write_bytes(records.encoded(dict(version=version, description="Fixture", rubric="Count",
            metrics=[dict(id="count", label="Count", direction="maximize")], command=[sys.executable, "score.py"], **definition)))
        (source / "samples.jsonl").write_bytes(records.encoded({"sample_id": "one", "input": "synthetic", "reference": ["alpha"]}).replace(b"\n", b"") + b"\n"
            + records.encoded({"sample_id": "two", "input": self.LONG, "reference": ["omega"], "split": "final"}).replace(b"\n", b"") + b"\n")
        return records.freeze(self.tree, self.root, source, f"evaluation/{version}")["manifest_sha256"]

    def test_freeze_requires_declared_final_check_or_reason(self):
        for name, samples in (("unsplit", b'{"sample_id":"one","input":"x"}\n'), ("only-final", b'{"sample_id":"one","input":"x","split":"final"}\n'),
                              ("unknown", b'{"sample_id":"one","input":"x","split":"test"}\n')):
            source = self.base / name
            source.mkdir()
            (source / "definition.json").write_bytes(records.encoded(dict(version="v9", description="Fixture", rubric="Count",
                metrics=[], command=[sys.executable, "score.py"])))
            (source / "samples.jsonl").write_bytes(samples)
            with self.assertRaisesRegex(ValueError, "final|development"):
                records.freeze(self.tree, self.root, source, "evaluation/v9")
            self.assertFalse(self.tree.exists("evaluation/v9"))
        with self.assertRaisesRegex(ValueError, "no_final_reason"):
            records.shape("evaluation/v9/definition.json", records.encoded(dict(version="v9", description="", rubric="", metrics=[],
                                                                                  command=["x"], no_final_reason=" ")))
        self.split_evaluation()

    def test_runs_see_only_their_split_and_final_publishes_totals_once(self):
        evaluation_hash = self.split_evaluation()
        config = self.evaluation()
        self.raw("tools/score.py", b"import json,os; from pathlib import Path\n"
                 b"out=Path(os.environ['TUNETUNE_OUTPUT']); rows=[json.loads(l) for l in open(os.environ['TUNETUNE_SAMPLES'])]\n"
                 b"(out/'outputs.jsonl').write_text(''.join(json.dumps({'sample_id':r['sample_id'],'output':['alpha']})+'\\n' for r in rows))\n"
                 b"(out/'metrics.json').write_text(json.dumps({'count':len(rows)}))\n")
        self.raw("tools/peek.py", b"import json,os; from pathlib import Path\n"
                 b"out=Path(os.environ['TUNETUNE_OUTPUT']); rows=[json.loads(l) for l in open(Path(os.environ['TUNETUNE_EVALUATION'])/'samples.jsonl')]\n"
                 b"(out/'outputs.jsonl').write_text(''.join(json.dumps({'sample_id':r['sample_id'],'output':['alpha']})+'\\n' for r in rows))\n"
                 b"(out/'metrics.json').write_text(json.dumps({'count':len(rows)}))\n")
        def run(ident, script, split=None):
            path = f"experiments/e1/evals/{ident}"
            self.publish(path + "/config.json", dict(id=ident, evaluation_version="v2", target_sha256=config["target_sha256"], evaluation_sha256=evaluation_hash,
                         **({"split": split} if split else {}), execution=dict(argv=[sys.executable, "-B", script], cwd=".", environment={}, timeout_seconds=5)))
            self.assertEqual(runner.execute(self.tree, path)["state"], "completed", self.tree.read(path + "/run.log"))
            return path
        development = run("dev", "tools/score.py")
        self.assertEqual([json.loads(line)["sample_id"] for line in self.tree.read(development + "/samples.jsonl").splitlines()], ["one"])
        self.assertEqual(records.finalize(self.tree, development)["metrics"], {"count": 1})
        self.assertEqual([row["sample_id"] for row in records.read_record(self.tree, development + "/outputs.jsonl")], ["one"])
        with self.assertRaisesRegex(ValueError, "split"):
            records.finalize(self.tree, run("peek", "tools/peek.py"))
        project = records.read_record(self.tree, "project.json")
        self.publish("project.json", dict(project, current_evaluation="v2", deliveries=["e1"]), create=False)
        self.assertIn("Delivery e1 has no final-check measurement on evaluation v2", records.validate(self.tree)["warnings"])
        final = run("final", "tools/score.py", "final")
        self.assertEqual(records.finalize(self.tree, final)["metrics"], {"count": 1})
        self.assertFalse(self.tree.exists(final + "/outputs.jsonl"))
        self.assertFalse(self.tree.exists(final + "/result/outputs.jsonl"))
        report = records.validate(self.tree)
        self.assertTrue(report["valid"], report)
        self.assertFalse([w for w in report["warnings"] if "final-check" in w])
        with self.assertRaisesRegex(ValueError, "immutable|aggregate"):
            self.publish(final + "/outputs.jsonl", b'{"sample_id":"two","input":"x","output":"y"}\n')
        self.publish("experiments/e1/evals/again/config.json", dict(id="again", evaluation_version="v2", split="final", target_sha256=config["target_sha256"],
                     evaluation_sha256=evaluation_hash, execution=dict(argv=[sys.executable, "-B", "tools/score.py"], cwd=".", environment={}, timeout_seconds=5)))
        with self.assertRaisesRegex(ValueError, "already has a final-check measurement"):
            runner.execute(self.tree, "experiments/e1/evals/again")
        self.assertFalse(self.tree.exists("experiments/e1/evals/again/run.log"))
        self.assertEqual(records.audit(self.tree)["final_checks"], {"v2": {"attempts": 2, "succeeded": 1, "experiments": ["e1"]}})

    def test_audit_flags_methods_that_contain_evaluation_material(self):
        self.split_evaluation()
        self.raw("proposal.json", dict(summary="Tags from the confirmed list: alpha", examples=[]))
        self.prepare(f"LABELS = ['alpha', 'omega']\nEXAMPLE = {self.LONG[:40]!r}\nopen('evaluation/v2/samples.jsonl')\n", "leaky")
        self.prepare("LABELS = ['alpha']\n", "clean")
        self.raw("experiments/clean/model/weights.bin", bytes(range(256)) * 4)
        findings = {(item["experiment"], item["check"]): item["values"] for item in records.audit(self.tree)["findings"]}
        self.assertEqual(findings[("leaky", "final_label")], ["omega"])
        self.assertEqual(findings[("leaky", "unconfirmed_vocabulary")], ["omega"])
        self.assertTrue(findings[("leaky", "final_content")])
        self.assertEqual(findings[("leaky", "reads_evaluation")], ["experiments/leaky/snapshot/train.py"])
        self.assertFalse([key for key in findings if key[0] in ("clean", "e1")])
        self.raw("experiments/leaky/status.json", dict(state="succeeded", updated_at=STAMP))
        project = records.read_record(self.tree, "project.json")
        self.raw("project.json", dict(project, deliveries=["leaky"]))
        warnings = records.validate(self.tree)["warnings"]
        self.assertIn("Delivery leaky audit final_label: omega", warnings)
        self.assertIn("Delivery leaky audit reads_evaluation: experiments/leaky/snapshot/train.py", warnings)
        self.raw("project.json", project)
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "records.py"), "audit", "--project", str(self.root)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["findings"]), 4)

    def test_compare_runs_entry_points_on_acceptance_inputs_and_merges(self):
        self.packaged("upper", "with open(sys.argv[2],'w') as f:\n    [f.write(json.dumps({'sample_id':r['sample_id'],'output':r['input'].upper()})+chr(10)) for r in rows]\n")
        self.packaged("broken", "sys.exit(3)\n")
        with self.assertRaises(OSError):
            runner.compare(self.tree, ["upper"], 5)
        self.raw("comparison/inputs.jsonl", b'{"sample_id":"a","input":"hi","note":"real"}\n{"sample_id":"b","input":"yo"}\n')
        with self.assertRaisesRegex(ValueError, "invoke.json"):
            self.evaluation()
            runner.compare(self.tree, ["e1"], 5)
        result = runner.compare(self.tree, ["upper", "broken"], 5)
        self.assertEqual(result["experiments"]["upper"]["outputs"], 2)
        self.assertEqual(result["experiments"]["broken"]["returncode"], 3)
        rows = records.read_record(self.tree, "comparison/outputs.jsonl")
        self.assertEqual([row["outputs"] for row in rows], [{"upper": "HI"}, {"upper": "YO"}])
        self.assertTrue(self.tree.exists("comparison/logs/broken.log"))
        self.raw("comparison/inputs.jsonl", b'{"sample_id":"a","input":"hi"}\n{"sample_id":"b","input":"changed"}\n')
        runner.compare(self.tree, ["broken"], 5)
        rows = records.read_record(self.tree, "comparison/outputs.jsonl")
        self.assertEqual([row["outputs"] for row in rows], [{"upper": "HI"}, {}])
        self.assertTrue(records.validate(self.tree)["valid"])
        self.assertFalse([p for p in (self.root / ".workspace/runtime").iterdir() if p.name.startswith("compare-")])

    def test_try_runs_one_local_input_without_recording_evidence(self):
        self.packaged("upper", "with open(sys.argv[2],'w') as f:\n    [f.write(json.dumps({'sample_id':r['sample_id'],'output':r['input'].upper()})+chr(10)) for r in rows]\n")
        self.packaged("broken", "print('model failed'); sys.exit(3)\n")
        before = sorted(str(p) for p in self.root.rglob("*") if ".workspace" not in p.parts)
        self.assertEqual(runner.try_model(self.tree, "upper", "new post", 5)["output"], "NEW POST")
        failed = runner.try_model(self.tree, "broken", "x", 5)
        self.assertEqual((failed["returncode"], "output" in failed), (3, False))
        self.assertIn("model failed", failed["log_tail"])
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*") if ".workspace" not in p.parts))
        self.assertFalse([p for p in (self.root / ".workspace/runtime").iterdir() if p.name.startswith("try-")])
        with self.assertRaisesRegex(ValueError, "Invalid experiment"):
            runner.try_model(self.tree, "../upper", "x", 5)
        with self.assertRaises((ValueError, OSError)):
            runner.try_model(self.tree, "missing", "x", 5)

    def shared(self, ident, requires):
        self.prepare("import json,os,sys; from pathlib import Path\n"
                     "(Path(os.environ['TUNETUNE_OUTPUT'])/'invoke.json').write_text(json.dumps("
                     f"{{'argv':[sys.executable,'-B','experiments/{ident}/model/predict.py'],'requires':{requires!r}}}))\n", ident)
        runner.execute(self.tree, f"experiments/{ident}")
        self.raw(f"experiments/{ident}/model/predict.py",
                 b"import json,sys\nw=open('resources/weights/w.bin').read()\nrows=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]\n"
                 b"with open(sys.argv[2],'w') as f:\n    [f.write(json.dumps({'sample_id':r['sample_id'],'output':w+r['input']})+chr(10)) for r in rows]\n")

    def test_models_reference_pinned_shared_weights_without_copying(self):
        self.raw("resources/weights/w.bin", b"W:")
        self.raw("resources/weights/.cache/meta", b"m")
        pinned = records.manifest(self.tree, "resources/weights")["manifest_sha256"]
        with self.assertRaisesRegex(ValueError, "experiment model or resource"):
            records.manifest(self.tree, "data")
        for ident in ("prompt-a", "prompt-b"):
            self.shared(ident, [{"path": "resources/weights", "sha256": pinned}])
            records.finalize(self.tree, f"experiments/{ident}")
            self.assertFalse(self.tree.exists(f"experiments/{ident}/model/w.bin"))
        self.assertEqual(runner.try_model(self.tree, "prompt-a", "post", 5)["output"], "W:post")
        self.raw("comparison/inputs.jsonl", b'{"sample_id":"a","input":"hi"}\n')
        self.assertEqual(runner.compare(self.tree, ["prompt-a", "prompt-b"], 5)["experiments"]["prompt-b"]["outputs"], 1)
        project = records.read_record(self.tree, "project.json")
        self.publish("project.json", dict(project, deliveries=["prompt-a"]), create=False)
        self.assertFalse([w for w in records.validate(self.tree)["warnings"] if "prompt-a" in w])
        self.raw("resources/weights/w.bin", b"changed")
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            runner.try_model(self.tree, "prompt-a", "post", 5)
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            runner.compare(self.tree, ["prompt-b"], 5)
        shutil.rmtree(self.root / "resources/weights")
        self.assertIn("Delivery prompt-a requires files that are missing", records.validate(self.tree)["warnings"])

    def test_model_entry_reports_serve_and_memory_and_compare_merges_served_rows(self):
        self.packaged("served", "with open(sys.argv[2],'w') as f:\n    [f.write(json.dumps({'sample_id':r['sample_id'],'output':'cold'})+chr(10)) for r in rows]\n")
        entry = records.model_entry(self.tree, "served")
        self.assertEqual((entry["serve"], entry["estimated"]), (None, True))
        self.assertGreater(entry["memory_gb"], 0)
        self.raw("comparison/inputs.jsonl", b'{"sample_id":"a","input":"hi"}\n{"sample_id":"b","input":"yo"}\n')
        self.raw(".workspace/runtime/answers.jsonl", b'{"sample_id":"a","input":"hi","output":"warm"}\n{"sample_id":"b","input":"old","output":"stale"}\n')
        report = runner.compare(self.tree, ["served"], 5, served={"served": ".workspace/runtime/answers.jsonl"})
        self.assertEqual(report["experiments"]["served"]["outputs"], 1)
        self.assertEqual([row["outputs"] for row in records.read_record(self.tree, "comparison/outputs.jsonl")], [{"served": "warm"}, {}])
        with self.assertRaisesRegex(ValueError, "Served outputs"):
            runner.compare(self.tree, ["served"], 5, served={"served": "comparison/inputs.jsonl"})
        self.prepare("import json,os,sys; from pathlib import Path\n"
                     "(Path(os.environ['TUNETUNE_OUTPUT'])/'invoke.json').write_text(json.dumps({'argv':['python3','p.py'],'serve':{'argv':['python3','s.py'],'memory_gb':-1}}))\n", "badserve")
        runner.execute(self.tree, "experiments/badserve")
        with self.assertRaisesRegex(ValueError, "memory_gb"):
            records.finalize(self.tree, "experiments/badserve")

    def test_invoke_requires_must_point_outside_the_model(self):
        self.shared("inside", [{"path": "experiments/inside/model/predict.py", "sha256": "0" * 64}])
        with self.assertRaisesRegex(ValueError, "outside the model"):
            records.finalize(self.tree, "experiments/inside")
        self.raw("resources/weights/w.bin", b"W:")
        self.shared("stale", [{"path": "resources/weights/w.bin", "sha256": "0" * 64}])
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            records.finalize(self.tree, "experiments/stale")
        self.assertEqual(records.read_record(self.tree, "experiments/stale/status.json")["state"], "completed")

    def test_finalize_refuses_incomplete_results_and_invalid_entry_points(self):
        self.prepare("import os; from pathlib import Path\n"
                     "(Path(os.environ['TUNETUNE_OUTPUT'])/'invoke.json').write_text('{\"argv\":[]}')\n", "bad")
        runner.execute(self.tree, "experiments/bad")
        with self.assertRaisesRegex(ValueError, "argument array"):
            records.finalize(self.tree, "experiments/bad")
        self.assertEqual(records.read_record(self.tree, "experiments/bad/status.json")["state"], "completed")
        self.evaluation()
        self.raw("experiments/e1/run.log", b"")
        self.publish(EVAL + "/status.json", dict(state="completed", updated_at=STAMP, returncode=0))
        self.raw(EVAL + "/result/outputs.jsonl", b'{"sample_id":"one","output":"yes"}\n')
        self.raw(EVAL + "/result/metrics.json", {})
        with self.assertRaisesRegex(ValueError, "declared metrics"):
            records.finalize(self.tree, EVAL)
        self.assertFalse(self.tree.exists(EVAL + "/outputs.jsonl"))
        self.raw(EVAL + "/result/metrics.json", {"count": 1})
        self.raw(EVAL + "/result/outputs.jsonl", b'{"sample_id":"other","output":"yes"}\n')
        with self.assertRaisesRegex(ValueError, "Unknown output"):
            records.finalize(self.tree, EVAL)
        self.raw(EVAL + "/result/outputs.jsonl", b'{"sample_id":"one","output":"yes"}\n')
        self.assertEqual(records.finalize(self.tree, EVAL)["state"], "succeeded")
        records.shape("evaluation/v2/samples.jsonl", b'{"sample_id":"a","input":"x","reference":"y","reference_status":"corrected"}\n')
        with self.assertRaisesRegex(ValueError, "reference_status"):
            records.shape("evaluation/v2/samples.jsonl", b'{"sample_id":"a","input":"x","reference_status":"approved"}\n')

    def test_started_states_reserved_logs_outputs_and_models_never_rerun(self):
        for state in ("running", "completed", "succeeded", "failed", "cancelled"):
            self.raw("experiments/e1/status.json", dict(state=state, updated_at=STAMP))
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "already started or completed"):
                runner.execute(self.tree, "experiments/e1")
        (self.root / "experiments/e1/status.json").unlink()
        for name in ("run.log", "outputs.jsonl", "model/file"):
            self.raw("experiments/e1/" + name, b"")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "already has"):
                runner.execute(self.tree, "experiments/e1")
            (self.root / "experiments/e1" / name).unlink()

    def test_pending_status_with_any_process_fact_cannot_start(self):
        for key, value in (("started_at", STAMP), ("config_sha256", "0" * 64), ("returncode", None), ("timed_out", False)):
            self.raw("experiments/e1/status.json", dict(state="pending", updated_at=STAMP, **{key: value}))
            with self.assertRaisesRegex(ValueError, "already started"):
                runner.execute(self.tree, "experiments/e1")
        self.raw("experiments/e1/status.json", dict(state="pending", updated_at=STAMP))
        self.assertEqual(runner.execute(self.tree, "experiments/e1")["state"], "completed")

    def test_symlink_cwd_log_input_record_and_project_are_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "cwd-link").symlink_to(outside, target_is_directory=True)
        config = records.read_record(self.tree, "experiments/e1/config.json")
        config["execution"]["cwd"] = "cwd-link"
        self.raw("experiments/e1/config.json", config)
        with self.assertRaises(OSError):
            runner.execute(self.tree, "experiments/e1")
        self.assert_unstarted()
        config["execution"]["cwd"] = "."
        self.raw("experiments/e1/config.json", config)
        (self.root / "experiments/e1/run.log").symlink_to(outside / "untouched")
        with self.assertRaises(ValueError):
            runner.execute(self.tree, "experiments/e1")
        self.assertFalse((outside / "untouched").exists())
        (self.root / "experiments/e1/run.log").unlink()
        (self.root / "data/train.txt").unlink()
        (self.root / "data/train.txt").symlink_to(outside / "missing")
        with self.assertRaises((OSError, ValueError)):
            runner.execute(self.tree, "experiments/e1")
        (self.root / "experiments/alias").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            runner.execute(self.tree, "experiments/alias")
        alias = self.base / "project-link"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            records.Tree(alias)
        self.assertEqual(list(outside.iterdir()), [])

    def test_lock_contention_invalid_paths_and_incompatible_schema_do_not_start(self):
        with self.tree.locked():
            result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", json.loads(result.stderr))
        self.assert_unstarted()
        for path in ("../experiments/e1", "experiments/e1/config.json", "/experiments/e1", "experiments/../e1", "assessments/r1"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.execute(self.tree, path)
        project = records.read_record(self.tree, "project.json")
        self.raw("project.json", dict(project, schema_version=1))
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unsupported schema_version", result.stderr)
        self.assert_unstarted()

    def test_incompatible_installed_metadata_refuses_execute_without_changes(self):
        for metadata in (dict(schema_min=2, schema_max=2), dict(schema_min=1, schema_max=3),
                         dict(schema_min=3, schema_max=4), dict(schema_min=3, schema_max=3), dict(schema_min=4, schema_max=True)):
            with self.subTest(metadata=metadata):
                self.raw(".workspace/manifest.json", metadata)
                before = {p.relative_to(self.root): p.read_bytes() if p.is_file() else None
                          for p in self.root.rglob("*")}
                with self.assertRaisesRegex(ValueError, "Incompatible kit schema range"):
                    runner.execute(self.tree, "experiments/e1")
                result = self.cli()
                self.assertEqual(result.returncode, 1)
                self.assertIn("Incompatible kit schema range", result.stderr)
                self.assert_unstarted()
                after = {p.relative_to(self.root): p.read_bytes() if p.is_file() else None
                         for p in self.root.rglob("*")}
                self.assertEqual(after, before)

    def test_spawn_failure_records_failed_status_and_permanent_log(self):
        with patch.object(runner.subprocess, "Popen", side_effect=OSError("Synthetic spawn failure")):
            status = runner.execute(self.tree, "experiments/e1")
        self.assertIsNone(status["returncode"])
        self.assertIn("spawn failure", status["error"])
        self.assertEqual(status["state"], "failed")
        with self.assertRaises(ValueError):
            runner.execute(self.tree, "experiments/e1")

    def test_payload_spawn_failure_reports_actual_error(self):
        config = records.read_record(self.tree, "experiments/e1/config.json")
        config["execution"]["argv"] = [str(self.base / "missing-executable")]
        self.raw("experiments/e1/config.json", config)
        with patch.object(runner.os, "killpg", wraps=os.killpg) as kill:
            status = runner.execute(self.tree, "experiments/e1")
        self.assertIsNone(status["returncode"])
        self.assertIn("missing-executable", status["error"])
        self.assertFalse(status["timed_out"])
        kill.assert_called_once()
        self.assertEqual(status["state"], "failed")

    def test_signal_during_spawn_retains_child_handle_for_cleanup(self):
        popen = subprocess.Popen
        spawned = []

        def spawn(*args, **kwargs):
            child = popen(*args, **kwargs)
            spawned.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        def interrupt(signum, frame):
            raise runner.InterruptedRun("Synthetic interruption during spawn")

        previous = signal.signal(signal.SIGTERM, interrupt)
        try:
            with patch.object(runner.subprocess, "Popen", side_effect=spawn):
                with self.assertRaises(runner.InterruptedRun):
                    runner.execute(self.tree, "experiments/e1")
            self.assertIsNotNone(spawned[0].returncode)
            status = records.read_record(self.tree, "experiments/e1/status.json")
            self.assertIn("Interrupted", status["error"])
            self.assertEqual(status["state"], "failed")
        finally:
            signal.signal(signal.SIGTERM, previous)
            for child in spawned:
                runner.kill_owned_group(child)

    def test_first_cli_signal_during_cleanup_preserves_result_and_reaps_owned_group(self):
        # Run the real CLI handlers in a separate interpreter, injecting the first
        # signal only after the private pipe has returned the payload's exit code.
        harness = r'''
import os, signal, sys
sys.path.insert(0, sys.argv.pop(1))
import run
stage, signum = sys.argv.pop(1), int(sys.argv.pop(1))
spawned, kills = [], []
received = injected = False
original_spawn = run.subprocess.Popen
original_kill = run.os.killpg
original_result = run.wait_result
original_mask = run.signal.pthread_sigmask
original_publish = run.publish_status
initial_mask = original_mask(signal.SIG_BLOCK, set())
def inject(where):
    global injected
    if received and not injected and stage == where:
        injected = True
        os.kill(os.getpid(), signum)
def spawn(*args, **kwargs):
    child = original_spawn(*args, **kwargs)
    spawned.append(child)
    original_wait = child.wait
    def wait(*args, **kwargs):
        inject("wait")
        return original_wait(*args, **kwargs)
    child.wait = wait
    return child
def result(*args):
    global received
    value = original_result(*args)
    received = True
    return value
def kill(group, sig):
    assert spawned[0].returncode is None, "Group kill after supervisor reaping"
    inject("killpg")
    kills.append(group)
    return original_kill(group, sig)
def mask(how, values):
    if how == signal.SIG_BLOCK and values:
        inject("mask")
    return original_mask(how, values)
def publish(tree, path, state, **details):
    if state != "running":
        inject("publish")
    return original_publish(tree, path, state, **details)
run.subprocess.Popen = spawn
run.wait_result = result
run.os.killpg = kill
run.signal.pthread_sigmask = mask
run.publish_status = publish
try:
    code = run.main()
    assert received and injected, "Signal injection was not reached"
    assert len(spawned) == 1 and kills == [spawned[0].pid], "Expected one owned group kill"
    assert spawned[0].returncode == -signal.SIGKILL, "Supervisor was not reaped"
    try:
        os.waitpid(spawned[0].pid, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        raise AssertionError("Supervisor remains waitable")
    assert original_mask(signal.SIG_BLOCK, set()) == initial_mask, "Signal mask not restored"
    sys.exit(code)
finally:
    # Bound failed regressions too; never clean up using a PID read from disk.
    run.os.killpg = original_kill
    for child in spawned:
        run.kill_owned_group(child)
'''
        for stage in ("mask", "killpg", "wait", "publish"):
            for sig in (signal.SIGINT, signal.SIGTERM):
                for exit_code in (0, 17):
                    with self.subTest(stage=stage, signal=sig, exit_code=exit_code):
                        ident = f"late-{stage}-{sig}-{exit_code}"
                        path = f"experiments/{ident}"
                        fifo = self.base / f"{ident}.fifo"
                        os.mkfifo(fifo)
                        worker = ("import os,signal\n"
                                  "signal.alarm(5)\n"
                                  f"fd=os.open({str(fifo)!r}, os.O_WRONLY)\n"
                                  "os.write(fd, b'ready')\n"
                                  "print('ready', flush=True)\n"
                                  "signal.pause()\n")
                        payload = ("import subprocess,sys\n"
                                   f"p=subprocess.Popen([sys.executable,'-c',{worker!r}], stdout=subprocess.PIPE)\n"
                                   "print(p.stdout.readline().decode().strip(), flush=True)\n"
                                   f"sys.exit({exit_code})\n")
                        self.prepare(payload, ident)
                        with os.fdopen(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK), "rb", buffering=0) as probe:
                            result = subprocess.run([sys.executable, "-B", "-c", harness, str(SCRIPTS), stage, str(sig),
                                                     "--project", str(self.root), "--path", path],
                                                    capture_output=True, text=True, timeout=10)
                            self.assertEqual(result.returncode, 1, result.stderr)
                            self.assertNotIn("Traceback", result.stderr)
                            self.assertIn("Signal", result.stderr)
                            with selectors.SelectSelector() as selector:
                                selector.register(probe, selectors.EVENT_READ)
                                self.assertTrue(selector.select(1), "Worker did not start")
                                self.assertEqual(os.read(probe.fileno(), 1024), b"ready")
                                self.assertTrue(selector.select(1), "Owned worker survived cleanup")
                                self.assertEqual(os.read(probe.fileno(), 1024), b"")
                        status = records.read_record(self.tree, path + "/status.json")
                        self.assertEqual(status["returncode"], exit_code)
                        self.assertFalse(status["timed_out"])
                        self.assertEqual(status["state"], "failed" if exit_code or stage == "mask" else "completed")
                        self.assertTrue(set(records.PROCESS) - {"error"} <= set(status))
                        self.assertEqual(status["config_sha256"], self.sha(path + "/config.json"))
                        before = self.tree.read(path + "/status.json")
                        with self.assertRaises(ValueError):
                            runner.execute(self.tree, path)
                        self.assertEqual(self.tree.read(path + "/status.json"), before)

    def test_sigterm_cleanup_leaves_status_and_prevents_retry(self):
        self.prepare("import os,time; print(os.getpid(), flush=True); time.sleep(60)\n", "interrupted", timeout=10)
        process = subprocess.Popen([sys.executable, "-B", str(SCRIPTS / "run.py"), "--project", str(self.root),
                                    "--path", "experiments/interrupted"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            log = self.root / "experiments/interrupted/run.log"
            deadline = time.monotonic() + 5
            while not log.exists() or not log.read_bytes().strip():
                self.assertIsNone(process.poll())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            process.send_signal(signal.SIGTERM)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 1, stderr)
            status = records.read_record(self.tree, "experiments/interrupted/status.json")
            self.assertEqual(status["returncode"], -signal.SIGKILL)
            self.assertEqual(status["state"], "failed")
            self.assertFalse(status["timed_out"])
            with self.assertRaises(ValueError):
                runner.execute(self.tree, "experiments/interrupted")
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
