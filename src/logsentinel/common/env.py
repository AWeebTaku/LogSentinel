"""Environment capture, written next to every experiment's results (env.json)."""
import os
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .config import ROOT

_PKGS = ["numpy", "pandas", "scikit-learn", "pyyaml"]


def _git_hash() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def capture_env() -> dict:
    meminfo = Path("/proc/meminfo").read_text().splitlines()
    mem_kb = next((int(x.split()[1]) for x in meminfo if x.startswith("MemTotal")), 0)
    cpuinfo = Path("/proc/cpuinfo").read_text().splitlines()
    cpu = next((x.split(":")[1].strip() for x in cpuinfo if "model name" in x), "")
    pkgs = {}
    for p in _PKGS:
        try:
            pkgs[p] = version(p)
        except PackageNotFoundError:
            pass
    return {
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": cpu,
        "cpu_count": os.cpu_count(),
        "mem_gb": round(mem_kb / 1024 / 1024, 1),
        "packages": pkgs,
        "git": _git_hash(),
    }
