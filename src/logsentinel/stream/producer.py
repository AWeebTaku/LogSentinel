"""Rate-controlled replay of an HDFS log slice into logs-raw.

Lines are loaded and pre-encoded BEFORE the clock starts so file I/O never throttles ingestion.
Only lines whose first block id is in `allowed` (e.g. the test-split blocks) are replayed, in original
log order, so interleaving across sessions is realistic.
"""
import json
import time
from collections.abc import Callable
from pathlib import Path

from confluent_kafka import Producer

from .wire import TOPIC_RAW, hdfs_key


def load_replay(log_path: Path, allowed: set[str], max_events: int) -> list[tuple[bytes, bytes]]:
    out = []
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            k = hdfs_key(line)
            if k in allowed:
                out.append((k.encode(), json.dumps(line).encode()))
                if len(out) >= max_events:
                    break
    return out


def replay_segments(events: list[tuple[bytes, bytes]], bootstrap: str, segments: list[tuple[int, float | None]],
                    partitions: int, linger_ms: int = 5, compression: str = "none",
                    on_progress: Callable[[int], None] | None = None,
                    should_stop: Callable[[], bool] | None = None) -> dict:
    """Send `events` in consecutive segments [(n_events, rate_eps or None=burst), ...], then one EOS marker per
    partition. Returns timing stats; `stopped` is True if should_stop() cut the replay short."""
    p = Producer({"bootstrap.servers": bootstrap, "linger.ms": linger_ms, "acks": 1,
                  "compression.type": compression, "batch.num.messages": 20000,
                  "queue.buffering.max.messages": 2_000_000, "queue.buffering.max.kbytes": 1_048_576})
    n, i = len(events), 0
    cpu0 = time.process_time()
    t0 = time.perf_counter()
    first_ns = time.time_ns()
    last_report = t0
    stopped = False
    seg_times: list[tuple[int, int, int]] = []          # (start_ns, end_ns, events) per segment, wall clock
    for seg_n, rate in segments:
        end, start, seg_t0 = min(n, i + seg_n), i, time.perf_counter()
        seg_start_ns = time.time_ns()
        while i < end and not stopped:
            if rate:
                target = min(end, start + int((time.perf_counter() - seg_t0) * rate) + 1)
                if target <= i:
                    p.poll(0)
                    time.sleep(0.0005)
                    continue
            else:
                target = min(end, i + 5000)
            while i < target:
                key, line = events[i]
                payload = b'{"i":%d,"t":%d,"l":%s}' % (i, time.time_ns(), line)
                try:
                    p.produce(TOPIC_RAW, value=payload, key=key)
                except BufferError:
                    p.poll(0.05)
                    continue
                i += 1
            p.poll(0)
            now = time.perf_counter()
            if on_progress and now - last_report >= 0.5:
                on_progress(i)
                last_report = now
            stopped = bool(should_stop and should_stop())
        seg_times.append((seg_start_ns, time.time_ns(), i - start))
        if stopped:
            break
    send_s = time.perf_counter() - t0
    last_send_ns = time.time_ns()
    for part in range(partitions):      # end-of-stream punctuation: one EOS marker per partition
        p.produce(TOPIC_RAW, value=b'{"eos":1}', partition=part)
    p.flush(60)
    if on_progress:
        on_progress(i)
    return {"events": i, "planned_events": n, "stopped": stopped, "send_seconds": send_s,
            "flush_seconds": time.perf_counter() - t0, "achieved_rate": i / send_s if send_s else 0.0,
            "first_send_ns": first_ns, "last_send_ns": last_send_ns, "segments": seg_times,
            "cpu_seconds": time.process_time() - cpu0}


def replay(events: list[tuple[bytes, bytes]], bootstrap: str, rate: float | None, partitions: int,
           linger_ms: int = 5, compression: str = "none") -> dict:
    """Single-rate replay; rate=None means burst (as fast as the client allows)."""
    out = replay_segments(events, bootstrap, [(len(events), rate)], partitions, linger_ms, compression)
    out["target_rate"] = rate
    return out
