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


def load():
    spec = importlib.util.spec_from_file_location("scout_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScoutTests(unittest.TestCase):
    def setUp(self):
        Handler.routes, Handler.seen = {}, []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        base = f"http://127.0.0.1:{self.server.server_port}"
        with patch.dict(os.environ, TUNETUNE_SCOUT_HF=base, TUNETUNE_SCOUT_ARXIV=base, TUNETUNE_SCOUT_GITHUB=base):
            self.scout = load()

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

    def test_rate_limit_and_missing_are_distinct_errors(self):
        Handler.routes["/search/repositories"] = (403, {}, {"x-ratelimit-remaining": "0", "retry-after": "60"})
        code, result = self.run_cli("repos", "--query", "setfit")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "rate_limited")
        self.assertEqual(result["error"]["retry_after_s"], "60")
        code, result = self.run_cli("inspect", "org/absent")
        self.assertEqual(result["error"]["code"], "not_found")

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
