"""Public lookup helper checks against a local fake endpoint; no real network is used."""
import contextlib
import importlib.util
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/tunetune/skills/research-workspace/scripts/scout.py"


class Handler(BaseHTTPRequestHandler):
    routes = {}

    def log_message(self, *args):
        pass

    def do_GET(self):
        Handler.seen.append(self.path)
        status, body, headers = Handler.routes.get(self.path.split("?")[0], (404, b"{}", {}))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

    def do_PUT(self):
        length = int(self.headers.get("Content-Length") or 0)
        Handler.bodies.append(json.loads(self.rfile.read(length) or b"null"))
        self.do_GET()


def load():
    spec = importlib.util.spec_from_file_location("scout_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScoutTests(unittest.TestCase):
    def setUp(self):
        Handler.routes, Handler.seen, Handler.bodies = {}, [], []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        base = f"http://127.0.0.1:{self.server.server_port}"
        with patch.dict(os.environ, TUNETUNE_SCOUT_HF=base, TUNETUNE_SCOUT_MODELSCOPE=base, TUNETUNE_SCOUT_ARXIV=base, TUNETUNE_SCOUT_GITHUB=base):
            self.scout = load()
        # All requests target the local fixture, regardless of the host's proxy configuration.
        local_requests = patch.object(self.scout, "urlopen", build_opener(ProxyHandler({})).open)
        local_requests.start()
        self.addCleanup(local_requests.stop)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.scout.main(list(argv))
        return code, json.loads(out.getvalue() or err.getvalue())

    def test_models_normalize_license_params_and_unknowns(self):
        Handler.routes["/api/models"] = (200, [
            {"id": "org/small", "downloads": 900, "likes": 3, "tags": ["license:mit", "zh"], "pipeline_tag": "feature-extraction",
             "safetensors": {"total": 24000000}},
            {"id": "org/custom", "downloads": 50, "tags": ["license:other"]},
        ], {"ratelimit": '"api";r=498;t=100'})
        code, result = self.run_cli("models", "--query", "bge", "--lang", "zh", "--limit", "5")
        self.assertEqual(code, 0)
        first, second = result["results"]
        self.assertEqual(first["license"], {"id": "mit", "class": "permissive"})
        self.assertEqual(first["params"]["value"], 24000000)
        self.assertEqual(second["license"]["class"], "restricted_or_custom")
        self.assertIn("params", second["unknown"])
        self.assertIn("ratelimit", result["limits"])
        self.assertIn("search=bge", Handler.seen[0])
        code, result = self.run_cli("models", "--query", "bge", "--min-downloads", "100", "--license", "permissive")
        self.assertEqual([r["id"] for r in result["results"]], ["org/small"])

    def test_modelscope_search_inspect_and_fit(self):
        model = {"Path": "BAAI", "Name": "bge-small-zh-v1.5", "Downloads": 900, "Stars": 4, "License": "mit", "Language": ["zh"],
                 "IsAccessible": 1, "LastUpdatedTime": 1732194829, "Libraries": ["pytorch", "transformer"],
                 "Tasks": [{"Name": "feature-extraction"}], "ModelInfos": {"safetensor": {"model_size": 24000000}},
                 "Architectures": ["BertModel"], "ModelType": ["bert"]}
        other = {"Path": "org", "Name": "custom", "Downloads": 10, "License": "other", "IsAccessible": 0}
        Handler.routes["/api/v1/dolphin/models"] = (200, {"Code": 200, "Data": {"Model": {"Models": [model, other], "TotalCount": 2}}}, {})
        code, result = self.run_cli("models", "--hub", "modelscope", "--query", "bge", "--task", "feature-extraction", "--lang", "zh", "--sort", "likes")
        self.assertEqual(code, 0)
        first, second = result["results"]
        self.assertEqual((first["hub"], first["id"], first["task"], first["library"], first["params"]["value"]),
                         ("modelscope", "BAAI/bge-small-zh-v1.5", "feature-extraction", "transformer", 24000000))
        self.assertEqual(first["last_modified"], "2024-11-21T13:13:49Z")
        self.assertEqual((second["gated"], second["license"]["class"]), (True, "restricted_or_custom"))
        self.assertEqual(Handler.bodies[0]["Name"], "bge")
        self.assertEqual(Handler.bodies[0]["SortBy"], "StarsCount")
        self.assertEqual({c["category"]: c["values"] for c in Handler.bodies[0]["Criterion"]}, {"tasks": ["feature-extraction"], "languages": ["zh"]})
        code, result = self.run_cli("models", "--hub", "modelscope", "--license", "permissive", "--max-params", "1e9")
        self.assertEqual([r["id"] for r in result["results"]], ["BAAI/bge-small-zh-v1.5"])
        full = "02ed473a14d4a4b3b9a61399080c77ccb485820b"
        Handler.routes["/api/v1/models/BAAI/bge-small-zh-v1.5"] = (200, {"Code": 200, "Data": model}, {})
        Handler.routes["/api/v1/models/BAAI/bge-small-zh-v1.5/repo/files"] = (200, {"Code": 200, "Data": {
            "LatestCommitter": {"ShortId": full[:8]}, "Files": [
                {"Type": "tree", "Path": "1_Pooling", "Size": 0, "Revision": "8" * 40},
                {"Type": "blob", "Path": "model.safetensors", "Size": 95827648, "Sha256": "a" * 64, "Revision": full}]}}, {})
        code, result = self.run_cli("inspect", "BAAI/bge-small-zh-v1.5", "--hub", "modelscope")
        item = result["results"][0]
        self.assertEqual((code, item["revision"], item["total_file_bytes"]), (0, full, 95827648))
        self.assertEqual(item["files"], [{"path": "model.safetensors", "size": 95827648, "sha256": "a" * 64}])
        self.assertEqual(item["config"], {"architectures": ["BertModel"], "model_type": "bert"})
        Handler.routes["/api/v1/models/BAAI/bge-small-zh-v1.5/repo"] = (200, {"num_hidden_layers": 4, "num_attention_heads": 8, "hidden_size": 512}, {})
        code, result = self.run_cli("fit", "BAAI/bge-small-zh-v1.5", "--hub", "modelscope", "--memory-gb", "8")
        fit = result["results"][0]
        self.assertEqual((code, fit["params"], fit["params_source"], fit["verdict"]), (0, 24000000, "metadata", "fits"))
        self.assertGreater(fit["kv_cache_gb"], 0)
        Handler.routes["/api/v1/models/org/absent"] = (200, {"Code": 10990101004, "Message": "model not found 404"}, {})
        code, result = self.run_cli("inspect", "org/absent", "--hub", "modelscope")
        self.assertEqual((code, result["error"]["code"]), (1, "not_found"))
        code, result = self.run_cli("inspect", "org/data", "--hub", "modelscope", "--kind", "dataset")
        self.assertEqual(result["error"]["code"], "unsupported")

    def test_rate_limit_and_missing_are_distinct_errors(self):
        Handler.routes["/search/repositories"] = (403, {}, {"x-ratelimit-remaining": "0", "retry-after": "60"})
        code, result = self.run_cli("repos", "--query", "setfit")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "rate_limited")
        self.assertEqual(result["error"]["retry_after_s"], "60")
        code, result = self.run_cli("inspect", "org/absent")
        self.assertEqual(result["error"]["code"], "not_found")

    def test_http_error_responses_are_closed_for_every_error_kind(self):
        cases = [(429, {}, "rate_limited"), (403, {"x-ratelimit-remaining": "0"}, "rate_limited"),
                 (404, {}, "not_found"), (401, {}, "restricted"), (403, {}, "restricted"),
                 (500, {}, "http_error")]
        for status, headers, expected in cases:
            with self.subTest(status=status, headers=headers):
                body = io.BytesIO(b"{}")
                error = HTTPError("http://127.0.0.1/fixture", status, "fixture", headers, body)
                with patch.object(self.scout, "urlopen", side_effect=error):
                    code, result = self.run_cli("repos", "--query", "fixture")
                self.assertEqual((code, result["error"]["code"]), (1, expected))
                self.assertTrue(body.closed)

    def test_fit_uses_metadata_and_marks_training_estimates(self):
        Handler.routes["/api/models/org/llm"] = (200, {"id": "org/llm", "safetensors": {"total": 4_000_000_000}}, {})
        Handler.routes["/org/llm/resolve/main/config.json"] = (200, {"num_hidden_layers": 36, "num_attention_heads": 32,
                                                                     "num_key_value_heads": 8, "hidden_size": 2560}, {})
        code, result = self.run_cli("fit", "org/llm", "--memory-gb", "16", "--platform", "apple", "--precision", "q4")
        fit = result["results"][0]
        self.assertEqual((code, fit["verdict"], fit["unknown"]), (0, "fits", []))
        self.assertGreater(fit["kv_cache_gb"], 0)
        code, result = self.run_cli("fit", "org/llm", "--memory-gb", "16", "--platform", "apple", "--mode", "full-finetune")
        fit = result["results"][0]
        self.assertEqual(fit["verdict"], "no")
        self.assertIn("activations", fit["unknown"])
        code, result = self.run_cli("fit", "--params", "1e8", "--memory-gb", "8")
        self.assertEqual(result["results"][0]["kv_cache_gb"], None)
        self.assertIn("kv_cache_gb", result["results"][0]["unknown"])

    def test_arxiv_atom_is_parsed(self):
        feed = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2209.11055v1</id>
        <title>Efficient Few-Shot
          Learning</title><published>2022-09-22T00:00:00Z</published><summary>Short summary.</summary></entry></feed>"""
        Handler.routes["/api/query"] = (200, feed, {})
        code, result = self.run_cli("papers", "--query", "setfit")
        self.assertEqual(result["results"][0]["title"], "Efficient Few-Shot Learning")
        self.assertEqual(result["results"][0]["id"], "2209.11055v1")


if __name__ == "__main__":
    unittest.main()
