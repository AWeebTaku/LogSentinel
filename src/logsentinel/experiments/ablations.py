"""Ablations: which design choices matter? (HDFS and BGL, chronological split, tuned-on-validation threshold, test metrics)

    python -m logsentinel.experiments.ablations         # results/ablations/{results.json,tables.md}

A1 Drain similarity threshold x tree depth (PCA detector)     A2 feature weighting (Drain + PCA)
A3 PCA variance kept (Drain, tf-idf)                           A4 autoencoder bottleneck size (Drain, tf-idf, 3 seeds)
Every row: PR-AUC, ROC-AUC and F1/precision/recall at the threshold tuned on the validation split.
"""
import json
import time

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfTransformer

from ..common.config import ROOT
from ..features.counts import load_or_build
from ..models import thresholds as th
from ..models.detectors import AEDetector, PCADetector
from ..parsing.parsers import drain_map
from . import metrics as mt

OUT = ROOT / "results" / "ablations"
DATASETS = ["hdfs", "bgl"]


def features(cf, sim_th: float = 0.4, depth: int = 4, weighting: str = "tfidf_sublinear"):
    freq = np.asarray(cf.X_mask[cf.rows("train")].sum(0)).ravel()
    M, names = drain_map(cf.vocab, freq, sim_th=sim_th, depth=depth)
    X = (cf.X_mask @ M).tocsr()
    tr = cf.rows("train")
    if weighting == "binary":
        X = (X > 0).astype(np.float32)
    elif weighting in ("tfidf_sublinear", "tfidf"):
        X = TfidfTransformer(sublinear_tf=(weighting == "tfidf_sublinear")).fit(X[tr]).transform(X)
    elif weighting != "counts":
        raise ValueError(weighting)
    return sp.csr_matrix(X, dtype=np.float32), len(names)


def evaluate(cf, X, det) -> dict:
    tr, va, te = cf.rows("train"), cf.rows("val"), cf.rows("test")
    det.fit(X[tr])
    yv, yt = cf.labels[va].astype(int), cf.labels[te].astype(int)
    sv, st = det.score(X[va]), det.score(X[te])
    r = mt.at_threshold(st, yt, th.tuned(sv, yv))
    return {**mt.ranking(st, yt), "f1": r["f1"], "precision": r["precision"], "recall": r["recall"],
            "val_pr_auc": mt.ranking(sv, yv)["pr_auc"]}


def med(rows: list[dict], key: str) -> float:
    return float(np.median([r[key] for r in rows]))


def run() -> dict:
    res: dict = {}
    for ds in DATASETS:
        cf = load_or_build(ds, "chronological")
        t0 = time.time()
        res[ds] = {"prevalence": float(cf.labels[cf.rows("test")].mean()), "A1": [], "A2": [], "A3": [], "A4": []}
        for sim in (0.3, 0.4, 0.5, 0.6):
            for depth in (3, 4, 5):
                X, n = features(cf, sim, depth)
                res[ds]["A1"].append({"sim_th": sim, "depth": depth, "templates": n, **evaluate(cf, X, PCADetector(seed=0))})
        for w in ("tfidf_sublinear", "tfidf", "counts", "binary"):
            X, n = features(cf, weighting=w)
            res[ds]["A2"].append({"weighting": w, **evaluate(cf, X, PCADetector(seed=0))})
        X, n = features(cf)
        for var in (0.90, 0.95, 0.99, 0.999):
            res[ds]["A3"].append({"variance": var, **evaluate(cf, X, PCADetector(variance=var, seed=0))})
        for b in (4, 8, 16, 32):
            runs = [evaluate(cf, X, AEDetector(bottleneck=b, seed=s)) for s in range(3)]
            res[ds]["A4"].append({"bottleneck": b, **{k: med(runs, k) for k in ("pr_auc", "roc_auc", "f1", "precision", "recall", "val_pr_auc")},
                                  "f1_range": [min(r["f1"] for r in runs), max(r["f1"] for r in runs)]})
        print(f"{ds}: {time.time() - t0:.0f} s", flush=True)
    return res


def md_rows(rows: list[dict], keys: list[str]) -> list[str]:
    out = ["| " + " | ".join(keys + ["Validation PR-AUC", "Test PR-AUC", "Test ROC-AUC", "Test F1", "Test precision", "Test recall"]) + " |",
           "|" + "---|" * (len(keys) + 6)]
    for r in rows:
        out.append("| " + " | ".join(str(r[k]) for k in keys) + f" | {r['val_pr_auc']:.3f} | {r['pr_auc']:.3f} | {r['roc_auc']:.3f} | "
                   f"{r['f1']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} |")
    return out


def selected(rows: list[dict], key: str, default) -> str:
    """The setting a practitioner would pick: highest VALIDATION PR-AUC (test is only looked at afterwards)."""
    best = max(rows, key=lambda r: r["val_pr_auc"])
    base = next((r for r in rows if r[key] == default), None)
    text = f"Selected on validation PR-AUC: **{key} = {best[key]}** (test PR-AUC {best['pr_auc']:.3f}, F1 {best['f1']:.3f})"
    if base is not None and base is not best:
        text += f"; the current default {default} gives test PR-AUC {base['pr_auc']:.3f}, F1 {base['f1']:.3f}"
    return text + ".\n"


def tables(res: dict) -> str:
    parts = ["# Ablations\n", __doc__.split("Every row")[0].split("\n\n", 1)[1]]
    for ds, d in res.items():
        title = (f"\n## {ds.upper()} (test prevalence {100 * d['prevalence']:.1f}%; a detector that flags everything gets "
                 f"F1 {2 * d['prevalence'] / (1 + d['prevalence']):.3f})\n")
        parts += [title, "### A1 Drain similarity threshold x depth\n",
                  *md_rows(d["A1"], ["sim_th", "depth", "templates"]), "\n### A2 Feature weighting\n", *md_rows(d["A2"], ["weighting"]),
                  "\n" + selected(d["A2"], "weighting", "tfidf_sublinear"),
                  "\n### A3 PCA variance kept\n", *md_rows(d["A3"], ["variance"]), "\n" + selected(d["A3"], "variance", 0.95),
                  "\n### A4 Autoencoder bottleneck (median of 3 seeds)\n", *md_rows(d["A4"], ["bottleneck"]),
                  "\n" + selected(d["A4"], "bottleneck", 16)]
    return "\n".join(parts) + "\n"


def main() -> None:
    res = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res))
    (OUT / "tables.md").write_text(tables(res))
    print(tables(res))


if __name__ == "__main__":
    main()
