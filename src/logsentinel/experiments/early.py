"""Early-detection study (offline simulation of the online engine on cached per-line sequences).

Question: HDFS sessions never end, and 40% of anomalous test sessions are short/incomplete (2-4 lines), so a
gated incremental rule (alert once a session has >= m lines and its score crosses the threshold) never sees them.
Candidate fix: add an age-T check. When a session is T log-seconds old, score its snapshot with a detector
trained on age-T snapshots of NORMAL sessions. Alert = incremental rule OR age-T rule.

    python -m logsentinel.experiments.early --bundle models/hdfs-drain-pca
"""
import argparse
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfTransformer

from ..common.config import ROOT
from ..features.sequences import Seq, build
from ..models.bundle import Bundle
from ..models.detectors import MODELS
from . import metrics as mt

K_STEPS = 64  # exact per-line simulation for the first K lines; longer sessions are checked at their end


def _pad(seqs: list[Seq]):
    S = len(seqs)
    cols = np.full((S, K_STEPS), -1, np.int16)
    dt = np.zeros((S, K_STEPS), np.int32)
    for i, s in enumerate(seqs):
        k = min(K_STEPS, len(s.cols))
        cols[i, :k], dt[i, :k] = s.cols[:k], s.dt[:k]
    return cols, dt


def _score(bundle: Bundle, counts: np.ndarray) -> np.ndarray:
    X = bundle.tfidf.transform(sp.csr_matrix(counts)).tocsr().astype(np.float32)
    return bundle.detector.score(X)


def incremental_alert_times(bundle: Bundle, seqs: list[Seq], gate: int) -> np.ndarray:
    """Log-time offset (s) at which the gated incremental rule first fires; inf if never."""
    S, d = len(seqs), bundle.parser.n_cols
    cols, dt = _pad(seqs)
    n = np.array([len(s.cols) for s in seqs])
    counts = np.zeros((S, d), np.float32)
    fire = np.full(S, np.inf)
    for k in range(K_STEPS):
        idx = np.flatnonzero(cols[:, k] >= 0)
        if not len(idx):
            break
        counts[idx, cols[idx, k]] += 1
        if k + 1 >= gate:
            live = idx[np.isinf(fire[idx])]
            if len(live):
                hit = _score(bundle, counts[live]) >= bundle.threshold
                fire[live[hit]] = dt[live[hit], k]
    for i in np.flatnonzero((n > K_STEPS) & np.isinf(fire)):   # long tail: check once with all lines
        full = np.bincount(seqs[i].cols, minlength=d)[None].astype(np.float32)
        if _score(bundle, full)[0] >= bundle.threshold:
            fire[i] = seqs[i].dt[-1]
    return fire


def snapshot_counts(seqs: list[Seq], T: int, d: int) -> np.ndarray:
    return np.stack([np.bincount(s.cols[s.dt <= T], minlength=d) for s in seqs]).astype(np.float32)


def fit_snapshot(train: list[Seq], T: int, d: int, model: str = "pca", seed: int = 0):
    C = snapshot_counts([s for s in train if s.label == 0], T, d)
    tf = TfidfTransformer(sublinear_tf=True).fit(sp.csr_matrix(C))
    det = MODELS[model](seed=seed).fit(tf.transform(sp.csr_matrix(C)).tocsr().astype(np.float32))
    return lambda counts: det.score(tf.transform(sp.csr_matrix(counts)).tocsr().astype(np.float32))


