"""Explain E5 latency excursions: slow-alert windows vs JVM pauses, competing processes and CPU frequency.

    python -m logsentinel.experiments.e5_diagnose        # reads results/perf/e5d (run: perf run --only e5d --reps 10)

An excursion window = alerts with total latency over SLOW_MS clustered within GAP_S of each other. For each window
we report the stage that grew, then look for (a) a broker GC/safepoint pause overlapping the window, (b) CPU taken by
processes that are not ours on the engine cores (2-3), (c) a frequency drop on those cores, and compare each with the
distribution over all normal windows so a finding means something.
"""
import json
from pathlib import Path

import numpy as np

from .gclog import parse_pauses
from .harness import STAGES
from .perf import OUT

SLOW_MS, GAP_S, MIN_PAUSE_MS = 300.0, 1.0, 20.0
KAFKA_LOGS = Path.home() / ".local/share/logsentinel/kafka-logs"
ENGINE_CORES = (2, 3)
DOC = OUT.parent.parent / "docs" / "perf" / "e5-diagnosis.md"


def alert_records(run: dict) -> list[dict]:
    """Per live alert: send time (s), total latency (ms) and its stages, from the worker files."""
    out = []
    for f in (OUT / "e5d" / "work" / run["run_id"]).glob("worker-*.jsonl"):
        for line in f.read_text().splitlines():
            a = json.loads(line)
            if not a.get("alerted") or a.get("kind") == "deadline_eos" or a.get("t_trigger_broker_ms") is None:
                continue
            b = a["t_trigger_broker_ms"] * 1e6
            out.append({"t": a["t_trigger_send"] / 1e9, "total": (a["t_alert"] - a["t_trigger_send"]) / 1e6,
                        "producer_to_broker": max(0.0, (b - a["t_trigger_send"]) / 1e6),
                        "broker_to_consumer": max(0.0, (a["t_trigger_recv"] - b) / 1e6),
                        "engine_update": max(0.0, (a["t_scored"] - a["t_trigger_recv"] - a["score_dur_ns"]) / 1e6)})
    return sorted(out, key=lambda r: r["t"])


def slow_windows(alerts: list[dict]) -> list[dict]:
    wins, cur = [], None
    for a in alerts:
        if a["total"] < SLOW_MS:
            continue
        if cur and a["t"] - cur["end"] <= GAP_S:
            cur["end"] = a["t"]
            cur["alerts"].append(a)
        else:
            cur = {"start": a["t"], "end": a["t"], "alerts": [a]}
            wins.append(cur)
    for w in wins:
        w["until"] = max(x["t"] + x["total"] / 1000 for x in w["alerts"])       # last slow alert leaves the pipeline
        w["max_ms"] = max(x["total"] for x in w["alerts"])
        w["stage_mean"] = {s: float(np.mean([x[s] for x in w["alerts"]])) for s in STAGES[:3]}
    return wins


def pauses() -> list[dict]:
    text = ""
    for pat in ("kafkaServer-gc.log*", "safepoint.log*"):
        for f in sorted(KAFKA_LOGS.glob(pat)):
            text += f.read_text(errors="replace") + "\n"
    return [p for p in parse_pauses(text) if p["ms"] >= MIN_PAUSE_MS]


def window_features(samples: list[dict], pz: list[dict], t0: float, t1: float) -> dict:
    """CPU/frequency/competition/pause features over [t0, t1]."""
    inw = [s for s in samples if t0 - 0.5 <= s["t"] <= t1 + 0.5]
    other = [sum(p["cpu_pct"] for p in s["top"] if p["core"] in ENGINE_CORES and not p["comm"].startswith(("python", "java", "taskset")))
             for s in inw]
    busy = [max(s["core_util"][c] for c in ENGINE_CORES) for s in inw]
    freq = [min(s["freq_mhz"][c] for c in ENGINE_CORES) for s in inw]
    hit = [p for p in pz if t0 <= p["t"] and p["t"] - p["ms"] / 1000 <= t1]
    return {"n": len(inw), "other_cpu_pct_max": max(other, default=0.0), "engine_core_util_max": max(busy, default=0.0),
            "min_freq_mhz": min(freq, default=0.0), "pause_ms_max": max((p["ms"] for p in hit), default=0.0),
            "pause_kinds": sorted({p["kind"] for p in hit})}


