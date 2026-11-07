"""Bounded, read-only resource probes for the local panel."""
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import threading
import time

INTERVAL = 5.0


def now():
    return datetime.now(timezone.utc).isoformat()


def size_label(value):
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or suffix == "TB":
            return f"{value:.1f} {suffix}" if suffix != "B" else f"{int(value)} B"
        value /= 1024


def segments(value):
    if not isinstance(value, str) or not value or any(c in value for c in "\\:\x00"):
        raise ValueError("Unsafe resource path")
    result = value.split("/")
    if any(part in ("", ".", "..") for part in result):
        raise ValueError("Unsafe resource path")
    return result


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=2, check=True,
                            stdin=subprocess.DEVNULL, shell=False)
    return result.stdout


def memory_probe():
    if sys.platform == "darwin":
        total = int(command(["/usr/sbin/sysctl", "-n", "hw.memsize"]).strip())
        output = command(["/usr/bin/vm_stat"])
        page_size = int(re.search(r"page size of (\d+) bytes", output).group(1))
        pages = dict(re.findall(r"^([^:]+):\s+(\d+)\.", output, re.MULTILINE))
        available = sum(int(pages[name]) for name in ("Pages free", "Pages inactive", "Pages speculative")) * page_size
    elif sys.platform.startswith("linux"):
        values = dict(re.findall(r"^(\w+):\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.MULTILINE))
        total, available = int(values["MemTotal"]) * 1024, int(values["MemAvailable"]) * 1024
    else:
        raise ValueError("Memory probe unavailable")
    if not 0 <= available <= total or total <= 0:
        raise ValueError("Invalid memory observation")
    return {"state": "ready", "detail": "系统内存（已用 / 总量）", "size": f"{size_label(total - available)} / {size_label(total)}"}


def gpu_probe():
    # WSL2 exposes the Windows NVIDIA driver's tool under /usr/lib/wsl/lib.
    binary = next((path for path in ("/usr/bin/nvidia-smi", "/usr/local/bin/nvidia-smi", "/opt/nvidia/bin/nvidia-smi",
                                       "/usr/lib/wsl/lib/nvidia-smi") if os.path.isfile(path)), None)
    if binary is None:
        raise ValueError("NVIDIA probe unavailable")
    output = command([binary, "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"])
    devices = {}
    for row in csv.reader(output.splitlines()):
        index, name, total, used, utilization = (value.strip() for value in row)
        total, used, utilization = float(total), float(used), float(utilization)
        if not all(math.isfinite(value) for value in (total, used, utilization)) or not (0 <= used <= total and total > 0 and 0 <= utilization <= 100):
            raise ValueError("Invalid GPU observation")
        devices[int(index)] = {"state": "busy" if utilization > 0 else "ready", "detail": f"{name} · 利用率 {utilization:g}%",
                               "size": f"显存 {used / 1024:.1f} / {total / 1024:.1f} GB"}
    return devices


class ResourceMonitor:
    def __init__(self, tree):
        self.tree = tree
        self.lock = threading.Lock()
        self.last_poll = float("-inf")
        self.inventory = None
        self.baselines = {}
        self.report = {"checked_at": now(), "items": []}

    def file_probe(self, item):
        path = item.get("path")
        if path:
            components = segments(path)
            with self.tree.directory(components[:-1]) as parent:
                info = os.stat(components[-1], dir_fd=parent, follow_symlinks=False)
            identity = path
        else:
            location = item.get("location")
            if not isinstance(location, str) or not location.startswith("/"):
                raise ValueError("No local path")
            components = segments(location[1:])
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            try:
                for part in components[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                info = os.stat(components[-1], dir_fd=fd, follow_symlinks=False)
            finally:
                os.close(fd)
            identity = location
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError("Resource is not an ordinary file or directory")
        fingerprint = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        key = (item["id"], identity)
        baseline = self.baselines.setdefault(key, fingerprint)
        result = {"state": "ready" if fingerprint == baseline else "changed",
                  "detail": "本地目录（仅观察目录本身）" if stat.S_ISDIR(info.st_mode) else "本地文件",
                  "modified_at": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()}
        if stat.S_ISREG(info.st_mode):
            result["size"] = size_label(info.st_size)
        return result

    def snapshot(self, resources):
        with self.lock:
            inventory = json.dumps(resources, sort_keys=True, ensure_ascii=False)
            if inventory == self.inventory and time.monotonic() - self.last_poll < INTERVAL:
                return json.loads(json.dumps(self.report))
            items, probes, active = [], {}, set()
            for index, item in enumerate(resources.get("items", [])):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                monitor = item.get("monitor", {})
                kind = monitor.get("kind") if isinstance(monitor, dict) else None
                if not kind:
                    continue
                if index >= 256:
                    items.append({"id": item["id"], "state": "unknown", "detail": "本轮观测数量已达上限"})
                    continue
                observed = {"id": item["id"], "state": "unknown"}
                try:
                    if any(key in item and not isinstance(item[key], str) for key in ("path", "location")):
                        raise ValueError("Invalid resource target")
                    active.add((item["id"], item.get("path") or item.get("location")))
                    if kind == "file":
                        observed.update(self.file_probe(item))
                    elif kind == "python":
                        target = item.get("location")
                        if "path" in item:
                            target = str(self.tree.root.joinpath(*segments(item["path"])))
                        if target and os.path.abspath(target) != os.path.abspath(sys.executable):
                            raise ValueError("Different Python environment")
                        observed.update(state="ready", detail=f"Python {platform.python_version()} · 面板运行环境")
                    elif kind in ("memory", "nvidia_gpu"):
                        if kind not in probes:
                            try:
                                probes[kind] = memory_probe() if kind == "memory" else gpu_probe()
                            except (OSError, ValueError, KeyError, AttributeError, subprocess.SubprocessError):
                                probes[kind] = None
                        probe = probes[kind]
                        if probe is None:
                            raise ValueError("Probe unavailable")
                        if kind == "nvidia_gpu":
                            index = monitor.get("index", 0)
                            if type(index) is not int or index < 0:
                                raise ValueError("Invalid GPU index")
                            probe = probe[index]
                        observed.update(probe)
                    else:
                        raise ValueError("Unsupported probe")
                except FileNotFoundError:
                    observed.update(state="missing", detail="本地路径不存在")
                except (OSError, ValueError, KeyError, AttributeError, TypeError, subprocess.SubprocessError):
                    observed.update(state="unknown", detail="当前环境无法检测此资源")
                items.append(observed)
            report = {"checked_at": now(), "items": items}
            try:
                self.tree.publish(".workspace/runtime/resources.json", report, internal=True, replace=True)
            except (OSError, ValueError):
                report = {"checked_at": now(), "items": [{"id": item["id"], "state": "unknown", "detail": "无法保存资源观测"} for item in items]}
            self.report, self.inventory, self.last_poll = report, inventory, time.monotonic()
            self.baselines = {key: value for key, value in self.baselines.items() if key in active}
            return json.loads(json.dumps(report))
