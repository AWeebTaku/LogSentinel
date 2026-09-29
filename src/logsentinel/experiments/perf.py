"""Performance experiments E4 (throughput ceiling), E5 (latency breakdown) and E7 (elasticity under a spike).

    python -m logsentinel.experiments.perf run                 # everything, 5 repeats, resumable (~2 h)
    python -m logsentinel.experiments.perf run --only e4a --reps 1
    python -m logsentinel.experiments.perf list                # show cells and how many repeats are done

Results: results/perf/<experiment>/<cell>.rep<k>.json. Repeats are INTERLEAVED across cells (rep 0 of every cell,
then rep 1, ...) so slow drift (thermal state, desktop background load) is spread over all configurations
instead of biasing whichever one happened to run last. Then: python -m logsentinel.experiments.perf_report
"""
import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..common.config import ROOT
from .harness import Ctx, RunConfig, run_once, saturation

OUT = ROOT / "results" / "perf"
SEC = 10                                    # seconds per paced run
E4A_W1 = [10_000, 20_000, 30_000, 40_000, 45_000, 50_000, 55_000, 60_000, 70_000]
E4A_W2 = [60_000, 70_000, 80_000, 100_000, 110_000, 120_000, 140_000]
BURST = 1_000_000                           # events for capacity (burst) runs
SPIKE_BASE, SPIKE_MULT, SPIKE_PRE, SPIKE_LEN, SPIKE_POST = 15_000, 10, 10, 8, 30


@dataclass
class Cell:
    experiment: str
    name: str
    cfg: RunConfig

    def path(self, rep: int) -> Path:
        return OUT / self.experiment / f"{self.name}.rep{rep}.json"


def burst(**kw) -> RunConfig:
    return RunConfig(plan=[[0, None]], events=BURST, **kw)


def cells_e4a() -> list[Cell]:
    """Offered-load sweep: at what rate does the backlog stop staying at zero?"""
    c = [Cell("e4a", f"w1_{r // 1000}k", RunConfig(plan=[[SEC, r]])) for r in E4A_W1]
    c += [Cell("e4a", f"w2_{r // 1000}k", RunConfig(plan=[[SEC, r]], workers=2)) for r in E4A_W2]
    return c


def cells_e4b() -> list[Cell]:
    """Tuning at burst (capacity): engine batch size, producer compression and linger, partitions."""
    c = [Cell("e4b", "base", burst())]
    c += [Cell("e4b", f"batch{b}", burst(batch=b)) for b in (500, 8000)]
    c += [Cell("e4b", "lz4", burst(compression="lz4"))]
    c += [Cell("e4b", f"linger{ms}", burst(linger_ms=ms)) for ms in (0, 20)]
    c += [Cell("e4b", f"w2_part{p}", burst(workers=2, partitions=p)) for p in (2, 6, 12)]
    return c


def cells_e4c() -> list[Cell]:
    """Worker scaling at burst, pinned (workers share cores 2-3) and unpinned (all four cores shared)."""
    c = []
    for w in (1, 2, 4):
        c.append(Cell("e4c", f"pinned_w{w}", burst(workers=w)))
        c.append(Cell("e4c", f"unpinned_w{w}", burst(workers=w, pin=False)))
    return c


