"""Train the age check (EarlyCheck) for a bundle from cached per-line sequences.

Choice of (age, model) is made offline by experiments/early.py with a validation-only rule; the threshold
here maximizes the F1 of the UNION rule (incremental alert OR age check) on the validation split.
"""
import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfTransformer

from ..experiments.early import incremental_alert_times, prf, snapshot_counts
from ..features.sequences import Seq
from .bundle import Bundle, EarlyCheck
from .detectors import MODELS


def attach_early(bundle: Bundle, seqs: list[Seq], age_s: int, model: str, gate: int = 13, seed: int = 0) -> Bundle:
    d = bundle.parser.n_cols
    tr = [s for s in seqs if s.split == "train" and s.label == 0]
    val = [s for s in seqs if s.split == "val"]
    C = snapshot_counts(tr, age_s, d)
    tf = TfidfTransformer(sublinear_tf=True).fit(sp.csr_matrix(C))
    det = MODELS[model](seed=seed).fit(tf.transform(sp.csr_matrix(C)).tocsr().astype(np.float32))
    sv = det.score(tf.transform(sp.csr_matrix(snapshot_counts(val, age_s, d))).tocsr().astype(np.float32))
    yv = np.array([s.label for s in val])
    inc = np.isfinite(incremental_alert_times(bundle, val, gate))
    cand = np.unique(sv)
    cand = cand[:: max(1, len(cand) // 400)]
    f1 = [prf(inc | (sv >= t), yv)["f1"] for t in cand]
    thr = float(cand[int(np.argmax(f1))])
    bundle.early = EarlyCheck(age_s, tf, det, thr, model)
    bundle.meta |= {"early": {"age_s": age_s, "model": model, "threshold": thr, "val_union_f1": float(max(f1)),
                              "gate": gate}}
    return bundle