def main() -> None:
    runs = [json.loads(f.read_text()) for f in sorted((OUT / "e5d").glob("*.rep*.json"))]
    runs = [r for r in runs if r["complete"] and r["sys_samples"]]
    pz = pauses()
    normal, slow = [], []
    n_alerts = 0
    for r in runs:
        al = alert_records(r)
        n_alerts += len(al)
        wins = slow_windows(al)
        t_lo, t_hi = r["producer"]["first_send_ns"] / 1e9, r["producer"]["last_send_ns"] / 1e9
        for w in wins:
            f = window_features(r["sys_samples"], pz, w["start"], w["until"])
            slow.append({"run": r["run_id"], "load": r["cell"], **f, "start_s": w["start"] - t_lo, "dur_s": w["until"] - w["start"],
                         "n_alerts": len(w["alerts"]), "max_ms": w["max_ms"], "stage_mean": w["stage_mean"]})
        busy_ts = [(w["start"], w["until"]) for w in wins]
        t = t_lo + 1.0                                                   # 1 s bins across the run, skipping slow windows
        while t + 1.0 <= t_hi:
            if not any(a <= t + 1.0 and b >= t for a, b in busy_ts):
                normal.append(window_features(r["sys_samples"], pz, t, t + 1.0))
            t += 1.0
    intro = (f"{len(runs)} instrumented runs, {n_alerts:,} alerts; excursion = alerts over {SLOW_MS:.0f} ms clustered "
             f"within {GAP_S:.0f} s. Pauses considered: broker JVM GC and safepoint pauses of at least {MIN_PAUSE_MS:.0f} ms "
             f"({len(pz)} in the logs).\n")
    lines = ["# E5 latency excursions: diagnosis\n", intro]
    if not slow:
        lines.append("**No excursion occurred in these runs**, so the cause could not be observed. "
                     f"Normal 1 s windows: {len(normal)}.")
    else:
        header = ("| Run | Start (s into run) | Duration (s) | Slow alerts | Max (ms) | Stage that grew (mean ms) | "
                  "Other-process CPU on engine cores (% max) | Engine core busy (max) | Min freq (MHz) | JVM pause (ms) |")
        lines += [f"**{len(slow)} excursion window(s) in {len({s['run'] for s in slow})} run(s).**\n", header, "|" + "---|" * 10]
        for s in slow:
            grew = max(s["stage_mean"], key=s["stage_mean"].get)
            lines.append(f"| {s['run']} | {s['start_s']:.1f} | {s['dur_s']:.1f} | {s['n_alerts']} | {s['max_ms']:.0f} | "
                         f"{grew} ({s['stage_mean'][grew]:.0f}) | {s['other_cpu_pct_max']:.0f} | {s['engine_core_util_max']:.2f} | "
                         f"{s['min_freq_mhz']:.0f} | {s['pause_ms_max']:.0f} {'(' + ', '.join(s['pause_kinds']) + ')' if s['pause_kinds'] else ''} |")
        def q(rows, key, p):
            return float(np.percentile([r[key] for r in rows], p)) if rows else float("nan")
        lines += ["", f"Baseline ({len(normal)} normal 1 s windows) versus the excursion windows:\n",
                  "| Feature | Normal p50 | Normal p95 | Normal p99 | Excursion median | Excursion max |", "|---|---|---|---|---|---|"]
        for key, label in (("other_cpu_pct_max", "Other-process CPU on engine cores (%)"), ("engine_core_util_max", "Engine core busy"),
                           ("min_freq_mhz", "Min frequency on engine cores (MHz)"), ("pause_ms_max", "JVM pause (ms)")):
            lines.append(f"| {label} | {q(normal, key, 50):.2f} | {q(normal, key, 95):.2f} | {q(normal, key, 99):.2f} | "
                         f"{np.median([s[key] for s in slow]):.2f} | {max(s[key] for s in slow):.2f} |")
        with_pause = sum(1 for s in slow if s["pause_ms_max"] > 0)
        lines.append(f"\nExcursions overlapping a JVM pause of at least {MIN_PAUSE_MS:.0f} ms: {with_pause} of {len(slow)}; "
                     f"normal windows overlapping one: {100 * np.mean([n['pause_ms_max'] > 0 for n in normal]):.1f}%.")
    DOC.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
