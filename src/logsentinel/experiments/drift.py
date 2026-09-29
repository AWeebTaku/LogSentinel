"""E8: concept drift. A static model versus retraining, over 10 chronological chunks of the HDFS test split.

    python -m logsentinel.experiments.drift            # results/drift/{results.json,tables.md,figures}

Drift is simulated as a software change that REWORDS the most common log messages from chunk DRIFT_AT onward (the message
text gets a new suffix, so a static model sees message types it never trained on). Because sessions are represented by
counts over a small vocabulary of masked messages, the rewording is applied to that vocabulary: cheap and exactly
reproducible. Conditions: none (control), moderate (top 2 message types, 36% of lines), severe (top 4, 72% of lines).

Arms (all use Drain + PCA, the model of the streaming path):
  static_tuned      trained once on the training split, threshold tuned on validation (uses labels)
  static_p99        same detector, unsupervised threshold (99th percentile of normal training scores)
  retrain_periodic  refit on the previous two chunks (unlabeled, contaminated by anomalies) at every chunk, threshold p99
  retrain_triggered refit only when the share of lines the model has never seen exceeds 5% (an unlabeled drift signal)
  retrain_oracle    like periodic (same threshold rule) but fitted with the labeled anomalies removed from the window
                    (isolates the effect of contamination; not deployable)
Chunk anomaly rates vary naturally (0.9% to 5.3%), so read every arm against its own no-drift control (the "penalty").
"""
import json
import time
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfTransformer

from ..common.config import ROOT
from ..features.counts import load_or_build
from ..models import thresholds as th
from ..models.detectors import PCADetector
from ..parsing.parsers import ParserRuntime
from . import metrics as mt

OUT = ROOT / "results" / "drift"
CHUNKS, DRIFT_AT, WINDOW, TRIGGER_UNK = 10, 4, 2, 0.05
CONDITIONS = {"none": 0, "moderate": 2, "severe": 4}          # number of most common message types reworded
ARMS = ["static_tuned", "static_p99", "retrain_periodic", "retrain_triggered", "retrain_oracle"]
SUFFIX = " status=ok"


def rewrite(message: str) -> str:
    return message + SUFFIX


def build_drift(vocab: list[str], test_line_share: np.ndarray, k: int):
    """Vocabulary after drift and the maps old columns -> new columns before and after the drift.
    Returns (vocab2, P_pre, P_post, changed) where P_* are (V x V2) 0/1 matrices."""
    V = len(vocab)
    changed = list(np.argsort(-test_line_share, kind="stable")[:k])
    vocab2 = list(vocab) + [rewrite(vocab[i]) for i in changed]
    pre = sp.csr_matrix((np.ones(V, np.float32), (np.arange(V), np.arange(V))), shape=(V, len(vocab2)))
    target = np.arange(V)
    for j, i in enumerate(changed):
        target[i] = V + j
    post = sp.csr_matrix((np.ones(V, np.float32), (np.arange(V), target)), shape=(V, len(vocab2)))
    return vocab2, pre, post, changed


@dataclass
class Model:
    rt: ParserRuntime
    M: sp.csr_matrix
    tf: TfidfTransformer
    det: PCADetector
    thr: float = 0.0
    fit_seconds: float = 0.0

    def counts(self, X: sp.csr_matrix) -> sp.csr_matrix:
        return (X @ self.M).tocsr()

    def score(self, X: sp.csr_matrix) -> np.ndarray:
        return self.det.score(self.tf.transform(self.counts(X)).tocsr().astype(np.float32))

    def unk_share(self, X: sp.csr_matrix) -> float:
        c = self.counts(X)
        total = float(c.sum())
        return float(c[:, 0].sum()) / total if total else 0.0


def fit_model(X: sp.csr_matrix, vocab2: list[str]) -> Model:
    """Fit Drain + tf-idf + PCA on the rows of X (sessions x vocab2 counts). No labels involved."""
    t0 = time.perf_counter()
    freq = np.asarray(X.sum(0)).ravel()
    rt = ParserRuntime("drain", vocab2, freq)
    cols = np.array([rt.column(s) for s in vocab2])
    M = sp.csr_matrix((np.ones(len(cols), np.float32), (np.arange(len(cols)), cols)), shape=(len(cols), rt.n_cols))
    tf = TfidfTransformer(sublinear_tf=True).fit((X @ M).tocsr())
    det = PCADetector(seed=0).fit(tf.transform((X @ M).tocsr()).tocsr().astype(np.float32))
    m = Model(rt, M, tf, det)
    m.fit_seconds = time.perf_counter() - t0
    return m


def p99_threshold(m: Model, X: sp.csr_matrix) -> float:
    return th.percentile(m.score(X), 99)


