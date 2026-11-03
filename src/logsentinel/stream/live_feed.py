"""Standalone external log generator -- simulates a real system shipping logs on its own.

Not part of the admin testing suite and not launched by the API. Run it exactly like you would
some other team's service that happens to produce logs: start it in its own terminal, independent
of LogSentinel, and it keeps publishing to Kafka's logs-raw topic indefinitely until you stop it
(Ctrl+C). The operator instance's "Start source" then just starts its detection engine watching
whatever is already flowing in -- it never produces anything itself (see
logsentinel.stream.watch). When a real log shipper exists, it replaces this script; nothing else
in the pipeline needs to change, since both speak the same logs-raw wire format.

Loops the real HDFS test-split sessions forever (reshuffled each lap, so it doesn't feel like one
deterministic replay), since there is no real log source wired up yet. Never sends an
end-of-stream marker -- unlike a bounded test replay, this is meant to look like a system that
just keeps running.

    python -m logsentinel.stream.live_feed                   # ~2000 events/s, forever
    python -m logsentinel.stream.live_feed --rate 500
"""
import argparse
import random
import signal
import time

from confluent_kafka import Producer

from ..common.config import KAFKA_BOOTSTRAP
from ..experiments.stream_e2e import replay_events
from ..features.counts import load_or_build
from .wire import TOPIC_RAW


def run(rate: float, bootstrap: str, seed: int = 0) -> None:
    cf = load_or_build("hdfs", "chronological")
    _, events = replay_events(cf, None)          # every test-split session, real log lines
    rng = random.Random(seed)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))

    p = Producer({"bootstrap.servers": bootstrap, "linger.ms": 5, "acks": 1})
    sent, laps, t0, next_report = 0, 0, time.perf_counter(), time.perf_counter() + 5
    print(f"[live-feed] external log generator starting: {len(events):,} log lines/lap, ~{rate:.0f} events/s, "
          f"topic={TOPIC_RAW}, bootstrap={bootstrap}. Ctrl+C to stop.", flush=True)
    try:
        while not stop["flag"]:
            order = list(range(len(events)))
            rng.shuffle(order)                    # each lap feels like a fresh batch, not a loop
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
                target = lap_t0 + n / rate
                now = time.perf_counter()
                if now < target:
                    p.poll(min(target - now, 0.05))
                elif now - next_report >= 0:
                    p.poll(0)
                if now >= next_report:
                    print(f"[live-feed] lap {laps}, {sent:,} events sent, "
                          f"{sent / (now - t0):.0f} events/s avg", flush=True)
                    next_report = now + 5
            laps += 1
    finally:
        p.flush(30)                               # no EOS marker: a real system doesn't send one either
        print(f"[live-feed] stopped after {laps} lap(s), {sent:,} events sent", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rate", type=float, default=2000.0, help="events/s (default 2000)")
    ap.add_argument("--bootstrap", default=KAFKA_BOOTSTRAP)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    run(a.rate, a.bootstrap, a.seed)


if __name__ == "__main__":
    main()
