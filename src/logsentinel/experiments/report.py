"""Cells -> paper artifacts: results/offline/{tables.csv, table.md, figures/*.png}.

    python -m logsentinel.experiments.report
E1: detection quality (default parser drain, val-tuned threshold).  E2: parser ablation.
E3: threshold strategies (iforest + drain).  Numbers are mean +- std over seeds on the TEST split.
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .offline import OUT

THR = ["percentile99", "three_sigma", "tuned_val"]


def load_cells() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((OUT / "cells").glob("*.json"))]


def ms(vals) -> str:
    v = np.asarray(vals, dtype=float)
    return f"{v.mean():.3f} ± {v.std():.3f}" if len(v) > 1 else f"{v.mean():.3f}"


def long_rows(cells) -> pd.DataFrame:
    rows = []
    for c in cells:
        base = {k: c[k] for k in ("dataset", "mode", "parser", "model", "n_features", "n_test", "test_anomalies")}
        for r in c["runs"]:
            common = base | {"seed": r["seed"], "roc_auc": r["roc_auc"], "pr_auc": r["pr_auc"],
                             "fit_s": r["fit_s"], "score_ms_per_session": r["score_ms_per_session"]}
            for t in THR:
                rows.append(common | {"threshold_rule": t} | {k: r["thresholds"][t][k]
                            for k in ("threshold", "precision", "recall", "f1")})
            rows.append(common | {"threshold_rule": "oracle_test", "f1": r["oracle_test"]["f1"],
                                  "threshold": r["oracle_test"]["threshold"]})
    return pd.DataFrame(rows)


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(x) for x in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(out)


def agg(df, by, metrics) -> pd.DataFrame:
    g = df.groupby(by, sort=False)
    return g.agg({m: ms for m in metrics}).reset_index()


def add_prevalence(t: pd.DataFrame, L: pd.DataFrame) -> pd.DataFrame:
    """Test anomaly rate = the precision of a 'flag everything' detector (F1 = 2p/(1+p))."""
    prev = L.groupby(["dataset", "mode"]).apply(
        lambda g: g.test_anomalies.iloc[0] / g.n_test.iloc[0], include_groups=False)
    t = t.copy()
    t.insert(2, "prevalence", [f"{prev[(d, m)]:.3f}" for d, m in zip(t.dataset, t["mode"])])
    return t


def tables(L: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tuned = L[L.threshold_rule == "tuned_val"]
    e1 = agg(tuned[tuned.parser == "drain"], ["dataset", "mode", "model"],
             ["roc_auc", "pr_auc", "precision", "recall", "f1"])
    e2 = agg(tuned, ["dataset", "mode", "model", "parser"], ["pr_auc", "f1"])
    e2 = e2.pivot(index=["dataset", "mode", "model"], columns="parser", values=["pr_auc", "f1"])
    e2.columns = [f"{m}:{p}" for m, p in e2.columns]
    e2 = e2.reset_index()
    e3 = agg(L[(L.model == "iforest") & (L.parser == "drain")], ["dataset", "mode", "threshold_rule"],
             ["threshold", "precision", "recall", "f1"])
    e3.loc[e3.threshold_rule == "oracle_test", ["precision", "recall"]] = "-"
    cost = agg(tuned[tuned.parser == "drain"], ["dataset", "mode", "model"], ["fit_s", "score_ms_per_session"])
    e1, e3 = add_prevalence(e1, L), add_prevalence(e3, L)
    return {"E1 detection quality (parser=drain, val-tuned threshold)": e1,
            "E2 parser ablation (val-tuned threshold; PR-AUC and F1 per parser)": e2,
            "E3 threshold strategies (iforest + drain; oracle_test = best F1 on test, upper bound)": e3,
            "Model cost (parser=drain): fit seconds, scoring ms per session": cost}


def figures(cells) -> None:
    fig_dir = OUT / "figures"
    fig_dir.mkdir(exist_ok=True)
    by = {(c["dataset"], c["mode"], c["parser"], c["model"]): c for c in cells}
    for ds in sorted({c["dataset"] for c in cells}):
        for mode in sorted({c["mode"] for c in cells if c["dataset"] == ds}):
            fig, ax = plt.subplots(1, 2, figsize=(10, 4))
            for model in ("iforest", "pca", "ae"):
                c = by.get((ds, mode, "drain", model))
                if c and "curve" in c["runs"][0]:
                    cv = c["runs"][0]["curve"]
                    ax[0].plot(cv["r"], cv["p"], label=model)
            ax[0].set(xlabel="recall", ylabel="precision", title=f"E1 PR curves: {ds} ({mode}, drain)")
            ax[0].legend()
            c = by.get((ds, mode, "drain", "iforest"))
            if c:
                r0 = c["runs"][0]
                ax[1].plot(r0["curve"]["t"], r0["curve"]["f1"], color="black")
                for name, col in zip(THR, ("tab:blue", "tab:orange", "tab:green")):
                    ax[1].axvline(r0["thresholds"][name]["threshold"], color=col, ls="--", label=name)
                ax[1].set(xlabel="threshold", ylabel="F1 (test)", title="E3 F1 vs threshold (iforest, drain)")
                ax[1].legend()
            fig.tight_layout()
            fig.savefig(fig_dir / f"{ds}.{mode}.png", dpi=130)
            plt.close(fig)


def main():
    cells = load_cells()
    if not cells:
        raise SystemExit("no cells found; run logsentinel.experiments.offline first")
    L = long_rows(cells)
    L.to_csv(OUT / "tables.csv", index=False)
    parts = [f"## {name}\n\n{md(t)}\n" for name, t in tables(L).items()]
    (OUT / "table.md").write_text("# Offline results (test split, mean ± std over seeds)\n\n"
        "> **Read F1 next to `prevalence`.** A detector that flags everything gets recall 1.0, precision = prevalence and\n"
        "> F1 = 2p/(1+p) (e.g. 0.768 at 0.623). Rows at that level (Thunderbird chronological, BGL random tuned_val) are\n"
        "> degenerate; judge them by ROC-AUC / PR-AUC vs prevalence instead.\n\n" + "\n".join(parts))
    figures(cells)
    print(f"wrote {OUT/'table.md'}, {OUT/'tables.csv'}, figures/ ({len(cells)} cells)")


if __name__ == "__main__":
    main()
