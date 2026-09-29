"""Benchmark harness: one configuration in, one fully measured streaming run out.

    run_once(RunConfig(...), Ctx(bundle), out_dir) -> dict      (also used by perf.py for E4, E5 and E7)

What one run does: recreate the topics, start a metrics collector, start engine workers (optionally pinned to
cores and optionally autoscaled by a lag rule), replay a rate plan, wait for the engines to drain, and return
throughput, backlog, CPU per component, and per-stage latency of the alerts. It never trusts a run blindly:
`complete` is False if the engines consumed a different number of events than were sent.

Core layout when `pin` is true on the 4-core dev machine: broker core 0, producer core 1, engine workers cores 2-3.
Latency stages come from the engine's own stamps (producer send, broker append time, consumer receive,
scoring duration, alert publish), all on one host clock; broker append time has 1 ms resolution.
"""
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from confluent_kafka import Consumer

from ..common.config import ROOT
from ..common.env import capture_env
from ..features.counts import load_or_build
from ..stream.admin import ensure_topics
from ..stream.producer import replay_segments
from ..stream.ready import wait_ready
from ..stream.wire import TOPIC_METRICS
from .stream_e2e import replay_events
from .sysmon import SysSampler

BOOTSTRAP = "127.0.0.1:9092"
KAFKA_PID_FILE = Path.home() / ".local/share/logsentinel/kafka.pid"
SESSION_STEPS = [2000, 8000, 20000, 40000, 80000, 130000, 172519]   # cached replay sizes (test sessions)
LINES_PER_SESSION = 16.6                                              # test split: 2,859,006 lines / 172,519 sessions
BROKER_CPUS, PRODUCER_CPUS, WORKER_CPUS = "0", {1}, "2,3"


@dataclass
class RunConfig:
    """`plan` is a list of [seconds, events_per_second] segments (rate None = burst all `events` at once)."""
    plan: list
    events: int = 0                      # burst only: how many events to send
    workers: int = 1
    partitions: int = 6
    batch: int = 2000                    # engine: max messages per consume() call
    compression: str = "none"
    linger_ms: int = 5
    min_lines: int = 10
    pin: bool = True
    autoscale: dict | None = None        # {"max_workers", "lag_threshold", "hold_s", "cooldown_s"}
    bundle: str = "models/hdfs-drain-pca-early"
    sysmon: bool = False                 # sample per-core CPU, frequency and competing processes (diagnosis)
    tag: str = ""

    def segment_events(self) -> list[tuple[int, float | None]]:
        out = []
        for sec, rate in self.plan:
            out.append((self.events, None) if rate is None else (int(sec * rate), float(rate)))
        return out

    def total_events(self) -> int:
        return sum(n for n, _ in self.segment_events())


# ---- pure helpers (unit-tested) ---------------------------------------------------------------------

STAGES = ("producer_to_broker", "broker_to_consumer", "engine_update", "scoring", "alert_emit", "total")


def stage_latencies(recs: list[dict]) -> dict[str, list[float]]:
    """Per-stage latency (ms) of live alerts. `producer_to_broker` includes the client's linger and batching;
    `engine_update` is the rest of the micro-batch's state updates before scoring. Sub-millisecond negative
    values (broker timestamps have 1 ms resolution) are clamped to 0."""
    out: dict[str, list[float]] = {s: [] for s in STAGES}
    for r in recs:
        if r.get("kind") == "deadline_eos" or not r.get("alerted") or r.get("t_trigger_broker_ms") is None:
            continue
        broker_ns = r["t_trigger_broker_ms"] * 1_000_000
        score = r["score_dur_ns"]
        out["producer_to_broker"].append(max(0.0, (broker_ns - r["t_trigger_send"]) / 1e6))
        out["broker_to_consumer"].append(max(0.0, (r["t_trigger_recv"] - broker_ns) / 1e6))
        out["engine_update"].append(max(0.0, (r["t_scored"] - r["t_trigger_recv"] - score) / 1e6))
        out["scoring"].append(score / 1e6)
        out["alert_emit"].append((r["t_alert"] - r["t_scored"]) / 1e6)
        out["total"].append((r["t_alert"] - r["t_trigger_send"]) / 1e6)
    return out


def pct_table(stages: dict[str, list[float]]) -> dict[str, dict]:
    return {k: {"n": len(v), **{f"p{q}": (float(np.percentile(v, q)) if v else None) for q in (50, 95, 99)}}
            for k, v in stages.items()}


def autoscale_decision(state: dict, lag: float, now_s: float, workers: int, cfg: dict) -> bool:
    """Reactive scale-out rule: add a worker when total lag has stayed above `lag_threshold` for `hold_s`
    seconds, at most `max_workers`, at most once per `cooldown_s`. `state` carries over_since / last_scale."""
    if lag <= cfg["lag_threshold"]:
        state["over_since"] = None
        return False
    state.setdefault("over_since", None)
    if state["over_since"] is None:
        state["over_since"] = now_s
    held = now_s - state["over_since"] >= cfg["hold_s"]
    cooled = now_s - state.get("last_scale", -1e9) >= cfg.get("cooldown_s", 10.0)
    if held and cooled and workers < cfg["max_workers"]:
        state["last_scale"] = now_s
        return True
    return False


