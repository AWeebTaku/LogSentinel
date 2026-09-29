import numpy as np
import scipy.sparse as sp
from sklearn.metrics import roc_auc_score

from logsentinel.experiments import metrics as mt
from logsentinel.models import thresholds as th
from logsentinel.models.detectors import MODELS, Detector


def _toy():
    rng = np.random.default_rng(0)
    normal = np.abs(rng.normal(0, 0.05, (600, 12))) + np.eye(12)[rng.integers(0, 3, 600)]
    anom = np.abs(rng.normal(0, 0.05, (60, 12))) + np.eye(12)[rng.integers(8, 12, 60)]
    return sp.csr_matrix(normal.astype(np.float32)), sp.csr_matrix(anom.astype(np.float32))


def test_all_detectors_rank_novel_events_higher_and_roundtrip(tmp_path):
    Xn, Xa = _toy()
    X = sp.vstack([Xn[:500], Xn[500:], Xa]).tocsr()
    y = np.r_[np.zeros(100), np.ones(60)]
    for name, cls in MODELS.items():
        m = cls(seed=0).fit(Xn[:500])
        s = m.score(sp.vstack([Xn[500:], Xa]).tocsr())
        assert roc_auc_score(y, s) > 0.8, name
        m.save(tmp_path / f"{name}.joblib")
        s2 = Detector.load(tmp_path / f"{name}.joblib").score(sp.vstack([Xn[500:], Xa]).tocsr())
        assert np.allclose(s, s2), name
    assert X.shape[0] == 660


def test_thresholds():
    s = np.arange(100, dtype=float)
    assert th.three_sigma(s) == s.mean() + 3 * s.std()
    assert th.percentile(s, 99) == np.percentile(s, 99)
    y = (s >= 90).astype(int)
    assert th.tuned(s, y) == 90.0
    assert th.tuned(s, np.zeros(100, int)) == float("inf")


def test_metrics_at_threshold():
    s = np.array([0.1, 0.2, 0.8, 0.9])
    y = np.array([0, 1, 0, 1])
    r = mt.at_threshold(s, y, 0.5)
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (1, 1, 1, 1)
    assert abs(r["f1"] - 0.5) < 1e-9
    assert mt.ranking(s, y)["roc_auc"] == 0.75
