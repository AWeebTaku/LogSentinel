"""E6: Spark Structured Streaming versus the Python consumer engine, same model, same events, same rate, same pinning.

    python -m logsentinel.experiments.e6 run --reps 5       # resumable, results/perf/e6/<engine>_<rate>k.rep<k>.json
    python -m logsentinel.experiments.e6 report             # tables.md + figure in results/perf/e6

Both arms are measured identically: alert latency = Kafka timestamp of the alert message minus the send time of the line
that triggered it (incremental alerts only: an age-check alert has no meaningful trigger line in Spark); throughput from the
engine's own consumption window; CPU and peak memory from the whole process tree (Spark = JVM + Python workers); startup =
process start to first micro-batch or first partition assignment. Both engines run on cores 2-3, broker on core 0, producer on 1.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from confluent_kafka import Consumer

from ..common.config import ROOT
from ..common.env import capture_env
from ..stream.admin import ensure_topics
from ..stream.producer import replay_segments
from ..stream.ready import wait_ready
from .harness import (
    BOOTSTRAP,
    COLD_BROKER_S,
    WORKER_CPUS,
    Ctx,
    Pinned,
    RunConfig,
    _spawn_worker,
    broker_pid,
    proc_cpu_seconds,
    proc_uptime_seconds,
)

OUT = ROOT / "results" / "perf" / "e6"
RATES = {"python": [1_000, 3_000, 5_000, 10_000, 20_000, 40_000, 50_000], "spark": [1_000, 2_000, 3_000, 4_000, 5_000]}
ENGINES = {"python": [], "spark": [], "spark-p1": ["--shuffle-partitions", "1"], "spark-p4": ["--shuffle-partitions", "4"],
           "spark-mo10k": ["--max-offsets-per-trigger", "10000"]}          # spark-* tuning variants, run at TUNE_RATE only
TUNE_RATE, TUNE_REPS = 3_000, 3
SEC = 15
DRAIN_TOLERANCE_S = {"python": 1.0, "spark": 10.0}     # Spark is micro-batch: one or two batches (about 4 s each here) of drain is normal


def descendants(root: int) -> set[int]:
    kids: dict[int, list[int]] = {}
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                ppid = int((d / "stat").read_text().rsplit(")", 1)[1].split()[1])
                kids.setdefault(ppid, []).append(int(d.name))
            except (OSError, IndexError, ValueError):
                continue
    out, todo = {root}, [root]
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in out:
                out.add(c)
                todo.append(c)
    return out


class TreeMonitor(threading.Thread):
    """CPU seconds and peak resident memory of a process and all its descendants (sampled every 0.5 s)."""

    def __init__(self, root: int):
        super().__init__(daemon=True)
        self.root, self.cpu, self.base, self.peak_rss_kb, self._halt = root, {}, {}, 0, threading.Event()
        self.hz = os.sysconf("SC_CLK_TCK")

    def run(self):
        first = True
        while not self._halt.wait(0.5):
            rss = 0
            for pid in descendants(self.root):
                try:
                    f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                    now = (int(f[11]) + int(f[12])) / self.hz
                    # CPU since monitoring began, NOT since the process started: start-up cost (JVM, model load) is reported
                    # separately. Processes already alive at the first sample count from then; later ones from zero.
                    self.base.setdefault(pid, now if first else 0.0)
                    self.cpu[pid] = max(self.cpu.get(pid, 0.0), now - self.base[pid])
                    rss += next(int(x.split()[1]) for x in Path(f"/proc/{pid}/status").read_text().splitlines() if x.startswith("VmRSS"))
                except (OSError, IndexError, ValueError, StopIteration):
                    continue
            first = False
            self.peak_rss_kb = max(self.peak_rss_kb, rss)

    def close(self) -> tuple[float, float]:
        self._halt.set()
        self.join(timeout=3)
        return sum(self.cpu.values()), self.peak_rss_kb / 1024


def read_alerts(group: str, idle_polls: int = 8) -> list[dict]:
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "auto.offset.reset": "earliest", "enable.auto.commit": False})
    c.subscribe(["alerts-critical"])
    out, idle = [], 0
    while idle < idle_polls:
        m = c.poll(0.5)
        if m is None or m.error():
            idle += 1
            continue
        idle = 0
        d = json.loads(m.value())
        d["_ts_ms"] = m.timestamp()[1]
        out.append(d)
    c.close()
    return out


def analyse_alerts(alerts: list[dict], label_of: dict, sessions_in_replay: set[str]) -> dict:
    live = [a for a in alerts if a["kind"] in ("incremental", "deadline")]
    inc = [(a["_ts_ms"] * 1e6 - a["t_trigger_send_ns"]) / 1e6 for a in alerts if a["kind"] == "incremental"]
    keys = {a["id"] for a in live}
    tp = sum(1 for k in keys if label_of.get(k) == 1)
    lat = {f"p{q}": (float(np.percentile(inc, q)) if inc else None) for q in (50, 95, 99)}
    return {"alerts": len(live), "incremental": len(inc), "deadline": len(live) - len(inc), "alerted_sessions": len(keys),
            "true_anomalies_alerted": tp, "false_alarms": len(keys) - tp, "incremental_latency_ms": {**lat, "n": len(inc)},
            "sessions_in_replay": len(sessions_in_replay)}


def parse_iso(ts: str) -> float:
    return datetime.fromisoformat(ts).timestamp()


def run_engine(engine: str, rate: int, ctx: Ctx, out_dir: Path, run_id: str, seconds: int = SEC, pin: bool = True) -> dict:
    n = int(rate * seconds)
    events = ctx.events(n)
    replay_keys = {k.decode() for k, _ in events}
    label_of = dict(zip(ctx.cf.ids, ctx.cf.labels.tolist(), strict=True))
    run_dir = out_dir / "work" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ensure_topics(BOOTSTRAP, 6, recreate=True)
    t_spawn = time.time()
    if engine == "python":
        cfg = RunConfig(plan=[[seconds, rate]], pin=pin)
        proc = _spawn_worker(cfg, ctx.bundle, 0, run_id, run_dir)
        wait_ready(run_dir, 1, 6, [proc])
    else:
        ready = run_dir / "ready"
        ready.unlink(missing_ok=True)
        cmd = [sys.executable, "-m", "logsentinel.stream.spark_engine", "--bundle", ctx.bundle, "--run-dir", str(run_dir),
               "--run-id", run_id, "--ready-file", str(ready), "--expected-rows", str(len(events) + 6), "--timeout-s", "400", *ENGINES[engine]]
        proc = subprocess.Popen((["taskset", "-c", WORKER_CPUS] if pin else []) + cmd, stdout=open(run_dir / "log", "w"),  # noqa: SIM115
                                stderr=subprocess.STDOUT, cwd=ROOT)
        while not ready.exists():
            if proc.poll() is not None or time.time() - t_spawn > 240:
                raise RuntimeError(f"spark engine did not start; see {run_dir / 'log'}")
            time.sleep(0.3)
        time.sleep(1.0)
    startup_s = time.time() - t_spawn
    mon = TreeMonitor(proc.pid)
    mon.start()
    bpid = broker_pid()
    uptime, cpu0 = proc_uptime_seconds(bpid), proc_cpu_seconds(bpid)
    try:
        with Pinned(pin):
            prod = replay_segments(events, BOOTSTRAP, [(len(events), float(rate))], 6)
        proc.wait(timeout=600)
    finally:
        if proc.poll() is None:
            proc.kill()
        cpu_s, rss_mb = mon.close()
    broker_cpu = proc_cpu_seconds(bpid) - cpu0
    time.sleep(1.0)
    if engine == "python":
        st = json.loads((run_dir / "worker-0.stats.json").read_text())
        consumed, first_s, last_s = st["events"], st["first_recv_ns"] / 1e9, st["last_recv_ns"] / 1e9
        batch, capacity = None, None
    else:
        st = json.loads((run_dir / "spark.stats.json").read_text())
        busy = [b for b in st["batches"] if b["rows"] > 0]
        consumed = st["rows"] - 6                                            # minus the 6 end-of-stream markers
        first_s = parse_iso(busy[0]["ts"])
        last_s = parse_iso(busy[-1]["ts"]) + busy[-1]["dur_ms"] / 1000
        capacity = consumed / (sum(b["dur_ms"] for b in busy) / 1000)      # events per second of non-empty batch time
        durs = [b["dur_ms"] for b in st["batches"]]
        batch = {"n": len(st["batches"]), "median_ms": float(np.median(durs)), "max_ms": float(max(durs)),
                 "empty_batch_median_ms": float(np.median([b["dur_ms"] for b in st["batches"] if b["rows"] == 0] or [0]))}
    span = max(last_s - first_s, 1e-9)
    alerts = read_alerts(f"{run_id}-alerts")
    return {
        "engine": engine, "rate": rate, "run_id": run_id, "env": capture_env(), "cold_start": uptime < COLD_BROKER_S,
        "complete": consumed == prod["events"], "events_sent": prod["events"], "events_consumed": consumed,
        "consumer": {"span_s": span, "rate_eps": consumed / span, "drain_s": last_s - prod["last_send_ns"] / 1e9},
        "processing_capacity_eps": capacity, "startup_s": startup_s, "engine_cpu_seconds": cpu_s, "engine_cpu_cores": cpu_s / max(span, 1.0),
        "engine_peak_rss_mb": rss_mb, "broker_cpu_seconds": broker_cpu, "spark_batches": batch,
        **analyse_alerts(alerts, label_of, replay_keys),
    }


def path(engine: str, rate: int, rep: int) -> Path:
    return OUT / f"{engine}_{rate // 1000}k.rep{rep}.json"


def cmd_run(reps: int, force: bool, only: list[str]) -> None:
    ctx = Ctx()
    todo = []
    for rep in range(reps):
        for r in sorted({x for v in RATES.values() for x in v}):
            for e in ("python", "spark"):
                if e in only and r in RATES[e]:
                    todo.append((rep, e, r))
    for rep in range(min(TUNE_REPS, reps)):
        todo += [(rep, e, TUNE_RATE) for e in ENGINES if e.startswith("spark-") and e in only]
    cells = [(rep, e, r) for rep, e, r in todo if force or not path(e, r, rep).exists()]
    print(f"{len(cells)} runs to do", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    print("warm-up (discarded): one short run per engine", flush=True)
    for e in ("python", "spark"):
        run_engine(e, 3_000, ctx, OUT / "warmup", f"warmup-{e}", seconds=8)
    t0 = time.time()
    for i, (rep, e, r) in enumerate(cells, 1):
        res = run_engine(e, r, ctx, OUT, f"{e}_{r // 1000}k-r{rep}")
        res["rep"] = rep
        path(e, r, rep).write_text(json.dumps(res))
        L = res["incremental_latency_ms"]
        eta = (time.time() - t0) / i * (len(cells) - i) / 60
        print(f"[{i}/{len(cells)}] {e:11s} {r // 1000:>2d}k rep{rep}: consumed {res['consumer']['rate_eps']:>8,.0f} ev/s, drain {res['consumer']['drain_s']:5.1f}s, "
              f"inc p50/p99 {L['p50'] or 0:6.0f}/{L['p99'] or 0:6.0f} ms, alerts {res['alerts']} (false {res['false_alarms']}), "
              f"cpu {res['engine_cpu_cores']:.2f} cores, rss {res['engine_peak_rss_mb']:.0f} MB, complete={res['complete']}  (~{eta:.0f} min left)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "report"])
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--only", nargs="*", default=list(ENGINES), choices=list(ENGINES))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.action == "run":
        if os.getloadavg()[0] > 1.5:
            print(f"WARNING: load average {os.getloadavg()[0]:.1f}; close other applications", file=sys.stderr)
        cmd_run(a.reps, a.force, a.only)
    else:
        from .e6_report import main as report
        report()


if __name__ == "__main__":
    main()
