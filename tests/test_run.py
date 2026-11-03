"""Run only synthetic commands in disposable projects; never train a real model."""
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "skills/research-workspace/scripts"
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
        self.raw("project.json", dict(schema_version=2, name="Synthetic", language="en", current_evaluation=None, deliveries=[]))
        self.raw("proposal.json", dict(summary="Fixture", sections=[], examples=[]))
        self.raw("resources.json", dict(items=[]))
        source = self.base / "evaluation"
        source.mkdir()
        (source / "definition.json").write_bytes(records.encoded(dict(version="v1", description="Fixture", rubric="Count",
            metrics=[dict(id="count", label="Count", direction="maximize")], command=[sys.executable, "evaluation/v1/evaluate.py"])))
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
        self.publish(path, dict(previous, state="succeeded", updated_at=STAMP, model_path="experiments/e1/model/rule.txt",
                                model_sha256=model_hash), create=not self.tree.exists(path))
        config = dict(id="r1", evaluation_version="v1", model_sha256=model_hash, evaluation_sha256=self.evaluation_hash,
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
        for key in ("model_sha256", "evaluation_sha256"):
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
        for metadata in (dict(schema_min=3, schema_max=3), dict(schema_min=1, schema_max=2),
                         dict(schema_min=2, schema_max=3), dict(schema_min=2, schema_max=True)):
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
