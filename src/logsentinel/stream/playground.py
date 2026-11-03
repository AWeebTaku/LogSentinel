"""Personal test tool: continuous traffic PLUS random anomaly bursts, in one process.

Not a stand-in for a real log source (that's live_feed.py) and not anything meant for production --
there is no real log-generating system behind this project yet, this exists purely so you can
exercise the full loop yourself: an anomaly appears, gets detected, you triage it (resolved or
false positive), and then check whether logsentinel.models.retrain_feedback picks it up. Run it
against staging, not production.

Like live_feed.py, loops the real HDFS test-split sessions forever for ordinary traffic. On top of
that, at random intervals it sends a burst of real known-anomalous sessions (the same pool
admin's "Inject anomaly burst" button draws from) stamped at the current stream time -- same
mechanism as stream/inject.py, just firing itself on a timer instead of waiting for a click.

    python -m logsentinel.stream.playground                         # defaults: see --help
    python -m logsentinel.stream.playground --anomaly-every 30 90 --anomaly-count 20 60
"""
import argparse
import json
import random
import signal
import time
from pathlib import Path

from confluent_kafka import Producer

from ..common.config import KAFKA_BOOTSTRAP
from ..experiments.stream_e2e import replay_events
from ..features.counts import load_or_build
from . import inject, pools
from .admin import ensure_topics
from .wire import TOPIC_RAW, hdfs_log_time


def run(rate: float, bootstrap: str, anomaly_every: tuple[float, float], anomaly_count: tuple[int, int],
        seed: int = 0, run_dir: Path | None = None) -> None:
    cf = load_or_build("hdfs", "chronological")
    _, events = replay_events(cf, None)
    pool = pools.load()
    ensure_topics(bootstrap, recreate=False)   # never wipes logs-raw: something else may already be consuming it
    rng = random.Random(seed)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))

    def progress(phase: str, sent: int, tag: int, watermark: float) -> None:
        if run_dir:
            (run_dir / "progress.json").write_text(json.dumps({
                "phase": phase, "sent": sent, "total": 0, "anomaly_bursts": tag, "watermark": watermark,
                "updated_ns": time.time_ns()}))

    p = Producer({"bootstrap.servers": bootstrap, "linger.ms": 5, "acks": 1})
    sent = tag = 0
    watermark = 0.0
    t0 = time.perf_counter()
    next_report = t0 + 5
    next_progress = t0
    next_anomaly = t0 + rng.uniform(*anomaly_every)
    print(f"[playground] personal test tool, not production: {len(events):,} log lines/lap, "
          f"~{rate:.0f} events/s, anomaly burst every {anomaly_every[0]:.0f}-{anomaly_every[1]:.0f}s "
          f"({anomaly_count[0]}-{anomaly_count[1]} sessions each). Ctrl+C to stop.", flush=True)
    progress("running", 0, 0, 0.0)
    try:
        while not stop["flag"]:
            order = list(range(len(events)))
            rng.shuffle(order)
            lap_t0 = time.perf_counter()
            for n, idx in enumerate(order):
                if stop["flag"]:
                    break
                key, line = events[idx]
                payload = b'{"i":%d,"t":%d,"l":%s}' % (sent, time.time_ns(), line)
                try:
                    p.produce(TOPIC_RAW, value=payload, key=key)
                except BufferError:
                    p.poll(0.05)
                sent += 1
                try:
                    watermark = max(watermark, hdfs_log_time(json.loads(line)))
                except ValueError:
                    pass
                target = lap_t0 + n / rate
                now = time.perf_counter()
                if now < target:
                    p.poll(min(target - now, 0.05))
                if now >= next_report:
                    print(f"[playground] {sent:,} events sent, {sent / (now - t0):.0f} events/s avg, "
                          f"{tag} anomaly burst(s) injected", flush=True)
                    next_report = now + 5
                if now >= next_progress:
                    progress("running", sent, tag, watermark)
                    next_progress = now + 1
                if now >= next_anomaly and watermark:
                    tag = (tag + 1) % 1000
                    count = rng.randint(*anomaly_count)
                    burst, keys = inject.build_burst(pool, count, watermark, tag, seed=rng.randint(0, 2**31))
                    inject.send(burst, bootstrap)
                    print(f"[playground] injected anomaly burst #{tag}: {count} session(s), "
                          f"e.g. {keys[0]}", flush=True)
                    next_anomaly = now + rng.uniform(*anomaly_every)
    finally:
        p.flush(30)
        progress("stopped", sent, tag, watermark)
        print(f"[playground] stopped: {sent:,} events sent, {tag} anomaly burst(s) injected", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rate", type=float, default=2000.0, help="events/s for ordinary traffic (default 2000)")
    ap.add_argument("--anomaly-every", type=float, nargs=2, metavar=("MIN_S", "MAX_S"), default=(60.0, 180.0),
                    help="random gap between anomaly bursts, seconds (default 60 180)")
    ap.add_argument("--anomaly-count", type=int, nargs=2, metavar=("MIN", "MAX"), default=(10, 50),
                    help="random anomalous-session count per burst (default 10 50)")
    ap.add_argument("--bootstrap", default=KAFKA_BOOTSTRAP)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run-dir", type=Path, default=None, help="write progress.json here (used by the admin UI)")
    a = ap.parse_args()
    run(a.rate, a.bootstrap, tuple(a.anomaly_every), tuple(a.anomaly_count), a.seed, a.run_dir)


if __name__ == "__main__":
    main()
