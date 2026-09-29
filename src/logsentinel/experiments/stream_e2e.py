"""End-to-end streaming benchmark on HDFS: replay test-split sessions through Kafka into N engine workers.

    scripts/kafka.sh start
    python -m logsentinel.experiments.stream_e2e --bundle models/hdfs-drain-pca --rate 5000 --sessions 20000

Writes results/stream/<run_id>/{summary.json, env.json, worker-*.jsonl, worker-*.stats.json, producer.json}.
Sessions are replayed COMPLETE (all their lines, original log order), so online detection is comparable
to the offline number printed alongside it.
"""
import argparse
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from ..common.config import ROOT
from ..common.env import capture_env
from ..features.counts import load_or_build
from ..models.bundle import Bundle, offline_scores
from ..stream.admin import ensure_topics
from ..stream.engine import resolve_bundle
from ..stream.producer import load_replay, replay
from ..stream.ready import wait_ready
from . import metrics as mt

BOOTSTRAP = "127.0.0.1:9092"


def replay_events(cf, n_sessions: int | None):
    """First `n_sessions` test sessions (by first appearance), all their lines; cached on disk."""
    test_ids = [cf.ids[i] for i in cf.rows("test")]
    ids = test_ids[:n_sessions] if n_sessions else test_ids
    cache = ROOT / "data" / "replay" / f"hdfs.test.{len(ids)}.pkl"
    if cache.exists():
        return ids, pickle.loads(cache.read_bytes())
    ev = load_replay(ROOT / "data/raw/hdfs/HDFS.log", set(ids), max_events=10**9)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(ev))
    return ids, ev


def pct(x, q):
    return float(np.percentile(x, q)) if len(x) else float("nan")


def lat(a) -> dict:
    return {"p50": pct(a, 50), "p95": pct(a, 95), "p99": pct(a, 99), "max": float(a.max()) if len(a) else None}