def chunk_metrics(m: Model, thr: float, X: sp.csr_matrix, y: np.ndarray) -> dict:
    s = m.score(X)
    r = mt.at_threshold(s, y, thr)
    neg = max(1, int((y == 0).sum()))
    return {"n": len(y), "anomalies": int(y.sum()), **mt.ranking(s, y), "threshold": thr, "precision": r["precision"],
            "recall": r["recall"], "f1": r["f1"], "fpr": r["fp"] / neg, "alert_rate": float((s >= thr).mean()),
            "unk_share": m.unk_share(X)}


def run_condition(cf, k: int, drift_at: int = DRIFT_AT, win: int = WINDOW) -> dict:
    te, tr, va = cf.rows("test"), cf.rows("train"), cf.rows("val")
    share = np.asarray(cf.X_mask[te].sum(0)).ravel()
    vocab2, P_pre, P_post, changed = build_drift(cf.vocab, share / share.sum(), k)
    Xtr, Xva, Xte = cf.X_mask[tr] @ P_pre, cf.X_mask[va] @ P_pre, cf.X_mask[te]
    ytr, yva, yte = cf.labels[tr], cf.labels[va], cf.labels[te]
    static = fit_model(Xtr[ytr == 0].tocsr(), vocab2)
    thr_tuned = th.tuned(static.score(Xva), yva.astype(int))
    thr_p99 = p99_threshold(static, Xtr[ytr == 0].tocsr())
    idx = np.array_split(np.arange(len(te)), CHUNKS)
    X = [(Xte[i] @ (P_post if c >= drift_at else P_pre)).tocsr() for c, i in enumerate(idx)]
    y = [yte[i].astype(int) for i in idx]

    def window(c: int, drop_anomalies: bool) -> sp.csr_matrix:
        parts = [X[j][y[j] == 0] if drop_anomalies else X[j] for j in range(max(0, c - win), c)]
        return sp.vstack(parts).tocsr()

    out = {a: [] for a in ARMS}
    triggered_model, triggered_thr, triggers, fit_times = static, thr_p99, [], {"periodic": [], "triggered": [], "oracle": []}
    for c in range(CHUNKS):
        out["static_tuned"].append(chunk_metrics(static, thr_tuned, X[c], y[c]))
        out["static_p99"].append(chunk_metrics(static, thr_p99, X[c], y[c]))
        if c == 0:
            for a in ("retrain_periodic", "retrain_oracle"):
                out[a].append(chunk_metrics(static, thr_p99, X[c], y[c]))
        else:
            w_all = window(c, False)
            for a, drop, key in (("retrain_periodic", False, "periodic"), ("retrain_oracle", True, "oracle")):
                w = window(c, drop)
                m = fit_model(w, vocab2)
                fit_times[key].append(m.fit_seconds)
                # same threshold rule for both (p99 of the UNFILTERED window) so the arms differ only in training-data purity
                out[a].append(chunk_metrics(m, p99_threshold(m, w_all), X[c], y[c]))
            if triggered_model.unk_share(X[c - 1]) > TRIGGER_UNK:      # unlabeled drift signal from the previous chunk
                w = window(c, False)
                triggered_model = fit_model(w, vocab2)
                triggered_thr = p99_threshold(triggered_model, w)
                fit_times["triggered"].append(triggered_model.fit_seconds)
                triggers.append(c)
        out["retrain_triggered"].append(chunk_metrics(triggered_model, triggered_thr, X[c], y[c]))
    return {"arms": out, "triggers": triggers, "changed_templates": [vocab2[i] for i in changed], "vocab2": len(vocab2),
            "fit_seconds": {k2: (float(np.mean(v)) if v else None) for k2, v in fit_times.items()}}


def penalty(drifted: dict, control: dict, arm: str, drift_at: int = DRIFT_AT, key: str = "f1") -> list[float]:
    """Per post-drift chunk: metric with drift minus the same arm's no-drift control."""
    return [drifted["arms"][arm][c][key] - control["arms"][arm][c][key] for c in range(drift_at, CHUNKS)]


