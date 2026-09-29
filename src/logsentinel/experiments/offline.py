"""Offline detection experiments (E1 detection quality, E2 parser ablation, E3 threshold strategy).

One "cell" = (dataset, split mode, parser, model), run for several seeds, written to
results/offline/cells/<dataset>.<mode>.<parser>.<model>.json. `report.py` turns cells into tables/figures.

    python -m logsentinel.experiments.offline --datasets bgl --modes chronological --models iforest pca
"""
import argparse
import json
import time

import numpy as np
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.metrics import precision_recall_curve

from ..common.config import ROOT
from ..common.env import capture_env
from ..features.counts import CountFeatures, load_or_build
from ..models import thresholds as th
from ..models.detectors import MODELS
from ..parsing.parsers import drain_map, regex_map
from . import metrics as mt

OUT = ROOT / "results" / "offline"
MAX_EVENTS = 5000
TRAIN_SCORE_ROWS = 50_000  # subsample of train used to derive percentile / 3-sigma thresholds


def build_matrix(cf: CountFeatures, parser: str):
    """Sparse TF-IDF matrix for all sessions under one parser arm; idf fitted on train only."""
    if parser == "raw":
        X = cf.X_raw
    else:
        freq = np.asarray(cf.X_mask[cf.rows("train")].sum(0)).ravel()
        M, _ = (regex_map if parser == "regex" else drain_map)(cf.vocab, freq, **(
            {"max_events": MAX_EVENTS} if parser == "regex" else {}))
        X = (cf.X_mask @ M).tocsr()
    tf = TfidfTransformer(sublinear_tf=True).fit(X[cf.rows("train")])
    return tf.transform(X).tocsr().astype(np.float32)


def _curve(scores, y, n=200):
    p, r, t = precision_recall_curve(y, scores)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    idx = np.unique(np.linspace(0, len(t) - 1, min(n, len(t))).astype(int))
    return {"t": t[idx].tolist(), "f1": f1[idx].tolist(), "p": p[:-1][idx].tolist(), "r": r[:-1][idx].tolist()}


def run_cell(cf: CountFeatures, X, model_name: str, seeds: list[int]) -> dict:
    tr, va, te = cf.rows("train"), cf.rows("val"), cf.rows("test")
    yv, yt = cf.labels[va].astype(int), cf.labels[te].astype(int)
    rng = np.random.default_rng(0)
    tr_sub = np.sort(rng.choice(tr, min(TRAIN_SCORE_ROWS, len(tr)), replace=False))
    runs = []
    for seed in seeds:
        m = MODELS[model_name](seed=seed)
        t0 = time.perf_counter()
        m.fit(X[tr])
        fit_s = time.perf_counter() - t0
        s_tr = m.score(X[tr_sub])
        s_va = m.score(X[va])
        s_te, score_s = m.timed_score(X[te])
        thr = {
            "percentile99": th.percentile(s_tr, 99),
            "three_sigma": th.three_sigma(s_tr),
            "tuned_val": th.tuned(s_va, yv),
        }
        run = {
            "seed": seed, "fit_s": fit_s, "score_ms_per_session": 1000 * score_s / len(te),
            **mt.ranking(s_te, yt),
            "thresholds": {k: mt.at_threshold(s_te, yt, v) for k, v in thr.items()},
            "oracle_test": mt.best_f1(s_te, yt),
        }
        if seed == seeds[0]:
            run["curve"] = _curve(s_te, yt)
        runs.append(run)
    return {"n_features": int(X.shape[1]), "n_train": len(tr), "n_val": len(va), "n_test": len(te),
            "test_anomalies": int(yt.sum()), "runs": runs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="*", default=["hdfs", "bgl", "thunderbird"])
    ap.add_argument("--modes", nargs="*", default=["chronological", "random"])
    ap.add_argument("--parsers", nargs="*", default=["raw", "regex", "drain"])
    ap.add_argument("--models", nargs="*", default=list(MODELS))
    ap.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    (OUT / "cells").mkdir(parents=True, exist_ok=True)
    (OUT / "env.json").write_text(json.dumps(capture_env(), indent=2))
    for ds in a.datasets:
        for mode in a.modes:
            cf = load_or_build(ds, mode)
            for parser in a.parsers:
                X = None
                for model in a.models:
                    path = OUT / "cells" / f"{ds}.{mode}.{parser}.{model}.json"
                    if path.exists() and not a.force:
                        continue
                    if X is None:
                        t0 = time.perf_counter()
                        X = build_matrix(cf, parser)
                        print(f"[{ds}.{mode}] parser={parser}: {X.shape[1]} features "
                              f"({time.perf_counter() - t0:.0f}s)", flush=True)
                    t0 = time.perf_counter()
                    res = run_cell(cf, X, model, a.seeds) | {
                        "dataset": ds, "mode": mode, "parser": parser, "model": model}
                    path.write_text(json.dumps(res))
                    r0 = res["runs"][0]
                    print(f"  {model:8s} auc={r0['roc_auc']:.3f} pr_auc={r0['pr_auc']:.3f} "
                          f"f1(val-tuned)={r0['thresholds']['tuned_val']['f1']:.3f} "
                          f"({time.perf_counter() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
