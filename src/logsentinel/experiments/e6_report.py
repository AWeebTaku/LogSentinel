"""E6 report: results/perf/e6/{tables.md, figures/e6_spark_vs_python.png} from the stored runs."""
import json
from collections import defaultdict

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .e6 import DRAIN_TOLERANCE_S, OUT, TUNE_RATE


def load() -> dict[tuple[str, int], list[dict]]:
    runs: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for f in sorted(OUT.glob("*.rep*.json")):
        r = json.loads(f.read_text())
        runs[(r["engine"], r["rate"])].append(r)
    return runs


def good(rs: list[dict]) -> list[dict]:
    return [r for r in rs if r["complete"] and not r["cold_start"]]


def stat(vals):
    v = [x for x in vals if x is not None]
    return (float(np.median(v)), float(min(v)), float(max(v)), len(v)) if v else None


def fmt(s, d=0, unit=""):
    if s is None:
        return "n/a"
    f = f"{{:,.{d}f}}"
    return f"{f.format(s[0])}{unit} [{f.format(s[1])}-{f.format(s[2])}]"


def md(header, rows):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|",
                      *["| " + " | ".join(str(c) for c in r) + " |" for r in rows]])


def per_cell(runs, engine):
    out = []
    for (e, rate), rs in sorted(runs.items(), key=lambda kv: kv[0][1]):
        rs = good(rs)
        if e != engine or not rs:
            continue
        lat50, lat99 = [r["incremental_latency_ms"]["p50"] for r in rs], [r["incremental_latency_ms"]["p99"] for r in rs]
        out.append({"rate": rate, "n": len(rs), "cons": stat([r["consumer"]["rate_eps"] for r in rs]), "cap": stat([r.get("processing_capacity_eps") for r in rs]),
                    "drain": stat([r["consumer"]["drain_s"] for r in rs]), "p50": stat(lat50), "p99": stat(lat99),
                    "cpu": stat([r["engine_cpu_cores"] for r in rs]), "rss": stat([r["engine_peak_rss_mb"] for r in rs]),
                    "alerts": stat([r["alerts"] for r in rs]), "inc": stat([r["incremental"] for r in rs]),
                    "false": sum(r["false_alarms"] for r in rs), "startup": stat([r["startup_s"] for r in rs]),
                    "sustained": np.median([r["consumer"]["drain_s"] for r in rs]) <= DRAIN_TOLERANCE_S[engine.split("-")[0]]})
    return out