def prf(flag: np.ndarray, y: np.ndarray) -> dict:
    tp, fp, fn = int((flag & (y == 1)).sum()), int((flag & (y == 0)).sum()), int((~flag & (y == 1)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, default=ROOT / "models/hdfs-drain-pca")
    ap.add_argument("--gate", type=int, default=13)
    ap.add_argument("--ages", type=int, nargs="*", default=[10, 30, 60, 120, 240, 420, 600])
    ap.add_argument("--models", nargs="*", default=["pca", "iforest", "ae"])
    a = ap.parse_args()
    bundle = Bundle.load(a.bundle)
    seqs = build(a.bundle)
    tr = [s for s in seqs if s.split == "train"]
    parts = {sp_: [s for s in seqs if s.split == sp_] for sp_ in ("val", "test")}
    d = bundle.parser.n_cols
    inc = {k: incremental_alert_times(bundle, v, a.gate) for k, v in parts.items()}
    y = {k: np.array([s.label for s in v]) for k, v in parts.items()}
    rows = []

    def report(name, flag, delay, yy):
        r = prf(flag, yy)
        det = flag & (yy == 1)
        r |= {"rule": name, "delay_p50_s": float(np.median(delay[det])) if det.any() else None,
              "delay_p95_s": float(np.percentile(delay[det], 95)) if det.any() else None}
        return r

    rows.append(report(f"incremental only (gate {a.gate})", np.isfinite(inc["test"]), inc["test"], y["test"]))

    def with_snapshot(name, snap_flag, T, extra=None):
        """Union with the incremental rule. Delay = earliest of (incremental fire, age-T check if it fired)."""
        delay = np.minimum(inc["test"], np.where(snap_flag, float(T), np.inf))
        rows.append(report(name, np.isfinite(delay), delay, y["test"]) | (extra or {}))

    for T in a.ages:
        # control: no model, "still under `gate` lines at age T" (the completion deadline)
        short = np.array([(s.dt <= T).sum() < a.gate for s in parts["test"]])
        with_snapshot(f"incremental OR (age {T}s and < {a.gate} lines)", short, T)
    for model in a.models:
        for T in a.ages:
            f = fit_snapshot(tr, T, d, model)
            sc = {k: f(snapshot_counts(v, T, d)) for k, v in parts.items()}
            cand = np.unique(sc["val"])
            cand = cand[:: max(1, len(cand) // 400)]
            f1s = [prf(np.isfinite(inc["val"]) | (sc["val"] >= t), y["val"])["f1"] for t in cand]
            thr = cand[int(np.argmax(f1s))]
            val_f1 = max(f1s)
            with_snapshot(f"incremental OR age-{T}s snapshot ({model})", sc["test"] >= thr, T,
                          {"thr": float(thr), "val_f1": float(val_f1), "model": model, "age": T})
    _, _, ref_val = None, None, None
    fv, yv = _final(bundle, parts["val"])
    ref_val = mt.at_threshold(fv, yv, bundle.threshold)["f1"]
    ok = [r for r in rows if "val_f1" in r and r["val_f1"] >= ref_val - 0.01]
    pick = min(ok, key=lambda r: (r["age"], -r["val_f1"])) if ok else None
    print(f"selection rule (validation only): shortest age whose val F1 >= final-model val F1 ({ref_val:.3f}) - 0.01")
    print("selected:", None if pick is None else f"{pick['model']} at age {pick['age']}s (val F1 {pick['val_f1']:.3f})")
    print(f"{'rule':44s} {'P':>6s} {'R':>6s} {'F1':>6s} {'FP':>6s} {'FN':>6s} {'delay p50/p95 (log s)':>22s}")
    for r in rows:
        dl = "-" if r["delay_p50_s"] is None else f"{r['delay_p50_s']:.0f}/{r['delay_p95_s']:.0f}"
        print(f"{r['rule']:44s} {r['precision']:6.3f} {r['recall']:6.3f} {r['f1']:6.3f} {r['fp']:6d} {r['fn']:6d} {dl:>22s}")
    out = ROOT / "results" / "early"
    out.mkdir(parents=True, exist_ok=True)
    (out / "age_snapshot.json").write_text(json.dumps({"rows": rows, "selected": pick, "ref_val_f1": ref_val}, indent=2))
    ref = mt.at_threshold(*_final(bundle, parts["test"]), bundle.threshold)
    print(f"reference, final full-session score (needs the whole lifetime): P/R/F1 = "
          f"{ref['precision']:.3f}/{ref['recall']:.3f}/{ref['f1']:.3f}")


def _final(bundle: Bundle, seqs: list[Seq]):
    C = np.stack([np.bincount(s.cols, minlength=bundle.parser.n_cols) for s in seqs]).astype(np.float32)
    return _score(bundle, C), np.array([s.label for s in seqs])


if __name__ == "__main__":
    main()
