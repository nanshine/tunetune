"""Resource observations inspect metadata, never resource contents or supplied commands."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "plugins/tunetune/skills/research-workspace/scripts/workspace.py"
spec = importlib.util.spec_from_file_location("monitor_test_workspace", SOURCE)
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)
monitor = workspace.monitor_module


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.tree = workspace.SafeTree(self.root)
        self.watcher = monitor.ResourceMonitor(self.tree)
        self.resource = {"id": "data", "title": "Data", "type": "dataset", "status": "unknown", "path": "input.txt", "monitor": {"kind": "file"}}
        (self.root / "input.txt").write_text("private contents")

    def observe(self, items=None):
        self.watcher.last_poll = float("-inf")
        return self.watcher.snapshot({"items": items or [self.resource]})

    def test_metadata_only_and_persistent_atomic_report(self):
        with patch.object(self.tree, "read", side_effect=AssertionError("Must not read resource contents")):
            report = self.observe()
        self.assertEqual(report["items"][0]["state"], "ready")
        self.assertEqual(report["items"][0]["size"], "16 B")
        self.assertNotIn("private contents", json.dumps(report))
        self.assertEqual(json.loads((self.root / ".workspace/runtime/resources.json").read_text()), report)
        self.assertEqual(list((self.root / ".workspace/runtime").glob(".pending-*")), [])

    def test_change_missing_and_recreation(self):
        self.observe()
        path = self.root / "input.txt"
        path.write_text("changed length")
        self.assertEqual(self.observe()["items"][0]["state"], "changed")
        self.assertEqual(self.observe()["items"][0]["state"], "changed")
        path.unlink()
        self.assertEqual(self.observe()["items"][0]["state"], "missing")
        path.write_text("new")
        self.assertEqual(self.observe()["items"][0]["state"], "changed")

    def test_polling_is_throttled_and_changed_inventory_refreshes(self):
        inventory = {"items": [self.resource]}
        first = self.watcher.snapshot(inventory)
        with patch.object(self.watcher, "file_probe", side_effect=AssertionError("Unnecessary probe")):
            self.assertEqual(self.watcher.snapshot(inventory), first)
        other = dict(self.resource, path="absent")
        self.assertEqual(self.watcher.snapshot({"items": [other]})["items"][0]["state"], "missing")
        first["items"].clear()
        self.assertTrue(self.watcher.report["items"])

    def test_unknown_and_supplied_command_never_execute(self):
        for kind in ("shell", "https://invalid.example", "python; touch owned"):
            resource = dict(self.resource, monitor={"kind": kind, "command": ["touch", "owned"]})
            with patch.object(monitor, "command", side_effect=AssertionError("Record-driven command")):
                self.assertEqual(self.observe([resource])["items"][0]["state"], "unknown")
        self.assertFalse((self.root / "owned").exists())

    def test_unsafe_relative_paths_and_symlinks_are_unknown(self):
        for path in ("../input.txt", "/etc/passwd", "x/../input.txt", "x\\y", "x\x00y"):
            self.assertEqual(self.observe([dict(self.resource, path=path)])["items"][0]["state"], "unknown")
        (self.root / "link").symlink_to(self.root / "input.txt")
        self.assertEqual(self.observe([dict(self.resource, path="link")])["items"][0]["state"], "unknown")
        (self.root / "linked-dir").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.observe([dict(self.resource, path="linked-dir/input.txt")])["items"][0]["state"], "unknown")
        os.mkfifo(self.root / "pipe")
        self.assertEqual(self.observe([dict(self.resource, path="pipe")])["items"][0]["state"], "unknown")

    def test_explicit_external_file_and_directory_metadata(self):
        external = dict(self.resource, location=str(self.root / "input.txt"))
        del external["path"]
        self.assertEqual(self.observe([external])["items"][0]["state"], "ready")
        (self.root / "folder").mkdir()
        value = self.observe([dict(self.resource, path="folder")])["items"][0]
        self.assertEqual(value["state"], "ready")
        self.assertNotIn("size", value)
        self.assertIn("目录本身", value["detail"])

    def test_python_probe_only_identifies_the_service_environment(self):
        resource = {"id": "python", "monitor": {"kind": "python"}, "location": sys.executable}
        self.assertEqual(self.observe([resource])["items"][0]["state"], "ready")
        self.assertEqual(self.observe([dict(resource, location="/another/python")])["items"][0]["state"], "unknown")
        self.assertEqual(self.observe([{"id": "python", "path": "missing-venv/bin/python", "monitor": {"kind": "python"}}])["items"][0]["state"], "unknown")

    def test_malformed_paths_do_not_escape_probe_error_handling(self):
        for path in ([], {}, True, 5):
            self.assertEqual(self.observe([dict(self.resource, path=path)])["items"][0]["state"], "unknown")

    def test_shared_hardware_probe_cached_per_refresh(self):
        items = [{"id": str(i), "monitor": {"kind": "memory"}} for i in range(3)]
        with patch.object(monitor, "memory_probe", return_value={"state": "ready", "size": "4 / 8 GB"}) as probe:
            values = self.observe(items)["items"]
            self.assertEqual(len(values), 3)
            probe.assert_called_once()
        with patch.object(monitor, "memory_probe", side_effect=subprocess.TimeoutExpired("probe", 2)):
            self.assertTrue(all(item["state"] == "unknown" for item in self.observe(items)["items"]))

    def test_gpu_parser_reports_real_memory_and_busy_state(self):
        with patch.object(monitor.os.path, "isfile", return_value=True), patch.object(monitor, "command", return_value="0, NVIDIA Test, 24576, 4096, 25\n") as probe:
            result = monitor.gpu_probe()[0]
            self.assertEqual(result["state"], "busy")
            self.assertEqual(result["size"], "显存 4.0 / 24.0 GB")
            self.assertEqual(probe.call_args.args[0][0], "/usr/bin/nvidia-smi")
        wsl = "/usr/lib/wsl/lib/nvidia-smi"
        with patch.object(monitor.os.path, "isfile", side_effect=lambda path: path == wsl), \
                patch.object(monitor, "command", return_value="0, NVIDIA Test, 24576, 4096, 25\n") as probe:
            monitor.gpu_probe()
            self.assertEqual(probe.call_args.args[0][0], wsl)
        for output in ("bad", "0, Test, nan, 4, 2", "0, Test, 8, 9, 2"):
            with patch.object(monitor.os.path, "isfile", return_value=True), patch.object(monitor, "command", return_value=output):
                with self.assertRaises(ValueError):
                    monitor.gpu_probe()

    def test_missing_gpu_is_unknown_not_fake_zero(self):
        item = {"id": "gpu", "monitor": {"kind": "nvidia_gpu", "index": 0}}
        with patch.object(monitor.os.path, "isfile", return_value=False):
            result = self.observe([item])["items"][0]
        self.assertEqual(result["state"], "unknown")
        self.assertNotIn("size", result)

    def test_mac_memory_and_linux_available_memory(self):
        output = "Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 100.\nPages inactive: 50.\nPages speculative: 10.\n"
        with patch.object(monitor.sys, "platform", "darwin"), patch.object(monitor, "command", side_effect=["1048576", output]):
            self.assertEqual(monitor.memory_probe()["state"], "ready")
        with patch.object(monitor.sys, "platform", "linux"), patch.object(monitor.Path, "read_text", return_value="MemTotal: 8192 kB\nMemAvailable: 4096 kB\n"):
            self.assertEqual(monitor.memory_probe()["size"], "4.0 MB / 8.0 MB")

    def test_publication_failure_and_runtime_symlink_do_not_leak(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / ".workspace").symlink_to(outside, target_is_directory=True)
        report = self.observe()
        self.assertEqual(report["items"][0]["state"], "unknown")
        self.assertEqual(list(outside.iterdir()), [])

    def test_report_symlink_is_not_replaced(self):
        runtime = self.root / ".workspace/runtime"
        runtime.mkdir(parents=True)
        external = self.root / "unrelated"
        external.write_text("keep")
        (runtime / "resources.json").symlink_to(external)
        self.assertEqual(self.observe()["items"][0]["state"], "unknown")
        self.assertEqual(external.read_text(), "keep")
        self.assertTrue((runtime / "resources.json").is_symlink())


if __name__ == "__main__":
    unittest.main()
