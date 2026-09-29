"""Streaming detection worker: consume logs-raw -> update sessions -> re-score touched sessions -> alerts.

Run N copies with the same --group to scale out (partitions are split between them; keyed by session,
so a session's lines always reach the same worker).

Per micro-batch (one consume() call) every session that received a line is re-scored in ONE vectorized
call; the first time a session's score reaches the threshold an alert is published to alerts-critical
(once per session). On end-of-stream (producer sends one EOS marker per partition) all open sessions are
flushed with a final full-session score, which equals the offline score for that session.

If the bundle has an age check (EarlyCheck), each session is also scored once when it is `age_s` LOG-seconds
old, driven by a per-worker event-time watermark (the newest log timestamp seen). That catches sessions that
stay incomplete (40% of HDFS anomalies are 2-4 line sessions that never grow). When the stream ends the
watermark jumps to +inf so pending checks still fire (kind "deadline_eos": excluded from latency stats).

Alert latency (ns, one host wall clock), for the line that triggered the alert
(for a deadline alert: the line whose timestamp pushed the watermark past the deadline):
  transport = t_trigger_recv - t_trigger_send    producer -> broker -> consumer
  compute   = t_scored - t_trigger_recv          rest of the batch's state updates + vectorized scoring
  emit      = t_alert - t_scored                 alert produce() call
  event->alert latency = t_alert - t_trigger_send   (the quantity the paper's <500 ms target refers to)
"""
import argparse
import contextlib
import json
import signal
import time
from pathlib import Path

import numpy as np
from confluent_kafka import Consumer, Producer

from ..models.bundle import Bundle, Scorer
from .sessionizer import Sessionizer
from .wire import TOPIC_ALERTS, TOPIC_METRICS, TOPIC_RAW, hdfs_log_time


def resolve_bundle(spec: str) -> Path:
    """A path, or `active:<dataset>` = the model currently promoted in the registry (read at start-up only)."""
    if not spec.startswith("active:"):
        return Path(spec)
    from ..store.db import active_model, connect
    with connect() as con:
        m = active_model(con, spec.split(":", 1)[1])
    if m is None:
        raise SystemExit(f"no active model registered for dataset {spec.split(':', 1)[1]!r}")
    return Path(m["path"])


