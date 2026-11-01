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

    def test_incomplete_experiments_and_assessments(self):
        for directory, final in (("experiments/e", "status.json"), ("assessments/a", "result.json")):
            good = self.state()
            self.write(f"{directory}/config.json", {})
            result = self.state()
            self.assertIn(final, result["error"])
            self.assertEqual(result["files"], good["files"])
            self.write(f"{directory}/{final}", {})
            self.assertIsNone(self.state()["error"])

    def test_allowlist_jsonl_markdown_and_log_preview(self):
        for pattern in wb.PATTERNS:
            path = pattern.replace("*", "one")
            if path == "project.json":
                continue
            content = "{\"id\":1}\n\n{\"id\":2}\n" if path.endswith(".jsonl") else (
                "hello" if path.endswith((".md", ".log")) else {})
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
