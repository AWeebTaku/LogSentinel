"""Watch supervisor: start engine workers against whatever is already on logs-raw, nothing else.

This is what the operator's "Start source" launches (see api/app.py) -- unlike
logsentinel.stream.source (the admin testing supervisor), it never produces any events itself.
For now that upstream feed is logsentinel.stream.live_feed, run separately, standing in for a real
log shipper; this process only ever consumes. Deliberately does NOT recreate logs-raw (ensure_topics
recreate=False) -- an external producer may already be writing to it, and recreating it out from
under that producer is exactly the bug class fixed in stream/admin.py for alerts-critical/
logsentinel-metrics. Runs open-ended (no total/sessions, just "running" until SIGTERM) and makes
no summary.json -- there is no fixed end to summarize.

    python -m logsentinel.stream.watch --run-id X --params '{"bundle": "active:hdfs", "workers": 1}'
"""
import argparse
import json
import signal
import subprocess
import sys
import time
import traceback

from ..common.config import KAFKA_BOOTSTRAP as BOOTSTRAP
from ..common.config import ROOT
from ..common.env import capture_env
from .admin import ensure_topics
from .engine import resolve_bundle
from .ready import wait_ready


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--params", required=True, help="JSON: bundle, workers, partitions")
    a = ap.parse_args()
    prm = {"bundle": "active:hdfs", "workers": 1, "partitions": 6, **json.loads(a.params)}
    run_dir = ROOT / "results" / "sources" / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time_ns()
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    procs: list[subprocess.Popen] = []

    def progress(phase: str, **extra) -> None:
        (run_dir / "progress.json").write_text(json.dumps({
            "phase": phase, "sent": 0, "total": 0, "started_ns": started, "updated_ns": time.time_ns(),
            "workers": prm["workers"], **extra}))

    try:
        progress("starting")
        (run_dir / "env.json").write_text(json.dumps(capture_env() | {"args": {k: str(v) for k, v in prm.items()}}))
        bundle_path = resolve_bundle(str(prm["bundle"]))
        ensure_topics(BOOTSTRAP, prm["partitions"], recreate=False)
        for w in range(prm["workers"]):
            ready = run_dir / f"ready-{w}"
            ready.unlink(missing_ok=True)
            procs.append(subprocess.Popen(
                [sys.executable, "-m", "logsentinel.stream.engine", "--bundle", str(bundle_path), "--bootstrap",
                 BOOTSTRAP, "--group", a.run_id, "--worker-id", str(w), "--run-dir", str(run_dir),
                 "--ready-file", str(ready)],
                stdout=open(run_dir / f"worker-{w}.log", "w"), stderr=subprocess.STDOUT))  # noqa: SIM115
        wait_ready(run_dir, prm["workers"], prm["partitions"], procs)

        progress("running")
        while not stop["flag"]:
            if any(p.poll() is not None for p in procs):
                raise RuntimeError("an engine worker exited unexpectedly; see worker-*.log")
            time.sleep(0.5)
        progress("stopping")
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(timeout=30)
        progress("stopped")
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
