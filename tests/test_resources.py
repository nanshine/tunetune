"""Resource preparation uses local HTTP fixtures and mocked repository responses only."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/tunetune/skills/research-workspace/scripts/resources.py"
SPEC = importlib.util.spec_from_file_location("resources_under_test", SCRIPT)
resources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resources)
CONTENT = b"bounded fixture data\n"
COMMIT = "a" * 40


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/data?signature=fixture")
            self.end_headers()
            return
        self.send_response(200)
        if self.path != "/stream":
            self.send_header("Content-Length", str(len(CONTENT)))
        self.end_headers()
        self.wfile.write(CONTENT)

    def log_message(self, *args):
        pass


class ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.json").write_text('{"schema_version":4}')

    def prepare(self, destination="resources/file.bin", **options):
        source = options.pop("source", self.url + "/data")
        return resources.prepare(self.root, source, destination, **options)

    def test_check_is_read_only_and_does_not_claim_size(self):
        before = list(self.root.rglob("*"))
        result = self.prepare()
        self.assertEqual(list(self.root.rglob("*")), before)
        self.assertIsNone(result["expected_bytes"])
        self.assertEqual(result["state"], "planned")

    def test_http_publishes_exclusively_and_verifies_hash(self):
        result = self.prepare(fetch=True, sha256=hashlib.sha256(CONTENT).hexdigest())
        self.assertEqual(result["actual_bytes"], len(CONTENT))
        self.assertEqual((self.root / "resources/file.bin").read_bytes(), CONTENT)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare(fetch=True)
        self.assertEqual(list(self.root.rglob(".resource-*")), [])

    def test_hash_mismatch_and_limits_leave_no_destination(self):
        for options in ({"sha256": "0" * 64}, {"max_bytes": 2},
                        {"source": self.url + "/stream", "max_bytes": 2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.prepare(fetch=True, **options)
            self.assertFalse((self.root / "resources/file.bin").exists())
            self.assertEqual(list(self.root.rglob(".resource-*")), [])

    def test_redirect_signed_query_is_allowed_without_source_credentials(self):
        self.prepare(source=self.url + "/redirect", fetch=True)
        self.assertEqual((self.root / "resources/file.bin").read_bytes(), CONTENT)

    def test_unsafe_sources_rejected(self):
        for source in ("http://example.com/file", "file:///etc/passwd", "https://u:p@example.com/a",
                       "https://example.com/a?token=secret", "https://example.com/a#part"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.prepare(source=source)

    def test_destination_traversal_symlinks_and_protected_paths_rejected(self):
        for name in ("../bad", "resources/../bad", "/tmp/bad", ".workspace/key", "project.json", "resources/.secret"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.prepare(destination=name)
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "resources").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.prepare(fetch=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_revisions_and_limits_must_be_explicit_valid_values(self):
        for options in ({"kind": "git"}, {"kind": "git", "revision": "main"},
                        {"kind": "model", "revision": "v1"}, {"max_bytes": 0}, {"timeout": float("nan")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.prepare(**options)

    def test_format_two_is_not_modified(self):
        project = self.root / "project.json"
        project.write_text('{"schema_version":2}')
        before = project.read_bytes()
        with self.assertRaisesRegex(ValueError, "format 4"):
            self.prepare(fetch=True)
        self.assertEqual(project.read_bytes(), before)
        self.assertFalse((self.root / "resources").exists())

    def test_model_downloads_fixed_revision_with_size_checks(self):
        def fake_download(url, target, budget, deadline, expected=None, internal=False):
            content = (json.dumps({"sha": COMMIT, "siblings": [{"rfilename": "weights.bin", "size": len(CONTENT)}]}).encode()
                       if internal else CONTENT)
            target.write_bytes(content)
            return len(content), hashlib.sha256(content).hexdigest()
        with patch.object(resources, "download", side_effect=fake_download):
            result = self.prepare(source="example/model", destination="resources/model", kind="model", revision=COMMIT, fetch=True)
        self.assertEqual(result["actual_bytes"], len(CONTENT))
        self.assertEqual((self.root / "resources/model/weights.bin").read_bytes(), CONTENT)
        self.assertEqual(list(self.root.rglob(".resource-*")), [])

    def test_git_rejects_links_before_publication(self):
        class Reply:
            stdout = b""
        def fake_run(command, **kwargs):
            result = Reply()
            if "rev-parse" in command:
                result.stdout = (COMMIT + "\n").encode()
            elif "ls-tree" in command:
                result.stdout = b"120000 blob " + b"b" * 40 + b" 4\tlink\0"
            return result
        with patch.object(resources.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "links"):
                self.prepare(source="https://example.com/repo.git", destination="resources/code", kind="git", revision=COMMIT, fetch=True)
        self.assertFalse((self.root / "resources/code").exists())

    def test_git_extracts_only_pinned_ordinary_blobs_without_checkout(self):
        commands = []
        class Reply:
            stdout = b""
        def fake_run(command, **kwargs):
            commands.append(command)
            result = Reply()
            if "rev-parse" in command:
                result.stdout = (COMMIT + "\n").encode()
            elif "ls-tree" in command:
                result.stdout = b"100644 blob " + b"b" * 40 + b" " + str(len(CONTENT)).encode() + b"\tmain.py\0"
            elif "cat-file" in command:
                result.stdout = CONTENT
            elif "init" in command:
                repository = next(x.split("=", 1)[1] for x in command if x.startswith("--git-dir="))
                Path(repository).mkdir()
            return result
        with patch.object(resources.subprocess, "run", side_effect=fake_run):
            self.prepare(source="https://example.com/repo.git", destination="resources/code", kind="git", revision=COMMIT, fetch=True)
        self.assertEqual((self.root / "resources/code/main.py").read_bytes(), CONTENT)
        self.assertFalse((self.root / "resources/code/.git").exists())
        self.assertFalse(any("checkout" in command for command in commands))
        self.assertTrue(all("core.hooksPath=" + resources.os.devnull in command for command in commands))

    def test_exclusive_directory_publish_never_replaces_empty_directory(self):
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "file").write_bytes(CONTENT)
        destination = self.root / "target"
        destination.mkdir()
        import os
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(FileExistsError):
                resources.publish_directory(stage, fd, "target")
        finally:
            os.close(fd)
        self.assertEqual(list(destination.iterdir()), [])
        self.assertTrue((stage / "file").exists())


if __name__ == "__main__":
    unittest.main()
