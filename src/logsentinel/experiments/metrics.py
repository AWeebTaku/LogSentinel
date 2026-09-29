import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


def at_threshold(scores: np.ndarray, y: np.ndarray, thr: float) -> dict:
    pred = scores >= thr
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"threshold": float(thr), "precision": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def ranking(scores: np.ndarray, y: np.ndarray) -> dict:
    if y.min() == y.max():
        return {"roc_auc": float("nan"), "pr_auc": float("nan")}
    return {"roc_auc": float(roc_auc_score(y, scores)), "pr_auc": float(average_precision_score(y, scores))}


def best_f1(scores: np.ndarray, y: np.ndarray) -> dict:
    """Oracle: best achievable F1 on this very set (upper bound, for context only)."""
    if y.sum() == 0:
        return {"f1": 0.0, "threshold": float("inf")}
    p, r, t = precision_recall_curve(y, scores)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    i = int(np.argmax(f1))
    return {"f1": float(f1[i]), "threshold": float(t[i])}