def saturation(rows: list[dict], min_ratio: float = 0.97, max_drain_s: float = 1.0, max_p99_ms: float = 500.0):
    """Highest offered rate that keeps up, scanning upward and stopping at the FIRST rate that does not (so one lucky
    run at a high rate cannot inflate it). Keeping up = consumer rate >= 97% of offered, backlog gone within 1 s of
    the last send, event-to-alert p99 under 500 ms. rows: [{offered, achieved, drain_s, p99_ms}], one per rate."""
    best = None
    for r in sorted(rows, key=lambda r: r["offered"]):
        ok = (r["achieved"] >= min_ratio * r["offered"] and r["drain_s"] <= max_drain_s
              and (r["p99_ms"] is None or r["p99_ms"] <= max_p99_ms))
        if not ok:
            break
        best = r["offered"]
    return best


def proc_cpu_seconds(pid: int) -> float:
    """utime + stime of a whole process (all threads) from /proc."""
    raw = Path(f"/proc/{pid}/stat").read_text()
    f = raw.rsplit(")", 1)[1].split()
    return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")


COLD_BROKER_S = 45.0    # a broker younger than this at the start of a run is "cold": its first paced run is ~0.5 s slower


def proc_uptime_seconds(pid: int) -> float:
    """Seconds since process `pid` started, from /proc (process start ticks plus the system boot time)."""
    starttime = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
    btime = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime"))
    return time.time() - (btime + starttime / os.sysconf("SC_CLK_TCK"))


def series_per_second(rows: list[dict]) -> list[dict]:
    """Engine metrics messages -> one point per second, summed over workers (lag, rate, open sessions)."""
    by: dict[int, dict] = {}
    for m in rows:
        t = m["ts_ns"] // 10**9
        d = by.setdefault(t, {"t": t, "lag": 0, "rate_eps": 0.0, "open_sessions": 0, "workers": 0, "alerts": 0})
        d["lag"] += m.get("lag") or 0
        d["rate_eps"] += m.get("rate_eps") or 0.0
        d["open_sessions"] += m.get("open_sessions") or 0
        d["alerts"] += m.get("alerts") or 0
        d["workers"] += 1
    return [by[t] for t in sorted(by)]


# ---- process orchestration --------------------------------------------------------------------------

class Ctx:
    """Loaded once per experiment session: dataset features and cached replay lists."""

    def __init__(self, bundle: str = "models/hdfs-drain-pca-early"):
        self.bundle = bundle
        self.cf = load_or_build("hdfs", "chronological")
        self._cache: tuple[int, list] | None = None

    def events(self, needed: int) -> list:
        k = next((s for s in SESSION_STEPS if s * LINES_PER_SESSION >= needed * 1.03), SESSION_STEPS[-1])
        if self._cache and self._cache[0] == k:
            ev = self._cache[1]
        else:
            self._cache = None                       # free the previous list before loading a larger one
            _, ev = replay_events(self.cf, k if k < SESSION_STEPS[-1] else None)
            self._cache = (k, ev)
        if len(ev) < needed:
            raise ValueError(f"only {len(ev):,} cached events, need {needed:,}")
        return ev[:needed]


class MetricsCollector(threading.Thread):
    """Reads the engines' per-second metrics from Kafka while a run is in progress."""

    def __init__(self, group: str):
        super().__init__(daemon=True)
        self.rows: list[dict] = []
        self._halt = threading.Event()
        self._latest: dict[int, dict] = {}
        self.c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "auto.offset.reset": "earliest",
                           "enable.auto.commit": False})
        self.c.subscribe([TOPIC_METRICS])

    def run(self):
        while not self._halt.is_set():
            m = self.c.poll(0.2)
            if m is None or m.error():
                continue
            row = json.loads(m.value())
            row["recv_ns"] = time.time_ns()
            self.rows.append(row)
            self._latest[row["worker"]] = row

    def total_lag(self, max_age_s: float = 3.0) -> int:
        now = time.time_ns()
        return sum(r.get("lag") or 0 for r in self._latest.values() if now - r["recv_ns"] < max_age_s * 1e9)

    def close(self):
        self._halt.set()
        self.join(timeout=5)
        self.c.close()


def _taskset(pid: int, cpus: str) -> None:
    subprocess.run(["taskset", "-a", "-pc", cpus, str(pid)], capture_output=True, check=False)


def broker_pid() -> int:
    return int(KAFKA_PID_FILE.read_text())


