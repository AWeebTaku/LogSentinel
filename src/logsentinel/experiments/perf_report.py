"""Turn results/perf runs into paper artifacts: results/perf/{tables.md, tables.csv, figures/*.png}.

    python -m logsentinel.experiments.perf_report

Every number is the MEDIAN over repeats with the min-max range and n; runs where the engines consumed a different
number of events than were sent are excluded from the statistics and counted separately.
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .harness import STAGES, saturation
from .perf import OUT, cells_e4a, cells_e4b, cells_e4c, cells_e5, cells_e7

CSV_ROWS: list[tuple] = []


def load(exp: str) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {}
    for f in sorted((OUT / exp).glob("*.rep*.json")):
        r = json.loads(f.read_text())
        runs.setdefault(r["cell"], []).append(r)
    return runs


def exclusions() -> dict[str, str]:
    f = OUT / "exclusions.json"
    return json.loads(f.read_text()) if f.exists() else {}


def run_key(r: dict) -> str:
    return f"{r['experiment']}/{r['cell']}.rep{r['rep']}"


def good(runs: list[dict]) -> list[dict]:
    """Runs used for steady-state statistics: complete, warm broker, and not set aside by hand (exclusions.json)."""
    ex = exclusions()
    return [r for r in runs if r["complete"] and not r.get("cold_start") and run_key(r) not in ex]


def load_e5() -> dict[str, list[dict]]:
    """E5 = the original runs plus the instrumented repeats (same configuration, same cells)."""
    merged: dict[str, list[dict]] = {}
    for exp in ("e5", "e5d"):
        for cell, rs in load(exp).items():
            merged.setdefault(cell, []).extend(rs)
    return merged


def stat(vals: list[float]) -> tuple[float, float, float, int] | None:
    v = [x for x in vals if x is not None]
    return (float(np.median(v)), float(min(v)), float(max(v)), len(v)) if v else None


def fmt(s, digits=0, unit="") -> str:
    if s is None:
        return "n/a"
    med, lo, hi, n = s
    f = f"{{:,.{digits}f}}"
    return f"{f.format(med)}{unit} [{f.format(lo)}-{f.format(hi)}] n={n}"


def record(exp: str, cell: str, metric: str, s) -> None:
    if s:
        CSV_ROWS.append((exp, cell, metric, *s))


def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def p99_of(r: dict, stage: str = "total"):
    return r["latency_ms"][stage]["p99"]


def sweep_rows(exp_runs: dict, cells) -> list[dict]:
    rows = []
    for c in cells:
        runs = good(exp_runs.get(c.name, []))
        if not runs:
            continue
        rows.append({"cell": c.name, "workers": c.cfg.workers, "offered": c.cfg.plan[0][1], "n": len(runs),
                     "n_bad": len(exp_runs[c.name]) - len(runs),
                     "ach": stat([r["consumer"]["rate_eps"] for r in runs]),
                     "drain": stat([r["consumer"]["drain_s"] for r in runs]),
                     "p99": stat([p99_of(r) for r in runs]),
                     "util": stat([max(r["consumer"]["worker_cpu_util"]) for r in runs]),
                     "broker": stat([r["broker_cpu_seconds"] for r in runs]),
                     "prod": stat([r["producer"]["cpu_seconds"] for r in runs])})
    return rows


def section_e4a() -> tuple[str, dict]:
    runs = load("e4a")
    rows = sweep_rows(runs, cells_e4a())
    sat = {}
    parts = []
    for w in (1, 2):
        rs = [r for r in rows if r["workers"] == w]
        if not rs:
            continue
        sat[w] = saturation([{"offered": r["offered"], "achieved": r["ach"][0], "drain_s": r["drain"][0],
                              "p99_ms": r["p99"][0]} for r in rs])
        table = md_table(
            ["Offered ev/s", "Consumed ev/s", "Backlog after last send (s)", "Event-to-alert p99 (ms)",
             "Engine CPU (cores)", "Broker CPU (s)", "Producer CPU (s)"],
            [[f"{r['offered']:,}", fmt(r["ach"]), fmt(r["drain"], 1), fmt(r["p99"]), fmt(r["util"], 2),
              fmt(r["broker"], 1), fmt(r["prod"], 1)] for r in rs])
        offered = [r["offered"] for r in rs]
        nxt = next((o for o in offered if sat[w] is not None and o > sat[w]), None)
        if sat[w] is None:
            head = f"**{w} worker(s)**: no tested rate was sustained"
        elif nxt is None:
            head = f"**{w} worker(s)**: every tested rate up to **{sat[w]:,} events/s** was sustained (limit not reached)"
        else:
            head = (f"**{w} worker{'s' if w > 1 else ''}**: sustained up to **{sat[w]:,} events/s**; "
                    f"the next tested rate, {nxt:,}, fails. The true limit lies in between.")
        parts.append(f"{head}\n\n{table}")
        for r in rs:
            for k in ("ach", "drain", "p99", "util", "broker", "prod"):
                record("e4a", r["cell"], k, r[k])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for w, col in ((1, "tab:blue"), (2, "tab:orange")):
        rs = [r for r in rows if r["workers"] == w]
        if not rs:
            continue
        x = [r["offered"] / 1000 for r in rs]
        ax[0].plot(x, [r["ach"][0] / 1000 for r in rs], "o-", color=col, label=f"{w} worker(s)")
        ax[0].fill_between(x, [r["ach"][1] / 1000 for r in rs], [r["ach"][2] / 1000 for r in rs], color=col, alpha=.2)
        ax[1].plot(x, [r["p99"][0] for r in rs], "o-", color=col, label=f"{w} worker(s)")
        ax[1].fill_between(x, [r["p99"][1] for r in rs], [r["p99"][2] for r in rs], color=col, alpha=.2)
    lim = max([r["offered"] for r in rows] + [1]) / 1000
    ax[0].plot([0, lim], [0, lim], "k--", lw=.8, label="offered = consumed")
    ax[0].set(xlabel="Offered load (k events/s)", ylabel="Consumed (k events/s)", title="E4a throughput vs offered load")
    ax[1].axhline(500, color="k", ls="--", lw=.8, label="500 ms target")
    ax[1].set(xlabel="Offered load (k events/s)", ylabel="Event-to-alert p99 (ms)", yscale="log",
              title="E4a latency vs offered load")
    for a in ax:
        a.legend()
        a.grid(alpha=.3)
    save(fig, "e4a_load_sweep")
    return "## E4a Offered-load sweep\n\nSustained = consumed >= 97% of offered, backlog gone within 1 s of the last " \
           "send, p99 under 500 ms, scanning upward and stopping at the first failing rate.\n\n" + "\n\n".join(parts), sat


def section_e4b() -> str:
    runs = load("e4b")
    base = good(runs.get("base", []))
    if not base:
        return ""
    b0 = np.median([r["consumer"]["rate_eps"] for r in base])
    rows, labels, meds, los, his = [], [], [], [], []
    for c in cells_e4b():
        rs = good(runs.get(c.name, []))
        if not rs:
            continue
        s = stat([r["consumer"]["rate_eps"] for r in rs])
        record("e4b", c.name, "capacity_eps", s)
        cfg = c.cfg
        desc = f"{cfg.workers}w, batch {cfg.batch}, {cfg.compression}, linger {cfg.linger_ms} ms, {cfg.partitions} partitions"
        rows.append([c.name, desc, fmt(s), f"{100 * s[0] / b0 - 100:+.1f}%" if c.name != "base" else "baseline",
                     fmt(stat([max(r["consumer"]["worker_cpu_util"]) for r in rs]), 2), fmt(stat([r["broker_cpu_seconds"] for r in rs]), 1)])
        labels.append(c.name); meds.append(s[0] / 1000); los.append((s[0] - s[1]) / 1000); his.append((s[2] - s[0]) / 1000)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(labels, meds, yerr=[los, his], capsize=3, color="tab:blue")
    ax.set(ylabel="Burst capacity (k events/s)", title="E4b tuning: capacity by configuration (median, min-max)")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=.3)
    save(fig, "e4b_tuning")
    return ("## E4b Tuning at burst (capacity)\n\nProducer sends 1M events as fast as it can; capacity = events consumed / "
            "time span of consumption. Baseline: 1 worker, batch 2000, no compression, linger 5 ms, 6 partitions.\n\n"
            + md_table(["Cell", "Configuration", "Capacity (ev/s)", "vs baseline", "Engine CPU (cores)", "Broker CPU (s)"], rows))


def section_e4c() -> str:
    runs = load("e4c")
    rows, series = [], {}
    for c in cells_e4c():
        rs = good(runs.get(c.name, []))
        if not rs:
            continue
        s = stat([r["consumer"]["rate_eps"] for r in rs])
        record("e4c", c.name, "capacity_eps", s)
        layout = "pinned" if c.cfg.pin else "unpinned"
        series.setdefault(layout, {})[c.cfg.workers] = s
    for layout, d in series.items():
        w1 = d.get(1)
        for w, s in sorted(d.items()):
            rows.append([layout, w, fmt(s), f"{s[0] / w1[0]:.2f}x" if w1 else "n/a", f"{100 * s[0] / w1[0] / w:.0f}%" if w1 else "n/a"])
    if not rows:
        return ""
    fig, ax = plt.subplots(figsize=(6, 4))
    for layout, d in series.items():
        ws = sorted(d)
        ax.errorbar(ws, [d[w][0] / 1000 for w in ws], yerr=[[(d[w][0] - d[w][1]) / 1000 for w in ws], [(d[w][2] - d[w][0]) / 1000 for w in ws]],
                    marker="o", capsize=3, label=layout)
    ax.set(xlabel="Engine workers", ylabel="Burst capacity (k events/s)", title="E4c worker scaling (4 cores)", xticks=[1, 2, 4])
    ax.legend()
    ax.grid(alpha=.3)
    save(fig, "e4c_scaling")
    return ("## E4c Worker scaling (burst capacity)\n\nPinned: broker on core 0, producer on core 1, workers share cores 2-3 "
            "(so 4 workers are oversubscribed). Unpinned: everything shares all four cores.\n\n"
            + md_table(["Layout", "Workers", "Capacity (ev/s)", "Speedup vs 1 worker", "Efficiency"], rows))


def pooled_latency(runs: list[dict]) -> np.ndarray:
    """Total event-to-alert latency (ms) of every live alert in every run of a cell, pooled (from the worker files)."""
    lats = []
    for r in runs:
        for f in (OUT / r["experiment"] / "work" / r["run_id"]).glob("worker-*.jsonl"):
            for line in f.read_text().splitlines():
                a = json.loads(line)
                if a.get("alerted") and a.get("kind") != "deadline_eos":
                    lats.append((a["t_alert"] - a["t_trigger_send"]) / 1e6)
    return np.array(lats)


def section_e5() -> str:
    runs = load_e5()
    rows, stack = [], {}
    for c in cells_e5():
        rs = good(runs.get(c.name, []))
        if not rs:
            continue
        offered = c.cfg.plan[0][1]
        n_alerts = sum(r["latency_ms"]["total"]["n"] for r in rs)
        for st in STAGES:
            p = {q: stat([r["latency_ms"][st][q] for r in rs]) for q in ("p50", "p95", "p99")}
            for q, s in p.items():
                record("e5", f"{c.name}:{st}", q, s)
            rows.append([f"{c.name.replace('load', '')}% ({offered:,} ev/s)", st, fmt(p["p50"], 1), fmt(p["p95"], 1), fmt(p["p99"], 1)])
            if st != "total":
                stack.setdefault(c.name, {})[st] = p["p50"][0] if p["p50"] else 0
            else:
                stack.setdefault(c.name, {})["_total99"] = p["p99"][0] if p["p99"] else 0
                stack[c.name]["_n"] = n_alerts
    if not rows:
        return ""
    pooled_rows = []
    for c in cells_e5():
        rs = good(runs.get(c.name, []))
        v = pooled_latency(rs) if rs else np.array([])
        if len(v):
            over = sum(1 for r in rs if (p99_of(r) or 0) > 500)
            pooled_rows.append([f"{c.name.replace('load', '')}% ({c.cfg.plan[0][1]:,} ev/s)", f"{len(v):,}",
                                f"{np.percentile(v, 50):.0f}", f"{np.percentile(v, 95):.0f}", f"{np.percentile(v, 99):.0f}",
                                f"{np.percentile(v, 99.9):.0f}", f"{100 * (v > 500).mean():.2f}%", f"{over} of {len(rs)}"])
            for q, val in ((50, 50), (95, 95), (99, 99), (99.9, 99.9)):
                CSV_ROWS.append(("e5", f"{c.name}:pooled_total", f"p{q}", float(np.percentile(v, val)), float(np.percentile(v, val)),
                                 float(np.percentile(v, val)), len(v)))
    fig, ax = plt.subplots(figsize=(8, 4.4))
    bottoms = np.zeros(len(stack))
    for st in STAGES[:-1]:
        vals = np.array([stack[k].get(st, 0) for k in stack])
        ax.bar([k.replace("load", "") + "%" for k in stack], vals, bottom=bottoms, label=st.replace("_", " "))
        bottoms += vals
    ax.plot([k.replace("load", "") + "%" for k in stack], [stack[k]["_total99"] for k in stack], "kD", label="total p99")
    ax.set(xlabel="Load (% of single-worker saturation)", ylabel="Latency (ms)", title="E5 event-to-alert latency by stage (median p50 per stage)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=.3)
    save(fig, "e5_latency_stages")
    return ("## E5 Latency breakdown by stage\n\nAlerts triggered during paced runs at 25/50/75% of single-worker saturation. "
            "Stages: producer to broker (includes client linger, batching, network, append), broker to consumer, "
            "engine update (rest of the micro-batch before scoring), scoring, alert emit. Broker append time has 1 ms "
            "resolution. Each cell is the median over repeats of that run's percentile.\n\n"
            + md_table(["Load", "Stage", "p50 (ms)", "p95 (ms)", "p99 (ms)"], rows)
            + "\n\n**Pooled over every alert and repeat** (a median of per-run percentiles hides a bad run; pooling does not). "
              "One run at 25% load had a 0.7 s stall before the broker and one run at 75% load had an 8 s consumer-side "
              "slowdown; the cause of both is unknown (the broker log shows nothing that distinguishes them from a normal run). Runs "
              "on a cold broker are excluded here and reported in the next section.\n\n"
            + md_table(["Load", "Alerts", "p50 (ms)", "p95 (ms)", "p99 (ms)", "p99.9 (ms)", "Share over 500 ms", "Runs with p99 over 500 ms"],
                       pooled_rows))


def section_cold() -> str:
    files = sorted((OUT / "e5cold").glob("cold*-run*.json"))
    if not files:
        return ""
    rows = []
    for f in files:
        r = json.loads(f.read_text())
        v = pooled_latency([{"experiment": "e5cold", "run_id": r["run_id"]}])
        restart, run = f.stem.split("-")
        rows.append([restart.replace("cold", "restart "), run.replace("run", "run "), "cold broker" if run == "run1" else "warm",
                     f"{len(v):,}", f"{np.percentile(v, 50):.0f}", f"{np.percentile(v, 99):.0f}", f"{int((v > 300).sum())}"])
        CSV_ROWS.append(("e5cold", f.stem, "p99_ms", float(np.percentile(v, 99)), float(np.percentile(v, 99)), float(np.percentile(v, 99)), len(v)))
    return ("## E5 cold-start effect\n\nThe first paced run after a broker restart is much slower than the following ones; the slow "
            "part is the producer-to-broker stage (about 500-700 ms on the slow alerts). 3 of 3 restarts reproduced it, 0 of 6 later "
            "runs did. A burst warm-up does not remove it. Same load as E5 at 25% (12,500 events/s).\n\n"
            + md_table(["Broker", "Run", "State", "Alerts", "p50 (ms)", "p99 (ms)", "Alerts over 300 ms"], rows))


def windowed_p99(run: dict, t0_ns: int, t1_ns: int):
    """p99 event-to-alert latency of alerts triggered in [t0, t1], recomputed from the run's worker files."""
    work = OUT / "e7" / "work" / run["run_id"]
    lats = []
    for f in work.glob("worker-*.jsonl"):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if r.get("alerted") and r.get("kind") != "deadline_eos" and t0_ns <= r["t_trigger_send"] <= t1_ns:
                lats.append((r["t_alert"] - r["t_trigger_send"]) / 1e6)
    return float(np.percentile(lats, 99)) if lats else None


