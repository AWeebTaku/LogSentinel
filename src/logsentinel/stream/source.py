"""Source supervisor: one process that runs a whole live pipeline session for the UI.

Ensures topics -> starts N engine workers (consumer group = run id) -> replays test-split HDFS sessions with a
scenario (normal | spike) -> drains -> writes summary.json (same format as experiments/stream_e2e.py).
Progress is written to <run_dir>/progress.json every second. SIGTERM stops the replay early (engines still get
their end-of-stream markers and flush). Injection into the running stream is done by the API (stream/inject.py).

    python -m logsentinel.stream.source --run-id X --params '{"rate": 2000, "sessions": 10000}'
"""
import argparse
import json
import signal
import subprocess
import sys
import time
import traceback

from ..common.config import ROOT
from ..common.env import capture_env
from ..experiments.stream_e2e import replay_events, summarize
from ..features.counts import load_or_build
from ..models.bundle import Bundle
from .admin import ensure_topics
from .engine import resolve_bundle
from .producer import replay_segments
from .ready import wait_ready

BOOTSTRAP = "127.0.0.1:9092"
SPIKE = (0.4, 0.2, 0.4)      # share of events at base rate, at 10x base rate, at base rate again


def plan_segments(n_events: int, rate: float, scenario: str) -> list[tuple[int, float | None]]:
    if scenario == "normal":
        return [(n_events, rate)]
    if scenario == "spike":
        a = int(n_events * SPIKE[0])
        b = int(n_events * SPIKE[1])
        return [(a, rate), (b, rate * 10), (n_events - a - b, rate)]
    raise ValueError(f"unknown scenario {scenario!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--params", required=True, help="JSON: bundle, rate, sessions, workers, scenario, partitions")
    a = ap.parse_args()
    prm = {"bundle": "active:hdfs", "rate": 2000, "sessions": 10000, "workers": 1, "scenario": "normal",
           "partitions": 6, **json.loads(a.params)}
    run_dir = ROOT / "results" / "sources" / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time_ns()
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    procs: list[subprocess.Popen] = []

    def progress(phase: str, sent: int = 0, total: int = 0, **extra) -> None:
        (run_dir / "progress.json").write_text(json.dumps({
            "phase": phase, "sent": sent, "total": total, "started_ns": started, "updated_ns": time.time_ns(),
            "scenario": prm["scenario"], "rate": prm["rate"], "workers": prm["workers"], **extra}))

    try:
        progress("starting")
        (run_dir / "env.json").write_text(json.dumps(capture_env() | {"args": {k: str(v) for k, v in prm.items()}}))
        bundle_path = resolve_bundle(str(prm["bundle"]))
        bundle = Bundle.load(bundle_path)
        cf = load_or_build("hdfs", "chronological")
        ids, events = replay_events(cf, prm["sessions"] or None)
        ensure_topics(BOOTSTRAP, prm["partitions"], recreate=True)
        for w in range(prm["workers"]):
            ready = run_dir / f"ready-{w}"
            ready.unlink(missing_ok=True)
            procs.append(subprocess.Popen(
                [sys.executable, "-m", "logsentinel.stream.engine", "--bundle", str(bundle_path), "--bootstrap",
                 BOOTSTRAP, "--group", a.run_id, "--worker-id", str(w), "--run-dir", str(run_dir),
                 "--ready-file", str(ready), "--exit-after-idle-s", "300"],
                stdout=open(run_dir / f"worker-{w}.log", "w"), stderr=subprocess.STDOUT))  # noqa: SIM115
        wait_ready(run_dir, prm["workers"], prm["partitions"], procs)

        total = len(events)
        progress("running", 0, total)
        prod = replay_segments(events, BOOTSTRAP, plan_segments(total, float(prm["rate"]), prm["scenario"]),
                               prm["partitions"], on_progress=lambda i: progress("running", i, total),
                               should_stop=lambda: stop["flag"])
        (run_dir / "producer.json").write_text(json.dumps(prod))
        progress("draining", prod["events"], total)
        for p in procs:
            p.wait(timeout=300)
        if prod["stopped"]:
            progress("stopped", prod["events"], total)
        else:
            try:
                (run_dir / "summary.json").write_text(json.dumps(summarize(run_dir, cf, ids, prod, prm["workers"], bundle)))
                progress("finished", total, total, summary=True)
            except Exception:  # noqa: BLE001  the stream itself ran fine; report the missing summary, not a failed run
                traceback.print_exc()
                progress("finished", total, total, summary=False)
    except Exception:  # noqa: BLE001  top level: record the failure for the UI, then exit non-zero
        traceback.print_exc()
        progress("failed")
        sys.exit(1)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
