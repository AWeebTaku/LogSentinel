"""Three ways to pick an alert threshold (E3). Scores: higher = more anomalous."""
import numpy as np
from sklearn.metrics import precision_recall_curve


def percentile(train_scores: np.ndarray, q: float = 99.0) -> float:
    return float(np.percentile(train_scores, q))


def three_sigma(train_scores: np.ndarray) -> float:
    """The paper's rule: mean + 3 std of scores on normal (training) data."""
    return float(train_scores.mean() + 3 * train_scores.std())


def tuned(val_scores: np.ndarray, val_y: np.ndarray) -> float:
    """Threshold maximizing F1 on the validation set (uses labels: an upper bound, not deployable as-is)."""
    if val_y.sum() == 0:
        return float("inf")
    p, r, t = precision_recall_curve(val_y, val_scores)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    return float(t[int(np.argmax(f1))])