class Pinned:
    """Context manager: broker on core 0, this (producer) process on core 1; everything restored on exit."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __enter__(self):
        if self.enabled:
            self.saved = os.sched_getaffinity(0)
            _taskset(broker_pid(), BROKER_CPUS)
            os.sched_setaffinity(0, PRODUCER_CPUS)
        return self

    def __exit__(self, *_):
        if self.enabled:
            os.sched_setaffinity(0, self.saved)
            _taskset(broker_pid(), f"0-{os.cpu_count() - 1}")


def _spawn_worker(cfg: RunConfig, bundle_path: str, wid: int, group: str, run_dir: Path) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "logsentinel.stream.engine", "--bundle", bundle_path, "--bootstrap", BOOTSTRAP,
           "--group", group, "--worker-id", str(wid), "--run-dir", str(run_dir),
           "--ready-file", str(run_dir / f"ready-{wid}"), "--batch", str(cfg.batch),
           "--min-lines", str(cfg.min_lines), "--exit-after-idle-s", "60"]
    if cfg.pin:
        cmd = ["taskset", "-c", WORKER_CPUS, *cmd]
    return subprocess.Popen(cmd, stdout=open(run_dir / f"worker-{wid}.log", "w"), stderr=subprocess.STDOUT,
                            cwd=ROOT)


def run_once(cfg: RunConfig, ctx: Ctx, out_dir: Path, run_id: str | None = None) -> dict:
    run_id = run_id or f"perf-{time.strftime('%H%M%S')}-{os.urandom(2).hex()}"
    run_dir = out_dir / "work" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    events = ctx.events(cfg.total_events())
    ensure_topics(BOOTSTRAP, cfg.partitions, recreate=True)
    collector = MetricsCollector(group=f"{run_id}-metrics")
    collector.start()
    sampler = SysSampler() if cfg.sysmon else None
    if sampler:
        sampler.start()
    procs: list[subprocess.Popen] = []
    scale_events: list[dict] = []
    stop_scaler = threading.Event()

    def add_worker():
        wid = len(procs)
        procs.append(_spawn_worker(cfg, ctx.bundle, wid, run_id, run_dir))
        return wid

    try:
        for _ in range(cfg.workers):
            add_worker()
        wait_ready(run_dir, cfg.workers, cfg.partitions, procs)

        if cfg.autoscale:
            def scaler():
                state: dict = {}
                while not stop_scaler.wait(0.5):
                    if autoscale_decision(state, collector.total_lag(), time.time(), len(procs), cfg.autoscale):
                        scale_events.append({"t_ns": time.time_ns(), "lag": collector.total_lag(),
                                             "workers_after": len(procs) + 1})
                        add_worker()
            threading.Thread(target=scaler, daemon=True).start()

        load_before = os.getloadavg()
        bpid = broker_pid()
        broker_uptime = proc_uptime_seconds(bpid)
        broker_cpu0 = proc_cpu_seconds(bpid)
        with Pinned(cfg.pin):
            prod = replay_segments(events, BOOTSTRAP, cfg.segment_events(), cfg.partitions,
                                   linger_ms=cfg.linger_ms, compression=cfg.compression)
        for p in procs:
            p.wait(timeout=600)
        broker_cpu = proc_cpu_seconds(bpid) - broker_cpu0        # whole run incl. the drain (where fetches happen)
    finally:
        stop_scaler.set()
        for p in procs:
            if p.poll() is None:
                p.kill()
        time.sleep(1.5)                           # let the last metrics messages arrive
        collector.close()
        sys_samples = sampler.close() if sampler else []

    recs, stats = [], []
    for w in range(len(procs)):
        f = run_dir / f"worker-{w}.jsonl"
        if f.exists():
            recs += [json.loads(line) for line in f.read_text().splitlines()]
        st = run_dir / f"worker-{w}.stats.json"
        if st.exists():
            stats.append(json.loads(st.read_text()))
    consumed = sum(s["events"] for s in stats)
    starts = [s["first_recv_ns"] for s in stats if s["first_recv_ns"]]
    span = (max(s["last_recv_ns"] for s in stats) - min(starts)) / 1e9 if starts else 0.0
    series = series_per_second(collector.rows)
    busy = [p["rate_eps"] for p in series if p["lag"] > 1000]
    lat = pct_table(stage_latencies(recs))
    result = {
        "config": asdict(cfg), "run_id": run_id, "env": capture_env(), "load_avg_before": list(load_before),
        "complete": consumed == prod["events"] and len(stats) == len(procs),
        "broker_uptime_s": broker_uptime, "cold_start": broker_uptime < COLD_BROKER_S,
        "producer": {k: prod[k] for k in ("events", "send_seconds", "achieved_rate", "first_send_ns", "last_send_ns",
                                          "segments", "cpu_seconds")},
        "consumer": {"events": consumed, "span_s": span, "rate_eps": consumed / span if span else None,
                     "busy_rate_eps_median": float(np.median(busy)) if busy else None,
                     "drain_s": (max(s["last_recv_ns"] for s in stats) - prod["last_send_ns"]) / 1e9 if stats else None,
                     "workers": len(procs),
                     "worker_cpu_seconds": [s["cpu_seconds"] for s in stats],
                     "worker_cpu_util": [s["cpu_seconds"] / span for s in stats] if span else None},
        "broker_cpu_seconds": broker_cpu,
        "alerts": {k: sum(1 for r in recs if r.get("kind") == k and r.get("alerted"))
                   for k in ("incremental", "deadline", "deadline_eos")},
        "latency_ms": lat, "scale_events": scale_events,
        "series": series, "sys_samples": sys_samples,
    }
    (out_dir / "runs").mkdir(exist_ok=True)
    return result
