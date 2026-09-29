"""Deployable model bundle: parser runtime + tf-idf + detector + threshold, and the serve-time Scorer.

    python -m logsentinel.models.train --dataset hdfs --parser drain --model pca --out models/hdfs-drain-pca
"""
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfTransformer

from ..features.counts import CountFeatures
from ..parsing.content import content, mask
from ..parsing.parsers import ParserRuntime
from . import thresholds as th
from .detectors import MODELS, Detector


@dataclass
class EarlyCheck:
    """Age check: when a session is `age_s` log-seconds old, score its snapshot with this detector
    (trained on age-`age_s` snapshots of normal sessions). Alerts on sessions that stay incomplete."""
    age_s: int
    tfidf: TfidfTransformer
    detector: Detector
    threshold: float
    model: str = ""


@dataclass
class Bundle:
    dataset: str
    parser: ParserRuntime
    tfidf: TfidfTransformer
    detector: Detector
    threshold: float
    meta: dict = field(default_factory=dict)
    early: EarlyCheck | None = None

    def save(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, out / "bundle.joblib")
        (out / "meta.json").write_text(json.dumps(self.meta, indent=2))

    @staticmethod
    def load(path: Path) -> "Bundle":
        return joblib.load(Path(path) / "bundle.joblib")


def train_bundle(cf: CountFeatures, dataset: str, parser: str, model: str,
                 threshold_rule: str = "tuned_val", seed: int = 0) -> Bundle:
    """Fit on cf's train split. The feature space comes from train strings only (see ParserRuntime)."""
    tr, va = cf.rows("train"), cf.rows("val")
    freq = np.asarray(cf.X_mask[tr].sum(0)).ravel()
    rt = ParserRuntime(parser, cf.vocab, freq)
    cols = np.array([rt.column(s) for s in cf.vocab])
    M = sp.csr_matrix((np.ones(len(cols), np.float32), (np.arange(len(cols)), cols)),
                      shape=(len(cols), rt.n_cols))
    X = (cf.X_mask @ M).tocsr()
    tf = TfidfTransformer(sublinear_tf=True).fit(X[tr])
    Xt = tf.transform(X).tocsr().astype(np.float32)
    det = MODELS[model](seed=seed).fit(Xt[tr])
    s_tr, s_va = det.score(Xt[tr]), det.score(Xt[va])
    yv = cf.labels[va].astype(int)
    thr = {"percentile99": lambda: th.percentile(s_tr, 99), "three_sigma": lambda: th.three_sigma(s_tr),
           "tuned_val": lambda: th.tuned(s_va, yv)}[threshold_rule]()
    meta = {"dataset": dataset, "parser": parser, "model": model, "threshold_rule": threshold_rule,
            "threshold": float(thr), "n_features": rt.n_cols, "seed": seed, "n_train": len(tr)}
    return Bundle(dataset, rt, tf, det, float(thr), meta)


class Scorer:
    """Serve-time twin of the offline pipeline: line -> column, counts -> tf-idf -> score."""

    def __init__(self, bundle: Bundle):
        self.b = bundle
        self.dataset = bundle.dataset
        self.threshold = bundle.threshold
        self.n_cols = bundle.parser.n_cols
        self.early = getattr(bundle, "early", None)   # old pickles predate the field

    def line_col(self, line: str) -> int:
        return self.b.parser.column(mask(content(line, self.dataset)))

    def score_counts(self, counts: list[Counter]) -> np.ndarray:
        indptr, idx, dat = [0], [], []
        for c in counts:
            idx.extend(c.keys())
            dat.extend(c.values())
            indptr.append(len(idx))
        X = sp.csr_matrix((np.array(dat, np.float32), np.array(idx, np.int32), np.array(indptr)),
                          shape=(len(counts), self.n_cols))
        return self.b.detector.score(self.b.tfidf.transform(X).tocsr().astype(np.float32))


    def score_snapshots(self, counts: list[Counter]) -> np.ndarray:
        e = self.early
        indptr, idx, dat = [0], [], []
        for c in counts:
            idx.extend(c.keys())
            dat.extend(c.values())
            indptr.append(len(idx))
        X = sp.csr_matrix((np.array(dat, np.float32), np.array(idx, np.int32), np.array(indptr)),
                          shape=(len(counts), self.n_cols))
        return e.detector.score(e.tfidf.transform(X).tocsr().astype(np.float32))


def offline_scores(bundle: Bundle, cf: CountFeatures, split: str) -> tuple[np.ndarray, np.ndarray]:
    """Scores + labels for a split through the bundle's own feature space (reference for online runs)."""
    cols = np.array([bundle.parser.column(s) for s in cf.vocab])
    M = sp.csr_matrix((np.ones(len(cols), np.float32), (np.arange(len(cols)), cols)),
                      shape=(len(cols), bundle.parser.n_cols))
    rows = cf.rows(split)
    X = bundle.tfidf.transform((cf.X_mask[rows] @ M).tocsr()).tocsr().astype(np.float32)
    return bundle.detector.score(X), cf.labels[rows].astype(int)

