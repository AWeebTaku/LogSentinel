"""Unsupervised detectors behind one interface: fit(X_train) / score(X) -> higher = more anomalous.

X is a (sessions x events) sparse TF-IDF matrix. All three are trained on normal sessions only.
Each is picklable (save/load) so the streaming engines in later weeks load the same object.
"""
import time
from pathlib import Path

import joblib
import numpy as np
import scipy.sparse as sp
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPRegressor

CHUNK = 20_000


def _dense_chunks(X: sp.csr_matrix, chunk: int = CHUNK):
    for i in range(0, X.shape[0], chunk):
        yield i, X[i : i + chunk].toarray().astype(np.float32, copy=False)


class Detector:
    name = "base"

    def fit(self, X: sp.csr_matrix) -> "Detector":
        raise NotImplementedError

    def score(self, X: sp.csr_matrix) -> np.ndarray:
        raise NotImplementedError

    def save(self, path: Path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "Detector":
        return joblib.load(path)

    def timed_score(self, X) -> tuple[np.ndarray, float]:
        t = time.perf_counter()
        s = self.score(X)
        return s, time.perf_counter() - t


class IForestDetector(Detector):
    name = "iforest"

    def __init__(self, n_estimators: int = 200, seed: int = 42):
        self.m = IsolationForest(n_estimators=n_estimators, random_state=seed, n_jobs=-1)

    def fit(self, X):
        self.m.fit(X)
        return self

    def score(self, X):
        return -self.m.score_samples(X)


class PCADetector(Detector):
    """Squared prediction error outside the principal subspace (Xu et al., SOSP 2009 style)."""

    name = "pca"

    def __init__(self, variance: float = 0.95, max_components: int = 64,
                 max_fit_rows: int = 20_000, seed: int = 42):
        self.variance, self.kmax, self.max_rows, self.seed = variance, max_components, max_fit_rows, seed

    def fit(self, X):
        rng = np.random.default_rng(self.seed)
        rows = np.sort(rng.choice(X.shape[0], min(self.max_rows, X.shape[0]), replace=False))
        D = X[rows].toarray().astype(np.float32)
        k = min(self.kmax, *D.shape)
        p = PCA(n_components=k, svd_solver="randomized", random_state=self.seed).fit(D)
        cum = np.cumsum(p.explained_variance_ratio_)
        self.k = int(min(np.searchsorted(cum, self.variance) + 1, k))
        self.mean = p.mean_.astype(np.float32)
        self.V = p.components_[: self.k].astype(np.float32)  # orthonormal rows
        return self

    def score(self, X):
        out = np.empty(X.shape[0], dtype=np.float64)
        for i, D in _dense_chunks(X):
            C = D - self.mean
            out[i : i + len(D)] = (C * C).sum(1) - ((C @ self.V.T) ** 2).sum(1)
        return np.maximum(out, 0.0)


class AEDetector(Detector):
    """MLP autoencoder (sklearn MLPRegressor, X -> X) scored by reconstruction MSE.
    # ponytail: sklearn MLP on <=20k rows, 25 epochs; move to PyTorch if a deeper/sequence model is needed.
    """

    name = "ae"

    def __init__(self, bottleneck: int = 16, max_fit_rows: int = 20_000, max_iter: int = 25, seed: int = 42):
        self.b, self.max_rows, self.max_iter, self.seed = bottleneck, max_fit_rows, max_iter, seed

    def fit(self, X):
        rng = np.random.default_rng(self.seed)
        rows = np.sort(rng.choice(X.shape[0], min(self.max_rows, X.shape[0]), replace=False))
        D = X[rows].toarray().astype(np.float32)
        h = int(min(128, max(2 * self.b, D.shape[1] // 2)))
        self.m = MLPRegressor(hidden_layer_sizes=(h, self.b, h), activation="relu", max_iter=self.max_iter,
                              random_state=self.seed, early_stopping=False).fit(D, D)
        return self

    def score(self, X):
        out = np.empty(X.shape[0], dtype=np.float64)
        for i, D in _dense_chunks(X):
            out[i : i + len(D)] = ((self.m.predict(D) - D) ** 2).mean(1)
        return out


MODELS = {"iforest": IForestDetector, "pca": PCADetector, "ae": AEDetector}