def saturation_from_e4a(workers: int = 1, default: int = 50_000) -> int:
    rows = []
    for c in cells_e4a():
        if c.cfg.workers != workers:
            continue
        runs = [json.loads(c.path(k).read_text()) for k in range(9) if c.path(k).exists()]
        if runs:
            rate = c.cfg.plan[0][1]
            ach = sorted(r["consumer"]["rate_eps"] for r in runs)[len(runs) // 2]
            drain = sorted(r["consumer"]["drain_s"] for r in runs)[len(runs) // 2]
            p99 = sorted(r["latency_ms"]["total"]["p99"] or 0 for r in runs)[len(runs) // 2]
            rows.append({"offered": rate, "achieved": ach, "drain_s": drain, "p99_ms": p99})
    return saturation(rows) or default


def cells_e5(sat: int | None = None) -> list[Cell]:
    """Latency breakdown at 25%, 50% and 75% of the single-worker saturation rate."""
    sat = sat or saturation_from_e4a()
    return [Cell("e5", f"load{int(f * 100)}", RunConfig(plan=[[2 * SEC, int(sat * f)]])) for f in (0.25, 0.5, 0.75)]


def cells_e5d() -> list[Cell]:
    """E5 again with the system sampler on (diagnosing latency excursions); run with --reps 10, not in the default set."""
    from dataclasses import replace
    return [Cell("e5d", c.name, replace(c.cfg, sysmon=True)) for c in cells_e5()]


def cells_e7() -> list[Cell]:
    """A 10x traffic spike: one worker, two workers, and one worker with reactive scale-out to two."""
    plan = [[SPIKE_PRE, SPIKE_BASE], [SPIKE_LEN, SPIKE_BASE * SPIKE_MULT], [SPIKE_POST, SPIKE_BASE]]
    auto = {"max_workers": 2, "lag_threshold": 20_000, "hold_s": 1.0, "cooldown_s": 10.0}
    return [Cell("e7", "fixed_w1", RunConfig(plan=plan)),
            Cell("e7", "fixed_w2", RunConfig(plan=plan, workers=2)),
            Cell("e7", "elastic_1to2", RunConfig(plan=plan, autoscale=auto))]


EXPERIMENTS = {"e4a": cells_e4a, "e4b": cells_e4b, "e4c": cells_e4c, "e5": cells_e5, "e5d": cells_e5d, "e7": cells_e7}
DEFAULT_SET = ["e4a", "e4b", "e4c", "e5", "e7"]     # e5d is opt-in: --only e5d --reps 10


def run_cells(cells: list[Cell], reps: int, force: bool, ctx: Ctx) -> None:
    todo = [(rep, c) for rep in range(reps) for c in cells if force or not c.path(rep).exists()]
    print(f"{len(todo)} runs to do ({len(cells) * reps - len(todo)} already done)", flush=True)
    t0 = time.time()
    for i, (rep, c) in enumerate(todo, 1):
        c.path(rep).parent.mkdir(parents=True, exist_ok=True)
        res = run_once(c.cfg, ctx, OUT / c.experiment, run_id=f"{c.name}-r{rep}")
        res["cell"], res["rep"], res["experiment"] = c.name, rep, c.experiment
        c.path(rep).write_text(json.dumps(res))
        cons = res["consumer"]
        eta = (time.time() - t0) / i * (len(todo) - i) / 60
        print(f"[{i}/{len(todo)}] {c.experiment}/{c.name} rep{rep}: {cons['rate_eps'] or 0:>9,.0f} ev/s, "
              f"drain {cons['drain_s'] or 0:4.1f}s, p99 {res['latency_ms']['total']['p99'] or 0:7.0f} ms, "
              f"complete={res['complete']}  (~{eta:.0f} min left)", flush=True)
        if not res["complete"]:
            print("  WARNING: run incomplete (events consumed != sent); it is kept but flagged", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "list"])
    ap.add_argument("--only", nargs="*", choices=list(EXPERIMENTS), default=DEFAULT_SET)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cells: list[Cell] = []
    for name in a.only:                                   # e5 needs e4a's saturation, so order matters
        cells += EXPERIMENTS[name]()
    if a.action == "list":
        for c in cells:
            done = sum(c.path(k).exists() for k in range(a.reps))
            print(f"{c.experiment}/{c.name:16s} {done}/{a.reps}")
        return
    import os
    if os.getloadavg()[0] > 1.5:
        print(f"WARNING: 1-min load average is {os.getloadavg()[0]:.1f}; close other applications for clean numbers",
              file=sys.stderr)
    ctx = Ctx()
    print("warm-up runs (discarded): a burst, then 15 s of paced traffic (a cold broker is slow on the paced path)", flush=True)
    run_once(RunConfig(plan=[[0, None]], events=50_000), ctx, OUT / "warmup")
    run_once(RunConfig(plan=[[15, 12_500]]), ctx, OUT / "warmup")
    for name in a.only:
        if name in ("e5", "e5d"):
            print(f"{name.upper()} uses saturation = {saturation_from_e4a():,} ev/s (single worker, from E4a)", flush=True)
        run_cells(EXPERIMENTS[name](), a.reps, a.force, ctx)


if __name__ == "__main__":
    main()
