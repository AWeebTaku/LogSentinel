"""Live scenario injection: send a burst of known-anomalous sessions into the running stream.

Injected sessions get fresh block ids (so they are new sessions) and EVERY line is stamped with the current
stream time. They therefore never advance the engine's log-time watermark: a jump forward would fire the
age check early on normal sessions that are still in flight and cause false alerts.
"""
import json
import random
import time

from confluent_kafka import Producer

from .wire import TOPIC_RAW, format_hdfs_time


def build_burst(pool: list[dict], count: int, stream_time: float, tag: int, seed: int = 0):
    """Returns (events [(key_bytes, line_json_bytes)], injected session keys)."""
    rnd = random.Random(seed or time.time_ns())
    picks = [pool[rnd.randrange(len(pool))] for _ in range(count)]
    stamp = format_hdfs_time(int(stream_time))
    keys, per_session = [], []
    for i, s in enumerate(picks):
        key = f"blk_9{tag:03d}{i:05d}"                     # digits only: the block regex is blk_-?\d+
        keys.append(key)
        per_session.append([(key, stamp + ln[13:].replace(s["id"], key)) for ln in s["lines"]])
    # interleave sessions round-robin so the burst looks like concurrent writes, not one session at a time
    events = []
    for j in range(max(len(x) for x in per_session)):
        for sess in per_session:
            if j < len(sess):
                k, ln = sess[j]
                events.append((k.encode(), json.dumps(ln).encode()))
    return events, keys


def send(events, bootstrap: str) -> None:
    p = Producer({"bootstrap.servers": bootstrap, "linger.ms": 5, "acks": 1})
    for i, (key, line) in enumerate(events):
        payload = b'{"i":%d,"t":%d,"l":%s}' % (-1 - i, time.time_ns(), line)
        while True:
            try:
                p.produce(TOPIC_RAW, value=payload, key=key)
                break
            except BufferError:
                p.poll(0.05)
        if i % 1000 == 0:
            p.poll(0)
    p.flush(30)