def tables(res: dict) -> str:
    rows = []
    for cond in ("moderate", "severe"):
        for arm in ARMS:
            post = res[cond]["arms"][arm][DRIFT_AT:]
            pen = penalty(res[cond], res["none"], arm)
            rows.append([cond, arm, f"{np.mean([p['f1'] for p in post]):.3f}", f"{np.mean(pen):+.3f}", f"{pen[0]:+.3f}",
                         f"{np.mean(penalty(res[cond], res['none'], arm, key='recall')):+.3f}",
                         f"{np.mean([p['fpr'] for p in post]) * 100:.2f}%", f"{np.mean([p['pr_auc'] for p in post]):.3f}"])
    head = ["Drift", "Arm", "Mean F1 (post-drift chunks)", "F1 penalty vs no-drift control", "Penalty in the first drifted chunk",
            "Recall penalty", "False-positive rate", "Mean PR-AUC"]
    md = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"] + ["| " + " | ".join(r) + " |" for r in rows]
    ctrl = [f"| {a} | {np.mean([p['f1'] for p in res['none']['arms'][a][DRIFT_AT:]]):.3f} | "
            f"{np.mean([p['fpr'] for p in res['none']['arms'][a][DRIFT_AT:]]) * 100:.2f}% |" for a in ARMS]
    trig = "\n".join(f"- {c}: retrained at chunks {res[c]['triggers'] or 'never'}" for c in ("none", "moderate", "severe"))
    fit = res["moderate"]["fit_seconds"]
    per_chunk = ["| Arm | " + " | ".join(f"c{c}" for c in range(CHUNKS)) + " |", "|---|" + "---|" * CHUNKS]
    for arm in ARMS:
        per_chunk.append(f"| {arm} | " + " | ".join(f"{p['f1']:.2f}" for p in res["severe"]["arms"][arm]) + " |")
    per_chunk.append("| (anomaly rate) | " + " | ".join(f"{100 * p['anomalies'] / p['n']:.1f}%" for p in res["severe"]["arms"]["static_p99"]) + " |")
    return ("## Post-drift chunks (4 to 9), mean over chunks\n\n" + "\n".join(md)
            + "\n\n## No-drift control (same chunks)\n\n| Arm | Mean F1 | False-positive rate |\n|---|---|---|\n" + "\n".join(ctrl)
            + "\n\n## F1 per chunk, severe drift (drift starts at chunk 4)\n\n" + "\n".join(per_chunk)
            + f"\n\n## Triggered retraining (unseen-line share above {TRIGGER_UNK:.0%})\n\n{trig}\n\n"
            f"Retrain cost (fit on about 34k sessions): periodic {fit['periodic']:.1f} s per fit, "
            f"triggered {'n/a' if fit['triggered'] is None else f'{fit['triggered']:.1f} s'}.\n")


def sensitivity(cf) -> tuple[str, list]:
    """Severe drift at different drift points and retraining window sizes; penalty vs a control with the same window."""
    rows, raw = [], []
    for win in (1, 2, 3):
        control = run_condition(cf, 0, DRIFT_AT, win)
        for at in (3, 4, 5, 6):
            d = run_condition(cf, CONDITIONS["severe"], at, win)
            pen = {a: float(np.mean(penalty(d, control, a, at))) for a in ARMS}
            raw.append({"window": win, "drift_at": at, "penalty": pen, "triggers": d["triggers"]})
            rows.append([f"{win}", f"{at}", *[f"{pen[a]:+.3f}" for a in ARMS], str(d["triggers"] or "never")])
    head = ["Window (chunks)", "Drift starts at chunk", *[f"{a} penalty" for a in ARMS], "Triggered at chunks"]
    md = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"] + ["| " + " | ".join(r) + " |" for r in rows]
    return ("## Sensitivity (severe drift): mean F1 penalty over post-drift chunks\n\nEach row is a separate run; the penalty is "
            "against a no-drift control with the same window. Closer to zero is better.\n\n" + "\n".join(md) + "\n"), raw


def figure(res: dict) -> None:
    fig, ax = plt.subplots(2, 3, figsize=(14, 7), sharex=True)
    for j, cond in enumerate(("none", "moderate", "severe")):
        for arm in ARMS:
            ax[0, j].plot(range(CHUNKS), [p["f1"] for p in res[cond]["arms"][arm]], marker="o", ms=3, label=arm)
        ax[1, j].plot(range(CHUNKS), [p["unk_share"] * 100 for p in res[cond]["arms"]["static_p99"]], "k-o", ms=3, label="static model")
        ax[1, j].plot(range(CHUNKS), [p["unk_share"] * 100 for p in res[cond]["arms"]["retrain_triggered"]], "r--o", ms=3, label="triggered arm's model")
        ax[1, j].axhline(TRIGGER_UNK * 100, color="grey", ls=":", label="retrain trigger")
        for a in (ax[0, j], ax[1, j]):
            a.axvline(DRIFT_AT - 0.5, color="grey", ls="--", lw=1)
            a.grid(alpha=.3)
        ax[0, j].set(title=f"drift: {cond}", ylabel="F1 per chunk")
        ax[1, j].set(xlabel="chunk (drift starts at chunk 4)", ylabel="lines never seen by the model (%)")
    ax[0, 0].legend(fontsize=7)
    ax[1, 0].legend(fontsize=7)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / "figures" / "e8_drift.png", dpi=130)
    plt.close(fig)


def main() -> None:
    cf = load_or_build("hdfs", "chronological")
    res = {}
    for cond, k in CONDITIONS.items():
        t0 = time.time()
        res[cond] = run_condition(cf, k)
        print(f"{cond}: done in {time.time() - t0:.0f} s; retrained at {res[cond]['triggers']}", flush=True)
    sens_md, sens_raw = sensitivity(cf)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"main": res, "sensitivity": sens_raw}, default=float))
    md = f"# E8 Concept drift\n\n{__doc__.split('Arms', 1)[0].split(chr(10) + chr(10), 1)[1]}\n{tables(res)}\n{sens_md}"
    (OUT / "tables.md").write_text(md)
    figure(res)
    print(tables(res))
    print(sens_md)


if __name__ == "__main__":
    main()