def run(a) -> None:
    a.bundle = resolve_bundle(str(a.bundle))
    scorer = Scorer(Bundle.load(a.bundle))
    early = scorer.early
    sess = Sessionizer(scorer.line_col, early.age_s if early else None)
    run_dir = Path(a.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    consumer = Consumer({"bootstrap.servers": a.bootstrap, "group.id": a.group,
                         "auto.offset.reset": "earliest", "enable.auto.commit": True,
                         "fetch.min.bytes": 1, "fetch.wait.max.ms": 20,
                         "queued.min.messages": 100000})
    producer = Producer({"bootstrap.servers": a.bootstrap, "linger.ms": 5, "acks": 1})
    assigned = {"n": 0}

    def on_assign(c, parts):
        assigned["n"] = len(parts)
        if a.ready_file:
            Path(a.ready_file).write_text(str(len(parts)))

    consumer.subscribe([TOPIC_RAW], on_assign=on_assign)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))

    events = alerts = eos = 0
    watermark = float("-inf")
    wm_send = wm_recv = wm_broker = 0
    first_recv = last_recv = 0
    score_ns = 0
    last_msg = last_report = last_metrics = time.monotonic()
    prev_events = 0
    alert_lats: list[float] = []      # ms, alerts raised since the last metrics message
    batch_ms: list[float] = []        # ms, per non-empty micro-batch since the last metrics message

    def consumer_lag() -> int:
        lag = 0
        for tp in consumer.assignment():
            with contextlib.suppress(Exception):       # metrics must never break scoring
                hi = consumer.get_watermark_offsets(tp, cached=True)[1]
                pos = consumer.position([tp])[0].offset
                lag += max(0, hi - pos) if pos >= 0 else 0
        return lag

    def publish_metrics(dt: float) -> None:
        nonlocal prev_events
        pct = lambda v, q: float(np.percentile(v, q)) if v else None
        producer.produce(TOPIC_METRICS, value=json.dumps({
            "run": a.group, "worker": a.worker_id, "ts_ns": time.time_ns(), "events": events,
            "rate_eps": (events - prev_events) / dt, "open_sessions": len(sess.open), "alerts": alerts,
            "alerts_interval": len(alert_lats), "lag": consumer_lag(), "batch_ms_p95": pct(batch_ms, 95),
            "alert_lat_p50": pct(alert_lats, 50), "alert_lat_p95": pct(alert_lats, 95),
            "alert_lat_p99": pct(alert_lats, 99),
            "watermark": None if watermark == float("-inf") else watermark}).encode())
        prev_events = events
        alert_lats.clear()
        batch_ms.clear()

    def raise_alert(key, s, sc, kind, evidence_s, t_send, t_recv, t_scored, t_broker_ms, score_dur_ns):
        nonlocal alerts
        s.alerted, s.alert_kind, s.alert_score, s.n_at_alert, s.evidence_s = True, kind, float(sc), s.n, evidence_s
        s.t_trigger_send, s.t_trigger_recv, s.t_scored = t_send, t_recv, t_scored
        s.t_trigger_broker_ms, s.score_dur_ns = t_broker_ms, score_dur_ns
        producer.produce(TOPIC_ALERTS, key=key.encode(), value=json.dumps({
            "id": key, "kind": kind, "score": float(sc), "n_lines": s.n, "evidence_log_s": evidence_s,
            "t_trigger_send_ns": t_send, "worker": a.worker_id, "run": a.group, "model": Path(a.bundle).name,
            "threshold": early.threshold if kind.startswith("deadline") else scorer.threshold}).encode())
        s.t_alert = time.time_ns()
        alerts += 1
        if kind != "deadline_eos":
            alert_lats.append((s.t_alert - t_send) / 1e6)

    def fire_deadlines(due, t_send, t_recv, t_broker_ms, kind):
        nonlocal score_ns
        due = [(k, s) for k, s in due if not s.alerted]
        if not due:
            return
        t0 = time.time_ns()
        scores = scorer.score_snapshots([s.snap for _, s in due])
        t_scored = time.time_ns()
        score_ns += t_scored - t0
        for (key, s), sc in zip(due, scores, strict=True):
            if sc >= early.threshold:
                raise_alert(key, s, sc, kind, early.age_s, t_send, t_recv, t_scored, t_broker_ms, t_scored - t0)

    while not stop["flag"]:
        msgs = consumer.consume(num_messages=a.batch, timeout=0.05)
        now_ns = time.time_ns()
        t_batch = time.perf_counter()
        touched: dict[str, object] = {}
        for m in msgs:
            if m.error():
                continue
            d = json.loads(m.value())
            if "eos" in d:
                eos += 1
                continue
            key = m.key().decode()
            try:
                log_t = hdfs_log_time(d["l"])
            except ValueError:            # malformed timestamp: treat as "no time progress"
                log_t = watermark if watermark > float("-inf") else 0
            broker_ms = m.timestamp()[1]                  # LogAppendTime: when the broker appended the message
            if log_t > watermark:
                watermark, wm_send, wm_recv, wm_broker = log_t, d["t"], now_ns, broker_ms
            touched[key] = sess.add(key, d["l"], d["t"], now_ns, log_t, broker_ms)
            events += 1
        if msgs:
            last_recv, last_msg = now_ns, time.monotonic()
            first_recv = first_recv or now_ns
        if touched and not a.no_incremental:
            t0 = time.time_ns()
            scores = scorer.score_counts([s.counts for s in touched.values()])
            t_scored = time.time_ns()
            score_ns += t_scored - t0
            for (key, s), sc in zip(touched.items(), scores, strict=True):
                if sc >= scorer.threshold and not s.alerted and s.n >= a.min_lines:
                    raise_alert(key, s, sc, "incremental", s.last_log - s.first_log,
                                s.last_send, s.last_recv, t_scored, s.last_broker_ms, t_scored - t0)
        if early and msgs:
            fire_deadlines(sess.pop_due(watermark), wm_send, wm_recv, wm_broker, "deadline")
        if msgs:
            batch_ms.append((time.perf_counter() - t_batch) * 1000)
        producer.poll(0)
        now = time.monotonic()
        if now - last_metrics >= 1.0:
            publish_metrics(now - last_metrics)
            last_metrics = now
        if now - last_report >= 1.0:
            print(f"[w{a.worker_id}] events={events:,} sessions={len(sess.open):,} alerts={alerts:,}", flush=True)
            last_report = now
        if assigned["n"] and eos >= assigned["n"]:
            break
        if a.exit_after_idle_s and events and now - last_msg > a.exit_after_idle_s:
            break

    if early:                                          # end of stream = event time advances to infinity
        fire_deadlines(sess.pop_due(float("inf")), wm_send, wm_recv, wm_broker, "deadline_eos")
    keys = list(sess.open)
    t0 = time.time_ns()
    final = scorer.score_counts([sess.open[k].counts for k in keys]) if keys else []
    score_ns += time.time_ns() - t0
    with open(run_dir / f"worker-{a.worker_id}.jsonl", "w") as f:
        for k, fs in zip(keys, final, strict=True):
            s = sess.open[k]
            f.write(json.dumps({
                "id": k, "n": s.n, "final_score": float(fs), "alerted": s.alerted, "kind": s.alert_kind,
                "alert_score": s.alert_score, "n_at_alert": s.n_at_alert, "evidence_log_s": s.evidence_s, "t_trigger_send": s.t_trigger_send,
                "t_trigger_recv": s.t_trigger_recv, "t_trigger_broker_ms": s.t_trigger_broker_ms,
                "t_scored": s.t_scored, "score_dur_ns": s.score_dur_ns, "t_alert": s.t_alert}) + "\n")
    producer.flush(10)
    consumer.close()
    (run_dir / f"worker-{a.worker_id}.stats.json").write_text(json.dumps({
        "events": events, "sessions": len(keys), "alerts": alerts, "eos": eos, "first_recv_ns": first_recv,
        "last_recv_ns": last_recv, "score_seconds": score_ns / 1e9, "threshold": scorer.threshold,
        "cpu_seconds": time.process_time()}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="bundle dir, or active:<dataset> from the model registry")
    ap.add_argument("--bootstrap", default="127.0.0.1:9092")
    ap.add_argument("--group", default="logsentinel-engine")
    ap.add_argument("--worker-id", type=int, default=0)
    ap.add_argument("--batch", type=int, default=2000, help="max messages per consume() call")
    ap.add_argument("--run-dir", default="results/stream/adhoc")
    ap.add_argument("--ready-file", default=None)
    ap.add_argument("--min-lines", type=int, default=10,
                    help="don't alert on a session until it has this many lines (partial sessions look anomalous)")
    ap.add_argument("--no-incremental", action="store_true",
                    help="skip per-batch re-scoring (final scores only); for pure-throughput runs")
    ap.add_argument("--exit-after-idle-s", type=float, default=0.0,
                    help="safety: exit after this long without messages (0 = wait for EOS/SIGTERM)")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
