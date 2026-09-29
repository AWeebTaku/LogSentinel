"""System sampler for benchmark diagnosis: per-core CPU use, per-core frequency and the busiest other processes.

Runs as a thread pinned to the producer's core (so it does not steal time from the engine cores) and samples every
`interval` seconds. Everything comes from /proc and /sys, no extra tools. Used to explain latency excursions.
"""
import os
import threading
import time
from pathlib import Path

BENCH_HINTS = ("logsentinel", "kafka", "java")                   # our own processes; everything else is "other"


def parse_proc_stat(text: str) -> dict[int, tuple[int, int]]:
    """Per-core (busy, total) jiffies from /proc/stat."""
    out = {}
    for line in text.splitlines():
        if line.startswith("cpu") and line[3].isdigit():
            f = line.split()
            v = [int(x) for x in f[1:9]]                            # user nice system idle iowait irq softirq steal
            idle = v[3] + v[4]
            out[int(f[0][3:])] = (sum(v) - idle, sum(v))
    return out


def core_util(prev: dict, cur: dict) -> list[float]:
    """Busy fraction per core between two parse_proc_stat() snapshots."""
    out = []
    for c in sorted(cur):
        db, dt = cur[c][0] - prev[c][0], cur[c][1] - prev[c][1]
        out.append(db / dt if dt > 0 else 0.0)
    return out


def _proc_cpu() -> dict[int, tuple[str, int, int]]:
    """pid -> (comm, cpu jiffies, last core) for every process."""
    out = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            raw = (d / "stat").read_text()
            head, tail = raw.split(") ", 1)[0], raw.rsplit(") ", 1)[1].split()
            out[int(d.name)] = (head.split("(", 1)[1], int(tail[11]) + int(tail[12]), int(tail[36]))
        except (OSError, IndexError, ValueError):
            continue                                                # process vanished mid-scan
    return out


def _freqs() -> list[float]:
    out = []
    for c in range(os.cpu_count() or 1):
        try:
            out.append(int(Path(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_cur_freq").read_text()) / 1000.0)
        except OSError:
            out.append(0.0)
    return out


class SysSampler(threading.Thread):
    def __init__(self, interval: float = 0.5, pin_cpu: int | None = 1, top_n: int = 5):
        super().__init__(daemon=True)
        self.interval, self.pin_cpu, self.top_n = interval, pin_cpu, top_n
        self.samples: list[dict] = []
        self._halt = threading.Event()

    def run(self):
        if self.pin_cpu is not None:
            os.sched_setaffinity(0, {self.pin_cpu})                  # this thread only
        hz = os.sysconf("SC_CLK_TCK")
        prev_stat = parse_proc_stat(Path("/proc/stat").read_text())
        prev_proc, prev_t = _proc_cpu(), time.time()
        while not self._halt.wait(self.interval):
            now = time.time()
            cur_stat = parse_proc_stat(Path("/proc/stat").read_text())
            cur_proc = _proc_cpu()
            dt = now - prev_t
            top = []
            for pid, (comm, j, core) in cur_proc.items():
                if pid in prev_proc:
                    pct = 100.0 * (j - prev_proc[pid][1]) / hz / dt
                    if pct >= 1.0:
                        top.append({"pid": pid, "comm": comm, "cpu_pct": round(pct, 1), "core": core})
            top.sort(key=lambda x: -x["cpu_pct"])
            self.samples.append({"t": now, "core_util": [round(x, 3) for x in core_util(prev_stat, cur_stat)],
                                 "freq_mhz": _freqs(), "top": top[: self.top_n + 4]})
            prev_stat, prev_proc, prev_t = cur_stat, cur_proc, now

    def close(self) -> list[dict]:
        self._halt.set()
        self.join(timeout=3)
        return self.samples
