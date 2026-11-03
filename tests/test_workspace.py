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

SOURCE = Path(__file__).resolve().parents[1] / "workspace" / "workspace.py"
SPEC = importlib.util.spec_from_file_location("workspace_server", SOURCE)
wb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wb)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.assets = self.base / "assets"
        self.root.mkdir()
        self.assets.mkdir()
        (self.assets / "index.html").write_text("<!doctype html><title>Workspace</title>")
        self.write("project.json", {"schema_version": 4, "name": "First"})
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
        self.assertEqual(set(value), {"files", "revision", "synced_at", "error", "observations", "view", "acceptance"})
        return value


    def rename(self, body, **kwargs):
        return self.request("POST", "/api/project/name", body, **kwargs)


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

    def install_helpers(self):
        scripts = Path(__file__).resolve().parents[1] / "skills/research-workspace/scripts"
        target = self.root / ".agents/skills/research-workspace/scripts"
        target.mkdir(parents=True)
        for name in ("records.py", "run.py"):
            (target / name).write_bytes((scripts / name).read_bytes())
        server = self.start(self.root)
        return server.server_address[1]

    def test_panel_responses_view_and_runs_need_installed_tools(self):
        self.assertEqual(self.request("POST", "/api/responses", {"kind": "proposal", "decision": "approve", "target_sha256": "0" * 64})[0], 503)
        self.assertEqual(self.request("POST", "/api/try", {"experiment": "e1", "input": "x"})[0], 503)
        port = self.install_helpers()
        origin = {"Origin": f"http://127.0.0.1:{port}"}
        self.write("project.json", {"schema_version": 4, "name": "First", "language": "en", "current_evaluation": None, "deliveries": []})
        self.write("proposal.json", {"summary": "Tags", "examples": []})
        self.write("resources.json", {"items": []})
        shown = hashlib.sha256((self.root / "proposal.json").read_bytes()).hexdigest()
        status, value, _ = self.request("POST", "/api/responses", {"kind": "proposal", "decision": "revise", "target_sha256": shown, "note": "更宽的标签"}, origin, port)
        self.assertEqual((status, value["decision"]), (200, "revise"))
        self.assertEqual(self.request("POST", "/api/responses", {"kind": "proposal", "decision": "approve", "target_sha256": "0" * 64}, origin, port)[0], 409)
        self.assertEqual(self.request("POST", "/api/responses", {"kind": "proposal", "decision": "approve"}, origin, port)[0], 400)
        state = self.request(port=port)[1]
        self.assertIn(f"responses/{value['id']}.json", state["files"])
        (self.root / ".workspace").mkdir(exist_ok=True)
        (self.root / ".workspace/view.json").write_text(json.dumps({"revision": 2, "open": ["review", "bogus"], "focus": {"experiment": "../x"},
                                                                   "attention": [{"view": "review", "message": "请审阅"}]}))
        view = self.request(port=port)[1]["view"]
        self.assertEqual(view, {"revision": 2, "open": ["review"], "focus": {}, "attention": [{"view": "review", "message": "请审阅"}]})
        status, value, _ = self.request("POST", "/api/try", {"experiment": "missing", "input": "x"}, origin, port)
        self.assertEqual(status, 200)
        self.assertIn("error", value)
        self.assertEqual(self.request("POST", "/api/acceptance/run", {"experiments": ["../x"]}, origin, port)[0], 400)

    def test_live_refresh_deletion_and_independent_return_values(self):
        initial = self.state()
        self.assertIsNone(initial["error"])
        self.assertIn("T", initial["synced_at"])
        self.write("proposal.json", {"examples": [{"id": "one"}]})
        fresh = self.state()
        self.assertNotEqual(fresh["revision"], initial["revision"])
        self.assertEqual(fresh["files"]["proposal.json"]["content"]["examples"][0]["id"], "one")
        self.assertEqual(self.state()["revision"], fresh["revision"])
        (self.root / "proposal.json").unlink()
        self.assertEqual(self.state()["revision"], initial["revision"])
        returned = self.server.reader.snapshot()
        returned["files"].clear()
        self.assertIn("project.json", self.server.reader.snapshot()["files"])

    def test_malformed_retains_entire_last_snapshot_and_recovers(self):
        good = self.state()
        self.write("proposal.json", '{"examples":')
        bad = self.state()
        self.assertIn("proposal.json", bad["error"])
        for key in ("files", "revision", "synced_at"):
            self.assertEqual(bad[key], good[key])
        self.write("proposal.json", {"examples": []})
        self.assertIsNone(self.state()["error"])


    def test_project_name_persists_and_preserves_other_fields(self):
        project = {"schema_version": 4, "name": "First", "language": "zh",
                   "current_evaluation": "v2", "custom": {"values": [1, False, None, "研究"]}}
        self.write("project.json", project)
        proposal = self.write("proposal.json", {"examples": []})
        proposal_before = proposal.read_bytes()
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
        self.assertEqual(proposal.read_bytes(), proposal_before)
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
                             dict(body, path="project.json"), dict(body, schema_version=4),
                             b"[]", b"null", b"{broken", b'{"name":"a","name":"b"}',
                             b'{"name":NaN}', b'"\xff"'):
            with self.subTest(body=invalid_body):
                self.assertEqual(self.rename(invalid_body)[0], 400)
        self.assertEqual((self.root / "project.json").read_bytes(), before)
        self.assertFalse((self.root / ".workspace").exists())

    def test_project_name_stale_hash_checks_disk_and_recovers(self):
        body = self.rename_body()
        self.state()
        path = self.write("project.json", {"schema_version": 4, "name": "Agent edit", "language": "en"})
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
            with self.assertRaises(wb.RequestError) as error:
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
        outside = self.write("outside.json", {"schema_version": 4, "name": "Outside"}, root=self.base)
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
        self.write("project.json", {"schema_version": 4, "name": "First"})
        linked_root = self.base / "linked-project"
        linked_root.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(wb.RequestError) as error:
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
        outside = self.write("outside.json", {"schema_version": 4, "name": "Outside"}, root=self.base)
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


    def test_host_validation_for_reads_and_unsupported_methods(self):
        for host in ("evil.example", "127.0.0.1", "127.0.0.1:1", f"127.0.0.1:{self.port}.evil", f"localhost:{self.port}."):
            self.assertEqual(self.request(headers={"Host": host})[0], 403)
            self.assertEqual(self.request("DELETE", headers={"Host": host})[0], 403)
        self.assertEqual(self.raw_request(f"GET /api/state HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nHost: evil\r\n\r\n"), 403)
        self.assertEqual(self.request(headers={"Host": f"localhost:{self.port}"})[0], 200)

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
        linked = self.root / "proposal.json"
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


    def test_root_ancestor_symlink_blocks_read_and_name_write(self):
        parent = self.base / "alias"
        parent.symlink_to(self.base, target_is_directory=True)
        reader = wb.Reader(parent / "project")
        before = (self.root / "project.json").read_bytes()
        self.assertTrue(reader.snapshot()["error"])
        with self.assertRaises(wb.RequestError):
            wb.save_project_name(reader, self.rename_body())
        self.assertEqual((self.root / "project.json").read_bytes(), before)

    def test_malformed_resource_target_retains_last_snapshot(self):
        self.write("resources.json", {"items": [{"id": "data", "path": "data.txt", "monitor": {"kind": "file"}}]})
        good = self.state()
        self.write("resources.json", {"items": [{"id": "data", "path": ["not", "text"], "monitor": {"kind": "file"}}]})
        bad = self.state()
        self.assertEqual(bad["files"], good["files"])
        self.assertTrue(bad["error"])

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


    def rename_body(self, name="Renamed"):
        return {"name": name, "expected_sha256": hashlib.sha256((self.root / "project.json").read_bytes()).hexdigest()}

    def test_required_format_and_unknown_json_fields(self):
        for content in ({}, {"schema_version": True}, {"schema_version": 1}, [], '{"schema_version":4,"schema_version":4}'):
            with self.subTest(content=content):
                self.write("project.json", content)
                result = wb.Reader(self.root).snapshot()
                self.assertEqual(result["files"], {})
                self.assertTrue(result["error"])
        (self.root / "project.json").unlink()
        self.assertTrue(wb.Reader(self.root).snapshot()["error"])

    def test_known_arrays_and_strict_json(self):
        for path, content in (("proposal.json", {"examples": {}}), ("resources.json", {"items": "bad"}),
                              ("project.json", {"schema_version":4,"deliveries":{}}),
                              ("experiments/e/analysis.json", []),
                              ("experiments/e/analysis.json", '{"score":NaN}'),
                              ("experiments/e/analysis.json", '{"score":1e999}')):
            with self.subTest(path=path):
                original = (self.root / "project.json").read_bytes()
                written = self.write(path, content)
                self.assertTrue(self.state()["error"])
                written.unlink()
                (self.root / "project.json").write_bytes(original)

    def test_pending_intents_do_not_block_refresh(self):
        self.write("experiments/e/config.json", {"id":"e"})
        self.write("experiments/e/evals/a/config.json", {"id":"a","evaluation_version":"v1"})
        for state in ("pending", "running", "completed", "succeeded", "failed", "cancelled"):
            self.write("experiments/e/evals/a/status.json", {"state":state})
            self.write("proposal.json", {"summary":state,"examples":[]})
            value = self.state()
            self.assertIsNone(value["error"])
            self.assertEqual(value["files"]["proposal.json"]["content"]["summary"], state)
        good = self.state()
        for state in (None, [], 3, "invented"):
            self.write("experiments/e/evals/a/status.json", {"state":state})
            self.assertEqual(self.state()["files"], good["files"])
            self.assertTrue(self.state()["error"])

    def test_closed_allowlist_keeps_source_models_and_logs_private(self):
        for pattern in wb.PATTERNS:
            path = pattern.replace("*", "one")
            if path == "project.json":
                continue
            content = '{"sample_id":"a","input":"text"}\n' if path.endswith(".jsonl") else {}
            if path.endswith("/status.json"):
                content = {"state":"running"}
            self.write(path, content)
        for path in ("src/private.json", "experiments/one/model/weights.json", "experiments/one/run.log", "evaluation/one/private.jsonl"):
            self.write(path, "secret")
        value = self.state()
        self.assertIsNone(value["error"])
        self.assertEqual(set(value["files"]), {pattern.replace("*", "one") for pattern in wb.PATTERNS})
        self.write("comparison/outputs.jsonl", '{}\n[]\n')
        self.assertTrue(self.state()["error"])

    def test_read_bounds_retain_snapshot(self):
        good = self.state()
        for field in ("MAX_FILES", "MAX_ENTRIES", "MAX_TOTAL_BYTES", "MAX_FILE_BYTES"):
            with patch.object(wb, field, 0):
                value = self.state()
                self.assertEqual(value["files"], good["files"])
                self.assertTrue(value["error"])

    def test_project_name_requires_current_format_and_limits(self):
        for project in ({}, {"schema_version": True}, {"schema_version":4.0}, {"schema_version":1}, [], "null", '{"schema_version":', '{"schema_version":4,"schema_version":4}', '{"schema_version":4,"custom":1e999}'):
            path = self.write("project.json", project)
            before = path.read_bytes()
            self.assertEqual(self.rename(self.rename_body())[0],409)
            self.assertEqual(path.read_bytes(),before)
        for project in ({"schema_version":4,"name":"First"}, {"schema_version":4,"custom":"x"*128}):
            path=self.write("project.json",project)
            with patch.object(wb,"MAX_FILE_BYTES",64):
                self.assertEqual(self.rename(self.rename_body("研"*120))[0],409)
        self.assertEqual(list(self.root.glob(".pending-*")),[])

    def test_independent_projects(self):
        other=self.base/"second"
        other.mkdir()
        self.write("project.json",{"schema_version":4,"name":"Second"},root=other)
        server=self.start(other)
        value=self.request(port=server.server_address[1])[1]
        self.assertEqual(value["files"]["project.json"]["content"]["name"],"Second")
        self.assertEqual(self.rename(self.rename_body())[0],200)
        self.assertEqual(self.request(port=server.server_address[1])[1]["files"],value["files"])
        self.assertEqual(self.request("POST","/api/execute",{})[0],404)

    def test_resource_observations_are_saved_and_do_not_change_inventory(self):
        path=self.write("data/file.txt","sample")
        inventory={"items":[{"id":"file","title":"Data","type":"dataset","status":"unknown","path":"data/file.txt","monitor":{"kind":"file"}}]}
        saved=self.write("resources.json",inventory).read_bytes()
        first=self.state()
        self.assertEqual(first["observations"]["items"][0]["state"],"ready")
        runtime=self.root/".workspace/runtime/resources.json"
        self.assertEqual(json.loads(runtime.read_text()),first["observations"])
        path.write_text("modified content")
        self.server.reader.monitor.last_poll=float("-inf")
        second=self.state()
        self.assertEqual(second["observations"]["items"][0]["state"],"changed")
        path.unlink()
        self.server.reader.monitor.last_poll=float("-inf")
        self.assertEqual(self.state()["observations"]["items"][0]["state"],"missing")
        self.assertEqual((self.root/"resources.json").read_bytes(),saved)


if __name__ == "__main__":
    unittest.main()