def main() -> None:
    runs = load()
    intro = ("Same model (`hdfs-drain-pca-early`), same events, same rate, both on cores 2-3 (broker core 0, producer core 1); Spark = local mode "
             "with 2 cores. 15 s of paced traffic per run, median with min-max over repeats. Latency = alert message timestamp minus the send time of the "
             "line that triggered it, incremental alerts only. \"Keeping up\" = backlog left after the last send is at most "
             f"{DRAIN_TOLERANCE_S['python']:.0f} s (Python) or {DRAIN_TOLERANCE_S['spark']:.0f} s (Spark, about two micro-batches).\n")
    parts = ["# E6: Spark Structured Streaming vs the Python consumer engine\n", intro]
    figs = {}
    for engine in ("python", "spark"):
        rows = per_cell(runs, engine)
        if not rows:
            continue
        figs[engine] = rows
        sus = [r["rate"] for r in rows if r["sustained"]]
        # highest rate such that it and every lower tested rate keep up
        best = None
        for r in rows:
            if not r["sustained"]:
                break
            best = r["rate"]
        parts += [f"## {engine}\n", f"Keeps up through **{best:,} events/s**" if best else "Does not keep up at any tested rate",
                  f" (keeping up at {sus}).\n" if sus else ".\n",
                  md(["Offered ev/s", "Runs", "Events/s over the consumption window (includes the tail)", "Processing capacity (Spark: events per second of batch time)", "Backlog after last send (s)", "Incremental latency p50 (ms)", "p99 (ms)",
                      "Engine CPU (cores)", "Peak memory (MB)", "Alerts (incremental)", "False alarms (all runs)", "Keeping up"],
                     [[f"{r['rate']:,}", r["n"], fmt(r["cons"]), fmt(r["cap"]), fmt(r["drain"], 1), fmt(r["p50"]), fmt(r["p99"]), fmt(r["cpu"], 2), fmt(r["rss"]),
                       f"{fmt(r['alerts'])} ({r['inc'][0]:.0f})", r["false"], "yes" if r["sustained"] else "no"] for r in rows])]
    if "python" in figs and "spark" in figs:
        common = sorted({r["rate"] for r in figs["python"]} & {r["rate"] for r in figs["spark"]})
        py, sp = {r["rate"]: r for r in figs["python"]}, {r["rate"]: r for r in figs["spark"]}
        parts += ["## Side by side at the shared rates\n", md(
            ["Offered ev/s", "Latency p50: Python / Spark (ms)", "p99: Python / Spark (ms)", "CPU cores: Python / Spark",
             "Peak memory MB: Python / Spark", "Incremental alerts: Python / Spark"],
            [[f"{r:,}", f"{py[r]['p50'][0]:,.0f} / {sp[r]['p50'][0]:,.0f}", f"{py[r]['p99'][0]:,.0f} / {sp[r]['p99'][0]:,.0f}",
              f"{py[r]['cpu'][0]:.2f} / {sp[r]['cpu'][0]:.2f}", f"{py[r]['rss'][0]:,.0f} / {sp[r]['rss'][0]:,.0f}",
              f"{py[r]['inc'][0]:.0f} / {sp[r]['inc'][0]:.0f}"] for r in common])]
    for eng in ("python", "spark"):
        st = [r["startup_s"] for k, rs in runs.items() if k[0] == eng for r in good(rs)]
        if st:
            parts.append(f"\nStartup ({eng}): median {np.median(st):.1f} s [{min(st):.1f}-{max(st):.1f}], n={len(st)} (process start to first partition assignment / first micro-batch).")
    tune = [(e, per_cell(runs, e)) for e in ("spark", "spark-p1", "spark-p4", "spark-mo10k")]
    trows = []
    for e, rows in tune:
        for r in rows:
            if r["rate"] == TUNE_RATE:
                trows.append([e, r["n"], fmt(r["drain"], 1), fmt(r["p50"]), fmt(r["p99"]), fmt(r["cpu"], 2)])
    if len(trows) > 1:
        tune_intro = (f"\n## Spark tuning check at {TUNE_RATE:,} events/s\n\nDefault = 2 shuffle partitions, at most 50,000 offsets per "
                      "micro-batch. p1 / p4 = 1 or 4 shuffle partitions; mo10k = at most 10,000 offsets per batch.\n")
        parts += [tune_intro, md(["Variant", "Runs", "Backlog after last send (s)", "Incremental latency p50 (ms)", "p99 (ms)", "Engine CPU (cores)"], trows)]
    (OUT / "tables.md").write_text("\n".join(str(p) for p in parts) + "\n")
    (OUT / "figures").mkdir(exist_ok=True)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    for engine, col in (("python", "tab:blue"), ("spark", "tab:orange")):
        rows = figs.get(engine, [])
        x = [r["rate"] / 1000 for r in rows]
        if not rows:
            continue
        ax[0].plot(x, [r["drain"][0] for r in rows], "o-", color=col, label=engine)
        ax[0].fill_between(x, [r["drain"][1] for r in rows], [r["drain"][2] for r in rows], color=col, alpha=.2)
        ax[1].plot(x, [r["p50"][0] for r in rows], "o-", color=col, label=f"{engine} p50")
        ax[1].plot(x, [r["p99"][0] for r in rows], "s--", color=col, label=f"{engine} p99")
        ax[2].plot(x, [r["cpu"][0] for r in rows], "o-", color=col, label=f"{engine} CPU cores")
    for e, ls in DRAIN_TOLERANCE_S.items():
        ax[0].axhline(ls, color="tab:blue" if e == "python" else "tab:orange", ls=":", lw=1)
    ax[0].set(xlabel="Offered load (k events/s)", ylabel="Backlog after last send (s)", yscale="symlog", title="Keeping up (dotted = tolerance)")
    ax[1].set(xlabel="Offered load (k events/s)", ylabel="Incremental alert latency (ms)", yscale="log", title="Event-to-alert latency")
    ax[2].set(xlabel="Offered load (k events/s)", ylabel="Engine CPU (cores, process tree)", title="CPU")
    for a in ax:
        a.grid(alpha=.3)
        a.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "figures" / "e6_spark_vs_python.png", dpi=130)
    plt.close(fig)
    print("wrote", OUT / "tables.md")


if __name__ == "__main__":
    main()
