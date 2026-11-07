"""Windows reaches TuneTune only through WSL2: native runs and Windows-drive studies are refused."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/tunetune/skills/research-workspace/scripts"

spec = importlib.util.spec_from_file_location("windows_init", SCRIPTS / "init.py")
installer = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode, previous = True, sys.dont_write_bytecode
try:
    spec.loader.exec_module(installer)
finally:
    sys.dont_write_bytecode = previous

WSL = "5.15.167.4-microsoft-standard-WSL2\n"
MOUNTS = """\
/dev/sdc / ext4 rw,relatime 0 0
C:\\134 /mnt/c 9p rw,noatime,aname=drvfs;path=C:\\;uid=1000 0 0
D:\\134 /mnt/d drvfs rw,noatime 0 0
/dev/sdd /mnt/wsl/disk ext4 rw 0 0
E:\\134 /mnt/my\\040drive 9p rw,aname=drvfs 0 0
"""


class NativeWindowsTests(unittest.TestCase):
    def test_every_entry_point_refuses_native_windows_with_wsl_guidance(self):
        for name in ("init.py", "records.py", "workspace.py", "resources.py", "run.py"):
            code = ("import runpy, sys; sys.platform = 'win32'; sys.path.insert(0, sys.argv[1]); "
                    "runpy.run_path(sys.argv[2], run_name='__main__')")
            result = subprocess.run([sys.executable, "-B", "-c", code, str(SCRIPTS), str(SCRIPTS / name)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, name)
            self.assertIn("inside WSL2", result.stderr, name)
            self.assertNotIn("Traceback", result.stderr, name)


class WindowsDriveTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.base)
        self.mounts, self.release = self.base / "mounts", self.base / "osrelease"
        self.mounts.write_text(MOUNTS)
        self.release.write_text(WSL)

    def drive(self, project):
        return installer.windows_drive(project, self.mounts, self.release)

    def test_windows_drives_inside_wsl_are_detected(self):
        self.assertEqual(self.drive("/mnt/c/Users/me/study"), "/mnt/c")
        self.assertEqual(self.drive("/mnt/c"), "/mnt/c")
        self.assertEqual(self.drive("/mnt/d/study"), "/mnt/d")
        self.assertEqual(self.drive("/mnt/my drive/study"), "/mnt/my drive")

    def test_linux_filesystems_inside_wsl_are_accepted(self):
        self.assertIsNone(self.drive("/home/me/tunetune/cats"))
        self.assertIsNone(self.drive("/mnt/wsl/disk/study"))
        self.assertIsNone(self.drive("/mnt/cc/study"))

    def test_shares_outside_wsl_are_left_alone(self):
        self.release.write_text("6.8.0-45-generic\n")
        self.assertIsNone(self.drive("/mnt/c/study"))
        self.assertIsNone(installer.windows_drive("/mnt/c/study", self.mounts, self.base / "missing"))

    def test_initialization_on_a_windows_drive_writes_nothing(self):
        project = self.base / "study"
        with patch.object(installer, "windows_drive", return_value="/mnt/c"):
            with self.assertRaisesRegex(ValueError, "Linux home directory"):
                installer.install(project)
        self.assertFalse(project.exists())


if __name__ == "__main__":
    unittest.main()
