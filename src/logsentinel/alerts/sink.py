"""Alert sink: consume alerts-critical -> SQLite. Runs separately from the engine and the API.

Delivery is at-least-once: offsets are committed only AFTER the DB transaction commits, and the
UNIQUE (run, session_key) constraint makes replays harmless. Malformed messages are counted and skipped
(a poison message must not stall the topic); DB errors are retried, never skipped.

    python -m logsentinel.alerts.sink
"""
import argparse
import json
import signal
import sys
import time

from confluent_kafka import Consumer, KafkaException, TopicPartition

from ..store.db import connect, insert_alerts, insert_metrics
from ..stream.wire import TOPIC_ALERTS, TOPIC_METRICS


def parse(values: list[bytes]) -> tuple[list[dict], int]:
    """Decode raw message values -> alert dicts. Returns (valid alerts, number skipped as malformed)."""
    good, bad = [], 0
    for v in values:
        try:
            a = json.loads(v)
            if not isinstance(a, dict) or "id" not in a or "score" not in a:
                raise ValueError("missing id/score")
            float(a["score"])
            good.append(a)
        except (ValueError, TypeError):
            bad += 1
    return good, bad


def ingest(con, values: list[bytes], ingested_ns: int | None = None) -> tuple[int, int]:
    """One batch -> DB. Returns (rows inserted, malformed skipped); duplicates are silently ignored."""
    good, bad = parse(values)
    return insert_alerts(con, good, ingested_ns), bad


def parse_metrics(values: list[bytes]) -> list[dict]:
    good = []
    for v in values:
        try:
            m = json.loads(v)
            if isinstance(m, dict) and "run" in m and "ts_ns" in m:
                good.append(m)
        except ValueError:
            pass                      # a bad metrics sample is not worth a log line per second
    return good


def commit_batch(consumer, msgs) -> bool:
    """Commit explicit offsets (max per partition + 1) after the DB commit. A failed commit is not fatal:
    the rows are already stored and a replay is deduplicated, so we log it and carry on."""
    top: dict[tuple[str, int], int] = {}
    for m in msgs:
        key = (m.topic(), m.partition())
        top[key] = max(top.get(key, -1), m.offset())
    try:
        consumer.commit(offsets=[TopicPartition(t, p, o + 1) for (t, p), o in top.items()], asynchronous=False)
        return True
    except KafkaException as exc:
        print(f"[sink] offset commit failed (rows are stored; replay is harmless): {exc}", file=sys.stderr, flush=True)
        return False


def run(a) -> None:
    consumer = Consumer({"bootstrap.servers": a.bootstrap, "group.id": a.group, "enable.auto.commit": False,
                         "auto.offset.reset": "earliest", "fetch.wait.max.ms": 50})
    consumer.subscribe([TOPIC_ALERTS, TOPIC_METRICS])
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    inserted = skipped = seen = 0
    last_msg = time.monotonic()
    while not stop["flag"]:
        msgs = [m for m in consumer.consume(num_messages=a.batch, timeout=0.1) if not m.error()]
        if msgs:
            last_msg = time.monotonic()
            while not stop["flag"]:
                try:
                    with connect() as con:
                        alert_msgs = [m.value() for m in msgs if m.topic() == TOPIC_ALERTS]
                        ins, bad = ingest(con, alert_msgs)
                        insert_metrics(con, parse_metrics([m.value() for m in msgs if m.topic() == TOPIC_METRICS]))
                    break
                except Exception as exc:               # noqa: BLE001  DB busy/locked etc.: retry, do not drop
                    print(f"[sink] DB error, retrying: {exc}", file=sys.stderr, flush=True)
                    time.sleep(1)
            else:
                break
            commit_batch(consumer, msgs)                # only after the DB commit
            seen, inserted, skipped = seen + len(alert_msgs), inserted + ins, skipped + bad
            print(f"[sink] consumed={seen:,} inserted={inserted:,} malformed={skipped:,}", flush=True)
        elif a.exit_after_idle_s and seen and time.monotonic() - last_msg > a.exit_after_idle_s:
            break
    consumer.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", default="127.0.0.1:9092")
    ap.add_argument("--group", default="alert-sink")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--exit-after-idle-s", type=float, default=0.0, help="exit after this long idle (tests)")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