def summarize(run_dir: Path, cf, expected_ids, prod: dict, workers: int, bundle: Bundle) -> dict:
    thr = bundle.threshold
    recs = [json.loads(line) for w in range(workers)
            for line in (run_dir / f"worker-{w}.jsonl").read_text().splitlines()]
    stats = [json.loads((run_dir / f"worker-{w}.stats.json").read_text()) for w in range(workers)]
    label_of = dict(zip(cf.ids, cf.labels.tolist(), strict=True))
    injected = [r for r in recs if r["id"] not in label_of]           # live-injected sessions have no dataset label
    recs = [r for r in recs if r["id"] in label_of]
    got = {r["id"]: r for r in recs}
    scored = [k for k in expected_ids if k in got]
    y = np.array([label_of[k] for k in scored])
    final = np.array([got[k]["final_score"] for k in scored])
    alerted = np.array([got[k]["alerted"] for k in scored])
    # streaming alert-any-time as a classifier: precision/recall of "an alert was ever raised"
    tp, fp = int((alerted & (y == 1)).sum()), int((alerted & (y == 0)).sum())
    fn = int((~alerted & (y == 1)).sum())
    p_ = tp / (tp + fp) if tp + fp else 0.0
    r_ = tp / (tp + fn) if tp + fn else 0.0
    stream = {"precision": p_, "recall": r_, "f1": 2 * p_ * r_ / (p_ + r_) if p_ + r_ else 0.0,
              "tp": tp, "fp": fp, "fn": fn}
    # equivalence: final online score vs the offline score of the same session
    off_s, _ = offline_scores(bundle, cf, "test")
    off_of = dict(zip([cf.ids[i] for i in cf.rows("test")], off_s.tolist(), strict=True))
    diff = np.array([abs(got[k]["final_score"] - off_of[k]) for k in scored])
    ms = 1e6
    al_all = [r for r in recs if r["alerted"]]
    al = [r for r in al_all if r["kind"] != "deadline_eos"]     # latency is only meaningful for live triggers
    kinds = {k: sum(r["kind"] == k for r in al_all) for k in ("incremental", "deadline", "deadline_eos")}
    ev_tp = np.array([r["evidence_log_s"] for r in al_all if label_of[r["id"]] == 1])
    transport = np.array([(r["t_trigger_recv"] - r["t_trigger_send"]) / ms for r in al])
    compute = np.array([(r["t_scored"] - r["t_trigger_recv"]) / ms for r in al])
    emit = np.array([(r["t_alert"] - r["t_scored"]) / ms for r in al])
    e2a = np.array([(r["t_alert"] - r["t_trigger_send"]) / ms for r in al])
    frac_at_alert = np.array([r["n_at_alert"] / r["n"] for r in al])
    events = sum(st["events"] for st in stats)
    span = (max(st["last_recv_ns"] for st in stats) - min(st["first_recv_ns"] for st in stats)) / 1e9
    off = mt.at_threshold(off_s, np.array([label_of[i] for i in off_of]), thr)
    return {
        "sessions_expected": len(expected_ids), "sessions_scored": len(scored),
        "coverage": len(scored) / len(expected_ids), "events_consumed": events,
        "producer": prod,
        "consumer_rate_eps": events / span if span > 0 else None,
        "drain_seconds_after_last_send": (max(st["last_recv_ns"] for st in stats) - prod["last_send_ns"]) / 1e9,
        "engine_score_seconds": sum(st["score_seconds"] for st in stats),
        "injected_sessions": len(injected), "injected_alerted": sum(r["alerted"] for r in injected),
        "alerts": len(al_all), "alerts_by_kind": kinds,
        "evidence_delay_log_s_true_alerts": {"p50": pct(ev_tp, 50), "p95": pct(ev_tp, 95)},
        "stream_alert_any_time": stream,
        "final_full_session": {**mt.at_threshold(final, y, thr), **mt.ranking(final, y)},
        "offline_reference_full_test": {**off, **mt.ranking(off_s, np.array([label_of[i] for i in off_of]))},
        "final_vs_offline_abs_diff": {"share_equal_1e-6": float((diff < 1e-6).mean()),
                                       "median": float(np.median(diff)), "max": float(diff.max())},
        "alert_at_fraction_of_session_lines": {"p50": pct(frac_at_alert, 50), "p95": pct(frac_at_alert, 95)},
        "latency_ms": {"transport": lat(transport), "compute": lat(compute), "emit": lat(emit),
                       "event_to_alert": lat(e2a)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=str(ROOT / "models/hdfs-drain-pca"), help="bundle dir or active:<dataset>")
    ap.add_argument("--rate", type=float, default=2000, help="events/s; 0 = burst")
    ap.add_argument("--sessions", type=int, default=5000, help="test sessions to replay; 0 = all")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--partitions", type=int, default=6)
    ap.add_argument("--min-lines", type=int, default=10)
    ap.add_argument("--no-incremental", action="store_true", help="final scores only (pure throughput)")
    ap.add_argument("--compression", default="none")
    ap.add_argument("--run-id", default=time.strftime("%Y%m%d-%H%M%S"))
    a = ap.parse_args()

    run_dir = ROOT / "results" / "stream" / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "env.json").write_text(json.dumps(capture_env() | {"args": {k: str(v) for k, v in vars(a).items()}}, indent=2))
    bundle_path = resolve_bundle(a.bundle)
    bundle = Bundle.load(bundle_path)
    cf = load_or_build("hdfs", "chronological")
    ids, events = replay_events(cf, a.sessions or None)
    print(f"replaying {len(events):,} lines of {len(ids):,} sessions "
          f"at {'burst' if not a.rate else f'{a.rate:,.0f}/s'} with {a.workers} worker(s)", flush=True)

    ensure_topics(BOOTSTRAP, a.partitions, recreate=True)
    procs = []
    for w in range(a.workers):
        ready = run_dir / f"ready-{w}"
        ready.unlink(missing_ok=True)
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "logsentinel.stream.engine", "--bundle", str(bundle_path), "--bootstrap", BOOTSTRAP,
             "--group", a.run_id, "--worker-id", str(w), "--run-dir", str(run_dir), "--ready-file", str(ready),
             "--exit-after-idle-s", "60", "--min-lines", str(a.min_lines), *(["--no-incremental"] if a.no_incremental else [])],
            stdout=open(run_dir / f"worker-{w}.log", "w")))  # noqa: SIM115
    wait_ready(run_dir, a.workers, a.partitions, procs)

    prod = replay(events, BOOTSTRAP, a.rate or None, a.partitions, compression=a.compression)
    (run_dir / "producer.json").write_text(json.dumps(prod))
    print(f"producer: {prod['achieved_rate']:,.0f} ev/s over {prod['send_seconds']:.1f}s", flush=True)
    for p in procs:
        p.wait(timeout=600)

    summary = summarize(run_dir, cf, ids, prod, a.workers, bundle)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    st, fi, off = summary["stream_alert_any_time"], summary["final_full_session"], summary["offline_reference_full_test"]
    L = summary["latency_ms"]
    print(f"sessions scored {summary['sessions_scored']:,}/{summary['sessions_expected']:,}  "
          f"alerts {summary['alerts']:,}  consumer rate {summary['consumer_rate_eps']:,.0f} ev/s  "
          f"drain {summary['drain_seconds_after_last_send']:.1f}s after last send")
    print(f"alerts by kind: {summary['alerts_by_kind']}  evidence delay (log-s, true alerts) "
          f"p50/p95 = {summary['evidence_delay_log_s_true_alerts']['p50']:.0f}/{summary['evidence_delay_log_s_true_alerts']['p95']:.0f}")
    print(f"stream (alert any time)  P/R/F1 = {st['precision']:.3f}/{st['recall']:.3f}/{st['f1']:.3f}")
    print(f"final full-session       P/R/F1 = {fi['precision']:.3f}/{fi['recall']:.3f}/{fi['f1']:.3f}  PR-AUC {fi['pr_auc']:.3f}")
    print(f"offline (whole test set) P/R/F1 = {off['precision']:.3f}/{off['recall']:.3f}/{off['f1']:.3f}  PR-AUC {off['pr_auc']:.3f}")
    d = summary["final_vs_offline_abs_diff"]
    print(f"final online vs offline score: {d['share_equal_1e-6']:.1%} identical, max |diff| {d['max']:.3g}")
    for k in ("transport", "compute", "emit", "event_to_alert"):
        print(f"  {k:15s} p50 {L[k]['p50']:8.1f}  p95 {L[k]['p95']:8.1f}  p99 {L[k]['p99']:8.1f} ms")
    print(f"results: {run_dir}")


if __name__ == "__main__":
    main()