def recovery_seconds(run: dict, base_rate: float):
    """Seconds from the end of the spike until total lag stays at or below one second of base traffic."""
    t_end = run["producer"]["segments"][1][1] / 1e9
    thr = max(1000.0, base_rate)
    pts = [p for p in run["series"] if p["t"] >= int(t_end)]
    for i, p in enumerate(pts):
        if all(q["lag"] <= thr for q in pts[i:]):
            return max(0.0, p["t"] - t_end)
    return None


def section_e7() -> str:
    runs = load("e7")
    cells = cells_e7()
    rows, curves = [], {}
    for c in cells:
        rs = good(runs.get(c.name, []))
        if not rs:
            continue
        base = c.cfg.plan[0][1]
        peak = stat([max(p["lag"] for p in r["series"]) for r in rs])
        rec_s = [recovery_seconds(r, base) for r in rs]
        recovered = [x for x in rec_s if x is not None]
        spike_p99 = stat([windowed_p99(r, r["producer"]["segments"][1][0], r["producer"]["segments"][1][1]) for r in rs])
        scale_t = [(e["t_ns"] - r["producer"]["first_send_ns"]) / 1e9 for r in rs for e in r["scale_events"]]
        for k, s in (("peak_lag", peak), ("recovery_s", stat(recovered)), ("spike_p99_ms", spike_p99)):
            record("e7", c.name, k, s)
        rows.append([c.name, fmt(peak), f"{len(recovered)}/{len(rs)}" if len(recovered) < len(rs) else f"{len(rs)}/{len(rs)}",
                     fmt(stat(recovered), 1), fmt(spike_p99),
                     f"{np.median(scale_t):.1f} s after start" if scale_t else "none"])
        # median-across-repeats lag curve on a common time axis (seconds since the first send)
        rel: dict[int, list[float]] = {}
        for r in rs:
            t0 = r["producer"]["first_send_ns"] // 10**9
            for p in r["series"]:
                rel.setdefault(int(p["t"] - t0), []).append(p["lag"])
        xs = sorted(k for k in rel if len(rel[k]) >= max(2, len(rs) // 2))
        curves[c.name] = (xs, [float(np.median(rel[k])) for k in xs], [min(rel[k]) for k in xs], [max(rel[k]) for k in xs],
                          float(np.median(scale_t)) if scale_t else None, rs[0]["producer"]["segments"], rs[0]["producer"]["first_send_ns"])
    if not rows:
        return ""
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for name, (xs, med, lo, hi, scale_at, segs, t0) in curves.items():
        ln, = ax.plot(xs, np.array(med) / 1000, label=name)
        ax.fill_between(xs, np.array(lo) / 1000, np.array(hi) / 1000, color=ln.get_color(), alpha=.15)
        if scale_at is not None:
            ax.axvline(scale_at, color=ln.get_color(), ls=":", lw=1)
    s0, s1 = (segs[1][0] - t0) / 1e9, (segs[1][1] - t0) / 1e9
    ax.axvspan(s0, s1, color="grey", alpha=.15, label="10x spike")
    ax.set(xlabel="Seconds since first send", ylabel="Consumer lag (k messages)", title="E7 lag under a 10x spike (median and min-max; dotted = scale-out)")
    ax.legend()
    ax.grid(alpha=.3)
    save(fig, "e7_spike_lag")
    return (f"## E7 Elasticity under a 10x spike\n\nBase {cells[0].cfg.plan[0][1]:,} ev/s, then 10x for "
            f"{cells[0].cfg.plan[1][0]} s, then base again. `elastic_1to2` starts with one worker and adds a second when total lag "
            "stays above 20,000 messages for 1 s (worker start-up and the group rebalance are included). Recovery = seconds "
            "after the spike ends until lag stays under one second of base traffic.\n\n"
            + md_table(["Config", "Peak lag (messages)", "Recovered", "Recovery after spike (s)", "p99 during spike (ms)", "Scale-out"], rows))


def section_env() -> str:
    for exp in ("e4a", "e4b", "e4c", "e5", "e7"):
        for rs in load(exp).values():
            if rs:
                e = rs[0]["env"]
                loads = [r["load_avg_before"][0] for x in (load(x) for x in ("e4a", "e4b", "e4c", "e5", "e7")) for v in x.values() for r in v]
                return ("## Setup\n\n" + md_table(["Item", "Value"], [
                    ["CPU", e["cpu"]], ["Cores / RAM", f"{e['cpu_count']} cores, {e['mem_gb']} GB"], ["OS", e["os"]],
                    ["Python", e["python"]], ["Kafka", "3.9.1 single broker (KRaft), 1 replica, LogAppendTime on logs-raw"],
                    ["Core layout (pinned)", "broker core 0, producer core 1, engine workers cores 2-3"],
                    ["Model", "hdfs-drain-pca-early (Drain3 + PCA, age check autoencoder at 30 s)"],
                    ["1-min load average when a run started", f"median {np.median(loads):.2f}, max {max(loads):.2f} (includes the benchmark's own previous run, so it is not a measure of other applications)"],
                    ["Repeats", "5 per cell, interleaved across cells; median with min-max"]]))
    return ""


def section_quality() -> str:
    total, bad = 0, []
    for exp in ("e4a", "e4b", "e4c", "e5", "e5d", "e7"):
        for cell, rs in load(exp).items():
            total += len(rs)
            bad += [f"{exp}/{cell} rep{r['rep']} (consumed {r['consumer']['events']:,} of {r['producer']['events']:,} sent)"
                    for r in rs if not r["complete"]]
    kept = []
    for f in sorted(OUT.glob("*/excluded/*.json")):                # runs set aside by hand, kept for the record
        r = json.loads(f.read_text())
        kept.append(f"- {f.parent.parent.name}/{r['cell']} rep{r['rep']}: consumed {r['consumer']['events']:,} of "
                    f"{r['producer']['events']:,} sent (a consumer-group rebalance during the run re-read messages; the "
                    "harness's readiness check was racy). Fixed and rerun; the original is kept in excluded/.")
    ex = exclusions()
    for exp in ("e4a", "e4b", "e4c", "e5", "e5d", "e7"):
        for rs in load(exp).values():
            for r in rs:
                if run_key(r) in ex:
                    kept.append(f"- {run_key(r)}: {ex[run_key(r)]}")
                elif r.get("cold_start"):
                    kept.append(f"- {run_key(r)}: broker uptime {r['broker_uptime_s']:.0f} s at the start (cold), excluded from steady-state statistics")
    head = (f"{total} runs are included; {len(bad)} still-incomplete runs are excluded from all statistics (consumed "
            "count differs from sent count).")
    lines = [head, *[f"- {b}" for b in bad], *(["", "Set aside earlier:", *kept] if kept else [])]
    return "## Data quality\n\n" + "\n".join(lines)


def save(fig, name: str) -> None:
    (OUT / "figures").mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / "figures" / f"{name}.png", dpi=130)
    plt.close(fig)


def main() -> None:
    e4a, sat = section_e4a()
    parts = ["# Performance results (LogSentinel, single 4-core host)\n", section_env(), e4a, section_e4b(), section_e4c(),
             section_e5(), section_cold(), section_e7(), section_quality()]
    (OUT / "tables.md").write_text("\n\n".join(p for p in parts if p) + "\n")
    with open(OUT / "tables.csv", "w") as f:
        f.write("experiment,cell,metric,median,min,max,n\n")
        f.writelines(",".join(str(x) for x in r) + "\n" for r in CSV_ROWS)
    print(f"wrote {OUT / 'tables.md'}, tables.csv and figures/; sustained rates by workers: {sat}")


if __name__ == "__main__":
    main()
