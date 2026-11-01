"""Stdlib integration tests for the local workspace transport."""
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

SOURCE = Path(__file__).resolve().parents[1] / "workspace" / "workspace.py"
SPEC = importlib.util.spec_from_file_location("workspace_server", SOURCE)
wb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wb)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.assets = self.base / "assets"
        self.root.mkdir()
        self.assets.mkdir()
        (self.assets / "index.html").write_text("<!doctype html><title>Workspace</title>")
        self.write("project.json", {"schema_version": 1, "name": "First"})
        self.server = self.start(self.root)
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"

    def start(self, root):
        server = wb.make_server(root, self.assets)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(stop)
        return server

    def write(self, name, content, root=None):
        path = (root or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, (dict, list)) else content,
                        encoding="utf-8")
        return path

    def request(self, method="GET", path="/api/state", body=None, headers=None, port=None):
        connection = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=3)
        self.addCleanup(connection.close)
        request_headers = {}
        if body is not None:
            body = json.dumps(body).encode() if isinstance(body, dict) else body
            request_headers = {"Content-Type": "application/json", "Origin": self.origin}
        request_headers.update(headers or {})
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        data = response.read()
        value = json.loads(data) if response.getheader("Content-Type", "").startswith("application/json") else data
        return response.status, value, dict(response.getheaders())

    def state(self):
        status, value, _ = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(set(value), {"files", "revision", "synced_at", "error"})
        return value

    def feedback(self, **changes):
        body = {"id": str(uuid.uuid4()), "kind": "comment", "text": "Please inspect this",
                "target": None, "target_sha256": None}
        body.update(changes)
        return body

    def post(self, body, **kwargs):
        return self.request("POST", "/api/feedback", body, **kwargs)

    def rename(self, body, **kwargs):
        return self.request("POST", "/api/project/name", body, **kwargs)

    def rename_body(self, name="Renamed"):
        return {"name": name, "expected_sha256": self.binding("project.json")["target_sha256"]}

    def binding(self, path):
        return {"target": path, "target_sha256": hashlib.sha256((self.root / path).read_bytes()).hexdigest()}

    def raw_request(self, request):
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as client:
            client.sendall(request.encode())
            client.shutdown(socket.SHUT_WR)
            data = b""
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                data += chunk
        return int(data.split(b" ", 2)[1])

    def test_live_refresh_deletion_and_independent_return_values(self):
        initial = self.state()
        self.assertIsNone(initial["error"])
        self.assertIn("T", initial["synced_at"])
        self.write("goal.json", {"examples": [{"id": "one"}]})
        fresh = self.state()
        self.assertNotEqual(fresh["revision"], initial["revision"])
        self.assertEqual(fresh["files"]["goal.json"]["content"]["examples"][0]["id"], "one")
        self.assertEqual(self.state()["revision"], fresh["revision"])
        (self.root / "goal.json").unlink()
        self.assertEqual(self.state()["revision"], initial["revision"])
        returned = self.server.reader.snapshot()
        returned["files"].clear()
        self.assertIn("project.json", self.server.reader.snapshot()["files"])

    def test_malformed_retains_entire_last_snapshot_and_recovers(self):
        good = self.state()
        self.write("goal.json", '{"examples":')
        bad = self.state()
        self.assertIn("goal.json", bad["error"])
        for key in ("files", "revision", "synced_at"):
            self.assertEqual(bad[key], good[key])
        self.write("goal.json", {"examples": []})
        self.assertIsNone(self.state()["error"])

    def test_no_prior_snapshot_and_required_version(self):
        for content in ({}, {"schema_version": True}, {"schema_version": 2}, [], '{"schema_version":1,"schema_version":1}'):
            with self.subTest(content=content):
                self.write("project.json", content)
                result = wb.Reader(self.root).snapshot()
                self.assertEqual(result["files"], {})
                self.assertTrue(result["error"])
        (self.root / "project.json").unlink()
        self.assertTrue(wb.Reader(self.root).snapshot()["error"])

    def test_known_array_fields_and_json_objects(self):
        for path, content in (("goal.json", {"examples": {}}), ("resources.json", {"items": "bad"}),
                              ("candidates.json", {"items": 1}), ("workspace.json", []),
                              ("releases/r.json", '{"score":NaN}'),
                              ("releases/r.json", '{"score":1e999}')):
            with self.subTest(path=path):
                written = self.write(path, content)
                self.assertTrue(self.state()["error"])
                written.unlink()
        self.assertIsNone(self.state()["error"])

    def test_incomplete_experiments_retain_snapshot(self):
        good = self.state()
        self.write("experiments/e/config.json", {})
        result = self.state()
        self.assertIn("experiments/e/status.json", result["error"])
        for key in ("files", "revision", "synced_at"):
            self.assertEqual(result[key], good[key])
        self.write("experiments/e/status.json", {})
        self.assertIsNone(self.state()["error"])

    def test_assessments_without_results_allow_other_refreshes(self):
        previous = self.state()
        config = {"experiment_id": "e", "evaluation_version": "v1"}
        self.server.reader.tree.publish("assessments/a/config.json", config)
        config_only = self.state()
        self.assertIsNone(config_only["error"])
        self.assertNotEqual(config_only["revision"], previous["revision"])
        self.assertEqual(config_only["files"]["assessments/a/config.json"]["content"], config)
        previous = config_only
        for state, training_state in ((None, "pending"), ("pending", "running"), ("running", "succeeded")):
            with self.subTest(state=state):
                if state is not None:
                    self.write("assessments/a/status.json", {"state": state})
                goal = {"examples": [{"id": training_state}]}
                self.write("goal.json", goal)
                self.write("experiments/e/config.json", {})
                self.write("experiments/e/status.json", {"state": training_state})
                fresh = self.state()
                self.assertIsNone(fresh["error"])
                self.assertNotEqual(fresh["revision"], previous["revision"])
                self.assertNotIn("assessments/a/result.json", fresh["files"])
                if state is not None:
                    self.assertEqual(fresh["files"]["assessments/a/status.json"]["content"]["state"], state)
                self.assertEqual(fresh["files"]["goal.json"]["content"], goal)
                self.assertEqual(fresh["files"]["experiments/e/status.json"]["content"]["state"], training_state)
                previous = fresh

    def test_assessment_results_allow_stale_running_status(self):
        for state in ("failed", "succeeded", "cancelled"):
            with self.subTest(state=state):
                directory = f"assessments/{state}"
                self.write(f"{directory}/config.json", {"experiment_id": "e"})
                self.write(f"{directory}/status.json", {"state": "running"})
                before = self.state()
                self.assertIsNone(before["error"])
                result = {"state": state, "metrics": {"accuracy": 0.9} if state == "succeeded" else {}}
                self.server.reader.tree.publish(f"{directory}/result.json", result)
                fresh = self.state()
                self.assertIsNone(fresh["error"])
                self.assertNotEqual(fresh["revision"], before["revision"])
                self.assertEqual(fresh["files"][f"{directory}/result.json"]["content"], result)
                self.assertEqual(fresh["files"][f"{directory}/status.json"], before["files"][f"{directory}/status.json"])

    def test_bad_assessment_records_retain_snapshot_and_recover(self):
        self.write("assessments/a/config.json", {})
        records = (("status.json", {"state": "running"}, ("succeeded", "failed", "cancelled")),
                   ("result.json", {"state": "succeeded", "metrics": {"accuracy": 0.9}}, ("pending", "running")))
        for filename, valid, _ in records:
            self.write(f"assessments/a/{filename}", valid)
        for filename, valid, invalid_states in records:
            path = f"assessments/a/{filename}"
            malformed = ([], "null", '{"state":', {}, {"state": None}, {"state": True},
                         {"state": 1}, {"state": []}, {"state": {}}, {"state": "unknown"})
            for index, content in enumerate((*malformed, *({"state": state} for state in invalid_states))):
                with self.subTest(path=path, content=content):
                    good = self.state()
                    self.assertIsNone(good["error"])
                    self.write(path, content)
                    goal = {"examples": [{"id": f"{filename}-{index}"}]}
                    self.write("goal.json", goal)
                    bad = self.state()
                    self.assertIn(path, bad["error"])
                    for key in ("files", "revision", "synced_at"):
                        self.assertEqual(bad[key], good[key])
                    self.write(path, valid)
                    recovered = self.state()
                    self.assertIsNone(recovered["error"])
                    self.assertEqual(recovered["files"]["goal.json"]["content"], goal)

    def test_allowlist_jsonl_markdown_and_log_preview(self):
        for pattern in wb.PATTERNS:
            path = pattern.replace("*", "one")
            if path == "project.json":
                continue
            content = "{\"id\":1}\n\n{\"id\":2}\n" if path.endswith(".jsonl") else (
                "hello" if path.endswith((".md", ".log")) else {})
            if path == "assessments/one/status.json":
                content = {"state": "running"}
            elif path == "assessments/one/result.json":
                content = {"state": "succeeded", "metrics": {}}
            self.write(path, content)
        self.write("code/private.json", {"secret": True})
        self.write("experiments/one/snapshot/source.json", {"secret": True})
        self.write("evaluation/draft/data.json", {"secret": True})
        log = self.write("experiments/one/train.log", "x" * (wb.LOG_PREVIEW_BYTES + 100))
        result = self.state()
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["files"]), len(wb.PATTERNS))
        self.assertEqual(result["files"]["assessments/one/outputs.jsonl"]["content"], [{"id": 1}, {"id": 2}])
        self.assertEqual(result["files"]["review.md"]["content"], "hello")
        self.assertEqual(len(result["files"]["experiments/one/train.log"]["content"]), wb.LOG_PREVIEW_BYTES)
        self.assertEqual(result["files"]["experiments/one/train.log"]["sha256"], hashlib.sha256(log.read_bytes()).hexdigest())
        self.write("assessments/one/outputs.jsonl", '{}\n[]\n')
        self.assertTrue(self.state()["error"])

    def test_read_bounds_retain_snapshot(self):
        good = self.state()
        with patch.object(wb, "MAX_FILES", 0):
            self.assertEqual(self.state()["revision"], good["revision"])
            self.assertTrue(self.state()["error"])
        with patch.object(wb, "MAX_ENTRIES", 0):
            self.assertTrue(self.state()["error"])
        with patch.object(wb, "MAX_TOTAL_BYTES", 1):
            self.assertTrue(self.state()["error"])
        self.write("review.md", "x" * (wb.MAX_FILE_BYTES + 1))
        self.assertTrue(self.state()["error"])

    def test_project_name_persists_and_preserves_other_fields(self):
        project = {"schema_version": 1, "name": "First", "language": "zh",
                   "current_evaluation": "v2", "custom": {"values": [1, False, None, "研究"]}}
        self.write("project.json", project)
        goal = self.write("goal.json", {"examples": []})
        goal_before = goal.read_bytes()
        before = self.state()
        status, saved, _ = self.rename(self.rename_body("  New name  "))
        self.assertEqual(status, 200)
        raw = (self.root / "project.json").read_bytes()
        self.assertEqual(saved, {"name": "New name", "sha256": hashlib.sha256(raw).hexdigest()})
        self.assertEqual(json.loads(raw), dict(project, name="New name"))
        fresh = self.state()
        self.assertIsNone(fresh["error"])
        self.assertNotEqual(fresh["revision"], before["revision"])
        self.assertEqual(fresh["files"]["project.json"], {"content": dict(project, name="New name"),
                                                        "sha256": saved["sha256"]})
        self.assertEqual(wb.Reader(self.root).snapshot()["files"], fresh["files"])
        self.assertEqual(goal.read_bytes(), goal_before)
        self.assertFalse((self.root / "feedback").exists())
        self.assertEqual(list(self.root.glob(".pending-*")), [])

    def test_project_name_trims_unicode_and_counts_codepoints(self):
        for name in ("研究 Café", "e\u0301" * 60, "\U00020000" * 120):
            with self.subTest(name=name):
                status, saved, _ = self.rename(self.rename_body(" \u3000" + name + "\u00a0 "))
                self.assertEqual(status, 200)
                self.assertEqual(saved["name"], name)
                self.assertEqual(json.loads((self.root / "project.json").read_bytes())["name"], name)

    def test_project_name_validation(self):
        before = (self.root / "project.json").read_bytes()
        body = self.rename_body()
        invalid = [None, False, 1, [], {}, "", " \u3000\u00a0", "x" * 121,
                   "\U00020000" * 121, "e\u0301" * 60 + "e", "\ud800", "\udfff", "\nName", "Name\t"]
        invalid.extend("a" + chr(code) + "b" for code in (*range(32), *range(127, 160)))
        for name in invalid:
            with self.subTest(name=name):
                self.assertEqual(self.rename(dict(body, name=name))[0], 400)
        for digest in (None, False, 1, [], {}, "", "0" * 63, "0" * 65, "A" * 64, "g" * 64, "0" * 64 + "\n"):
            with self.subTest(digest=digest):
                self.assertEqual(self.rename(dict(body, expected_sha256=digest))[0], 400)
        for invalid_body in ({}, {"name": "Name"}, {"expected_sha256": body["expected_sha256"]},
                             dict(body, path="project.json"), dict(body, schema_version=2),
                             b"[]", b"null", b"{broken", b'{"name":"a","name":"b"}',
                             b'{"name":NaN}', b'"\xff"'):
            with self.subTest(body=invalid_body):
                self.assertEqual(self.rename(invalid_body)[0], 400)
        self.assertEqual((self.root / "project.json").read_bytes(), before)
        self.assertFalse((self.root / ".workspace").exists())

    def test_project_name_stale_hash_checks_disk_and_recovers(self):
        body = self.rename_body()
        self.state()
        path = self.write("project.json", {"schema_version": 1, "name": "Agent edit", "language": "en"})
        before = path.read_bytes()
        self.assertEqual(self.rename(body)[0], 409)
        self.assertEqual(path.read_bytes(), before)
        body = self.rename_body()
        self.assertEqual(self.rename(body)[0], 200)
        self.assertEqual(json.loads(path.read_bytes())["language"], "en")
        self.assertEqual(self.rename(body)[0], 409)
        path.unlink()
        self.assertEqual(self.rename(body)[0], 409)
        self.assertFalse(path.exists())
        self.assertEqual(list(self.root.glob(".pending-*")), [])

    def test_project_name_requires_valid_current_schema_and_file_limits(self):
        for project in ({}, {"schema_version": True}, {"schema_version": 1.0}, {"schema_version": 2},
                        [], "null", '{"schema_version":', '{"schema_version":1,"schema_version":1}',
                        '{"schema_version":1,"custom":1e999}'):
            with self.subTest(project=project):
                path = self.write("project.json", project)
                before = path.read_bytes()
                self.assertEqual(self.rename(self.rename_body())[0], 409)
                self.assertEqual(path.read_bytes(), before)
        for project, limit in (({"schema_version": 1, "name": "First"}, 64),
                               ({"schema_version": 1, "custom": "x" * 128}, 64)):
            with self.subTest(project=project):
                path = self.write("project.json", project)
                before = path.read_bytes()
                with patch.object(wb, "MAX_FILE_BYTES", limit):
                    self.assertEqual(self.rename(self.rename_body("研" * 120))[0], 409)
                self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".pending-*")), [])

    def test_project_name_cooperates_with_canonical_records_lock(self):
        source = SOURCE.parents[1] / "skills" / "research-workspace" / "scripts" / "records.py"
        spec = importlib.util.spec_from_file_location("canonical_records", source)
        records = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(records)
        tree = records.Tree(self.root.resolve())
        self.addCleanup(tree.close)
        lock = self.write(".workspace/runtime/records.lock", "keep this lock inode")
        before = (self.root / "project.json").read_bytes()
        body = self.rename_body()
        with tree.locked():
            self.assertEqual(self.rename(body)[0], 409)
            self.assertEqual((self.root / "project.json").read_bytes(), before)
        replace = os.replace
        def check_lock(*args, **kwargs):
            with self.assertRaises(BlockingIOError):
                with tree.locked():
                    self.fail("Canonical writer acquired the name writer's lock")
            return replace(*args, **kwargs)
        with patch.object(wb.os, "replace", side_effect=check_lock):
            self.assertEqual(self.rename(body)[0], 200)
        self.assertEqual(lock.read_text(), "keep this lock inode")
        with tree.locked():
            pass

    def test_project_name_atomic_replace_and_independent_reader_contention(self):
        before = (self.root / "project.json").read_bytes()
        body = self.rename_body()
        other = wb.Reader(self.root)
        replace = os.replace
        def check_replace(source, destination, **kwargs):
            self.assertTrue(source.startswith(".pending-"))
            self.assertEqual(destination, "project.json")
            self.assertEqual(kwargs["src_dir_fd"], kwargs["dst_dir_fd"])
            self.assertEqual((self.root / "project.json").read_bytes(), before)
            self.assertEqual(sync.call_count, 1)
            with self.assertRaises(wb.FeedbackError) as error:
                wb.save_project_name(other, body)
            self.assertEqual(error.exception.status, 409)
            return replace(source, destination, **kwargs)
        with (self.root / "project.json").open("rb") as old:
            with patch.object(wb.os, "fsync", wraps=os.fsync) as sync:
                with patch.object(wb.os, "replace", side_effect=check_replace):
                    self.assertEqual(self.rename(body)[0], 200)
                self.assertEqual(sync.call_count, 2)
            self.assertEqual(old.read(), before)
        self.assertEqual(list(self.root.glob(".pending-*")), [])
        saved = wb.save_project_name(other, self.rename_body("Second rename"))
        self.assertEqual(saved["name"], "Second rename")

    def test_project_name_uses_reader_lock(self):
        with patch.object(self.server.reader, "lock", wraps=self.server.reader.lock) as lock:
            self.assertEqual(self.rename(self.rename_body())[0], 200)
            lock.__enter__.assert_called_once()
            lock.__exit__.assert_called_once()

    def test_project_name_failed_publication_cleans_up_and_unlocks(self):
        before = (self.root / "project.json").read_bytes()
        body = self.rename_body()
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with patch.object(wb.os, operation, side_effect=OSError("Cannot publish")):
                    self.assertEqual(self.rename(body)[0], 409)
                self.assertEqual((self.root / "project.json").read_bytes(), before)
                self.assertEqual(list(self.root.glob(".pending-*")), [])
        self.assertEqual(self.rename(body)[0], 200)

    def test_project_name_symlink_and_nonregular_file_protection(self):
        body = self.rename_body()
        outside = self.write("outside.json", {"schema_version": 1, "name": "Outside"}, root=self.base)
        before = outside.read_bytes()
        path = self.root / "project.json"
        path.unlink()
        for target in (outside, self.base / "missing.json"):
            with self.subTest(target=target):
                path.symlink_to(target)
                self.assertEqual(self.rename(body)[0], 409)
                self.assertTrue(path.is_symlink())
                path.unlink()
        os.mkfifo(path)
        self.assertEqual(self.rename(body)[0], 409)
        path.unlink()
        path.mkdir()
        self.assertEqual(self.rename(body)[0], 409)
        path.rmdir()
        self.write("project.json", {"schema_version": 1, "name": "First"})
        linked_root = self.base / "linked-project"
        linked_root.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(wb.FeedbackError) as error:
            wb.save_project_name(wb.Reader(linked_root), body)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(outside.read_bytes(), before)
        self.assertFalse((self.base / "missing.json").exists())

    def test_project_name_lock_symlinks_and_nonregular_files(self):
        body = self.rename_body()
        before = (self.root / "project.json").read_bytes()
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = self.write("records.lock", "outside lock", root=outside)
        for relative, target in ((".workspace", outside), (".workspace/runtime", outside),
                                 (".workspace/runtime/records.lock", sentinel),
                                 (".workspace/runtime/records.lock", outside / "missing")):
            with self.subTest(relative=relative, target=target):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(target)
                self.assertEqual(self.rename(body)[0], 409)
                self.assertTrue(path.is_symlink())
                path.unlink()
        lock = self.root / ".workspace/runtime/records.lock"
        os.mkfifo(lock)
        self.assertEqual(self.rename(body)[0], 409)
        lock.unlink()
        lock.mkdir()
        self.assertEqual(self.rename(body)[0], 409)
        self.assertEqual((self.root / "project.json").read_bytes(), before)
        self.assertEqual(sentinel.read_text(), "outside lock")
        self.assertEqual(list(outside.iterdir()), [sentinel])
        self.assertEqual(list(self.root.glob(".pending-*")), [])

    def test_project_name_rechecks_destination_before_replace(self):
        body = self.rename_body()
        path = self.root / "project.json"
        outside = self.write("outside.json", {"schema_version": 1, "name": "Outside"}, root=self.base)
        before = outside.read_bytes()
        fsync = os.fsync
        def swap_destination(fd):
            path.unlink()
            path.symlink_to(outside)
            return fsync(fd)
        with patch.object(wb.os, "fsync", side_effect=swap_destination):
            self.assertEqual(self.rename(body)[0], 409)
        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".pending-*")), [])

    def test_project_name_host_origin_and_request_limits(self):
        body = self.rename_body()
        before = (self.root / "project.json").read_bytes()
        for host in ("evil.example", "127.0.0.1", "127.0.0.1:1"):
            self.assertEqual(self.rename(body, headers={"Host": host})[0], 403)
        for origin in ("", "null", "http://evil.example", f"http://localhost:{self.port}", self.origin + "/"):
            self.assertEqual(self.rename(body, headers={"Origin": origin})[0], 403)
        self.assertEqual(self.rename(body, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.rename(body, headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.rename(b"x" * (wb.MAX_BODY_BYTES + 1))[0], 413)
        base = f"POST /api/project/name HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\n"
        self.assertEqual(self.raw_request(base + "Content-Length: 2\r\n\r\n{}"), 403)
        base += f"Origin: {self.origin}\r\n"
        for headers, status in (("", 411), ("Content-Length: 2\r\nContent-Length: 2\r\n", 411),
                                ("Content-Length: 0\r\n", 413), ("Content-Length: 3\r\n", 400),
                                (f"Origin: {self.origin}\r\nContent-Length: 2\r\n", 403)):
            self.assertEqual(self.raw_request(base + headers + "\r\n{}"), status)
        for path in ("/api/project", "/api/project/name/", "/api/project/name?other=1"):
            self.assertEqual(self.request("POST", path, body)[0], 404)
        self.assertEqual(self.request(path="/api/project/name")[0], 404)
        self.assertEqual((self.root / "project.json").read_bytes(), before)
        self.assertEqual(self.rename(body, headers={"Host": f"localhost:{self.port}",
                                                    "Origin": f"http://localhost:{self.port}"})[0], 200)

    def test_project_name_keeps_feedback_immutable_and_hash_bound(self):
        body = self.feedback(**self.binding("project.json"))
        status, saved, _ = self.post(body)
        self.assertEqual(status, 201)
        path = self.root / f"feedback/incoming/{body['id']}.json"
        before = path.read_bytes()
        self.assertEqual(self.rename(self.rename_body())[0], 200)
        self.assertEqual(self.post(body)[:2], (200, saved))
        self.assertEqual(self.post(dict(body, id=str(uuid.uuid4())))[0], 409)
        self.assertEqual(self.post(self.feedback(**self.binding("project.json")))[0], 201)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads((self.root / "project.json").read_bytes())["name"], "Renamed")

    def test_feedback_immutable_idempotency_and_business_unchanged(self):
        before = (self.root / "project.json").read_bytes()
        body = self.feedback(**self.binding("project.json"))
        status, saved, _ = self.post(body)
        self.assertEqual(status, 201)
        self.assertEqual(saved["source"], "workspace")
        self.assertIn("created_at", saved)
        path = self.root / f"feedback/incoming/{body['id']}.json"
        self.assertEqual(json.loads(path.read_text()), saved)
        self.assertEqual(self.post(body)[:2], (200, saved))
        self.assertEqual(self.post(dict(body, text="Changed"))[0], 409)
        self.assertEqual((self.root / "project.json").read_bytes(), before)
        self.assertEqual(list(path.parent.glob(".pending-*")), [])
        self.assertIn(str(path.relative_to(self.root)), self.state()["files"])

    def test_stale_hash_validated_against_disk_without_polling(self):
        body = self.feedback(**self.binding("project.json"))
        self.state()
        self.write("project.json", {"schema_version": 1, "name": "changed"})
        self.assertEqual(self.post(body)[0], 409)
        self.assertFalse((self.root / "feedback").exists())
        self.assertEqual(self.post(self.feedback(target="goal.json", target_sha256="0" * 64))[0], 409)

    def test_response_binding_options_closed_handled_and_retry(self):
        request_id = "question-1"
        path = f"feedback/requests/{request_id}.json"
        self.write(path, {"id": request_id, "options": ["yes", {"id": "no"}]})
        body = self.feedback(kind="response", request_id=request_id, choice="yes", sample_id="sample-1", **self.binding(path))
        self.assertEqual(self.post(dict(body, request_id="wrong"))[0], 400)
        self.assertEqual(self.post(dict(body, choice="maybe"))[0], 400)
        self.assertEqual(self.post(body)[0], 201)
        self.assertTrue((self.root / f"feedback/responses/{body['id']}.json").is_file())
        self.write("feedback/handled/record.json", {"feedback_id": body["id"]})
        self.assertEqual(self.post(dict(body, id=str(uuid.uuid4())))[0], 409)
        self.assertEqual(self.post(body)[0], 200)
        (self.root / "feedback/handled/record.json").unlink()
        self.write(path, {"id": request_id, "status": "closed"})
        closed = self.feedback(kind="response", request_id=request_id, **self.binding(path))
        self.assertEqual(self.post(closed)[0], 409)

    def test_response_evidence_and_missing_choice(self):
        path = "feedback/requests/q.json"
        self.write(path, {"id": "q", "options": ["yes"], **self.binding("project.json")})
        body = self.feedback(kind="response", request_id="q", **self.binding(path))
        self.assertEqual(self.post(body)[0], 400)
        self.write("project.json", {"schema_version": 1, "name": "updated"})
        self.assertEqual(self.post(dict(body, choice="yes"))[0], 409)
        self.write(path, {"id": "q", "options": []})
        body = self.feedback(kind="response", request_id="q", **self.binding(path))
        self.assertEqual(self.post(body)[0], 201)
        self.assertEqual(self.post(dict(body, id=str(uuid.uuid4())))[0], 409)
        self.assertEqual(self.post(body)[0], 200)

    def test_all_non_response_kinds_and_cross_kind_id_conflict(self):
        for kind in ("comment", "change", "preference", "acceptance"):
            self.assertEqual(self.post(self.feedback(kind=kind))[0], 201)
        self.write("feedback/requests/q.json", {})
        body = self.feedback()
        self.assertEqual(self.post(body)[0], 201)
        self.assertEqual(self.post(dict(body, kind="response", request_id="q", **self.binding("feedback/requests/q.json")))[0], 409)

    def test_full_length_unicode_feedback(self):
        body = self.feedback(text="研" * wb.MAX_TEXT_LENGTH)
        self.assertEqual(self.post(body)[0], 201)
        self.assertEqual(self.post(body)[0], 200)

    def test_invalid_feedback_fields(self):
        for changes in ({"id": "../escape"}, {"id": "x/y"}, {"id": ".hidden"}, {"id": "x" * 129},
                        {"kind": "run"}, {"text": "  "}, {"text": "x" * (wb.MAX_TEXT_LENGTH + 1)},
                        {"target": "code/source.json", "target_sha256": "0" * 64},
                        {"target": "../project.json", "target_sha256": "0" * 64},
                        {"target": "project.json", "target_sha256": None}, {"target_sha256": "0" * 64},
                        {"request_id": "../q"}, {"source": "agent"}, {"choice": []}):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(self.feedback(**changes))[0], 400)
        self.assertEqual(self.post(b"[]")[0], 400)
        self.assertEqual(self.post(b"{broken")[0], 400)

    def test_host_origin_and_request_framing(self):
        for host in ("evil.example", "127.0.0.1", "127.0.0.1:1", f"127.0.0.1:{self.port}.evil", f"localhost:{self.port}."):
            self.assertEqual(self.request(headers={"Host": host})[0], 403)
            self.assertEqual(self.request("DELETE", headers={"Host": host})[0], 403)
        for origin in ("null", "http://evil.example", f"http://localhost:{self.port}", self.origin + "/"):
            self.assertEqual(self.post(self.feedback(), headers={"Origin": origin})[0], 403)
        self.assertEqual(self.post(self.feedback(), headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.post(self.feedback(), headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.post(b"x" * (wb.MAX_BODY_BYTES + 1))[0], 413)
        base = f"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\n"
        self.assertEqual(self.raw_request(base + "Content-Length: 2\r\n\r\n{}"), 403)
        base += f"Origin: {self.origin}\r\n"
        self.assertEqual(self.raw_request(base + "\r\n"), 411)
        self.assertEqual(self.raw_request(base + "Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}"), 411)
        self.assertEqual(self.raw_request(f"GET /api/state HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nHost: evil\r\n\r\n"), 403)
        self.assertEqual(self.request(headers={"Host": f"localhost:{self.port}"})[0], 200)
        self.assertEqual(self.post(self.feedback(), headers={"Host": f"localhost:{self.port}", "Origin": f"http://localhost:{self.port}"})[0], 201)

    def test_static_assets_csp_and_traversal(self):
        status, content, headers = self.request(path="/")
        self.assertEqual(status, 200)
        self.assertIn(b"Workspace", content)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        for path in ("/../project/project.json", "/%2e%2e/project/project.json", "/%2fetc/passwd",
                     "/project.json", "/api/project", "/.hidden", "/%00", "/a%5c..%5cproject.json"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)[0], 404)
        (self.assets / "leak.json").symlink_to(self.root / "project.json")
        (self.assets / "linked").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.request(path="/leak.json")[0], 404)
        self.assertEqual(self.request(path="/linked/project.json")[0], 404)

    def test_reader_symlinks_and_nonregular_files(self):
        good = self.state()
        secret = self.write("secret.json", {"secret": "hidden"})
        linked = self.root / "goal.json"
        linked.symlink_to(secret)
        self.assertEqual(self.state()["files"], good["files"])
        self.assertIn("Symlink", self.state()["error"])
        linked.unlink()
        (self.root / "experiments").symlink_to(self.base)
        self.assertTrue(self.state()["error"])
        (self.root / "experiments").unlink()
        os.mkfifo(linked)
        self.assertTrue(self.state()["error"])
        linked.unlink()
        (self.root / "code").symlink_to(self.base)
        self.assertIsNone(self.state()["error"])

    def test_feedback_symlinks_at_every_level(self):
        outside = self.base / "outside"
        outside.mkdir()
        feedback = self.root / "feedback"
        feedback.symlink_to(outside)
        self.assertEqual(self.post(self.feedback())[0], 409)
        feedback.unlink()
        feedback.mkdir()
        incoming = feedback / "incoming"
        incoming.symlink_to(outside)
        self.assertEqual(self.post(self.feedback())[0], 409)
        incoming.unlink()
        incoming.mkdir()
        body = self.feedback()
        (incoming / f"{body['id']}.json").symlink_to(outside / "missing.json")
        self.assertEqual(self.post(body)[0], 409)
        self.assertEqual(list(outside.iterdir()), [])

    def test_parallel_immutable_submissions(self):
        body = self.feedback()
        results = []
        def submit():
            results.append(wb.save_feedback(self.server.reader, body))
        threads = [threading.Thread(target=submit) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertEqual(len(results), 8)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertTrue(all(saved == results[0][0] for saved, _ in results))

    def test_atomic_publication_across_independent_readers(self):
        body = self.feedback()
        barrier = threading.Barrier(6)
        results, errors = [], []
        def submit():
            reader = wb.Reader(self.root)
            barrier.wait(timeout=3)
            try:
                results.append(wb.save_feedback(reader, body))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=submit) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 6)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertTrue(all(saved == results[0][0] for saved, _ in results))

    def test_cli_rejects_symlinked_runtime_without_external_writes(self):
        outside = self.base / "outside-runtime"
        outside.mkdir()
        (self.root / ".workspace").symlink_to(outside)
        result = subprocess.run([sys.executable, "-B", str(SOURCE), "--project", str(self.root)],
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue((self.root / ".workspace").is_symlink())

    def test_independent_projects(self):
        other = self.base / "second"
        other.mkdir()
        self.write("project.json", {"schema_version": 1, "name": "Second"}, root=other)
        server = self.start(other)
        status, state, _ = self.request(port=server.server_address[1])
        self.assertEqual(status, 200)
        self.assertEqual(state["files"]["project.json"]["content"]["name"], "Second")
        self.assertEqual(self.state()["files"]["project.json"]["content"]["name"], "First")
        self.assertEqual(self.post(self.feedback())[0], 201)
        self.assertFalse((other / "feedback").exists())

    def test_cli_url_runtime_and_keyboard_interrupt(self):
        process = subprocess.Popen([sys.executable, "-B", str(SOURCE), "--project", str(self.root),
                                    "--assets", str(self.assets), "--port", "0"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        self.addCleanup(cleanup)
        import select
        ready, _, _ = select.select([process.stdout], [], [], 5)
        self.assertTrue(ready, "CLI did not print a flushed URL")
        url = process.stdout.readline().strip()
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        port = int(url.rsplit(":", 1)[1])
        runtime = self.root / f".workspace/runtime/server-{port}.json"
        self.assertEqual(json.loads(runtime.read_text()), {"project": str(self.root), "pid": process.pid, "url": url})
        self.assertEqual(self.request(port=port)[0], 200)
        process.send_signal(signal.SIGINT)
        _, errors = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, errors)
        self.assertFalse(runtime.exists())


if __name__ == "__main__":
    unittest.main()
