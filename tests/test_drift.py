import numpy as np
import scipy.sparse as sp

from logsentinel.experiments.drift import CHUNKS, DRIFT_AT, build_drift, fit_model, rewrite

VOCAB = ["conn from <*> ok", "disk <*> full warning now", "block <*> replicated to <*> nodes", "user <*> logged in today"]


def test_build_drift_rewords_the_most_common_templates_and_preserves_counts():
    share = np.array([0.5, 0.3, 0.15, 0.05])
    vocab2, pre, post, changed = build_drift(VOCAB, share, k=2)
    assert changed == [0, 1] and len(vocab2) == 6
    assert vocab2[4] == rewrite(VOCAB[0]) and vocab2[5] == rewrite(VOCAB[1])
    X = sp.csr_matrix(np.array([[3.0, 2.0, 1.0, 4.0]]))
    a, b = (X @ pre).toarray()[0], (X @ post).toarray()[0]
    assert a.tolist() == [3, 2, 1, 4, 0, 0]                        # before the drift: original columns
    assert b.tolist() == [0, 0, 1, 4, 3, 2]                        # after: the two common messages moved to their new text
    assert a.sum() == b.sum() == X.sum()                           # drift moves counts, never creates or drops lines
    assert build_drift(VOCAB, share, k=0)[3] == []                 # control condition: nothing changes


def test_unseen_line_share_flags_drift_and_retraining_removes_it():
    rng = np.random.default_rng(0)
    share = np.array([0.5, 0.3, 0.15, 0.05])
    vocab2, pre, post, _ = build_drift(VOCAB, share, k=2)
    base = sp.csr_matrix(rng.integers(1, 6, size=(400, 4)).astype(np.float32))
    static = fit_model((base @ pre).tocsr(), vocab2)
    assert static.unk_share((base @ pre).tocsr()) == 0.0           # nothing unseen before the drift
    drifted = (base @ post).tocsr()
    assert static.unk_share(drifted) > 0.4                          # rewording sends most lines to the <UNK> column
    refit = fit_model(drifted, vocab2)                              # retraining on post-drift data learns the new wording
    assert refit.unk_share(drifted) == 0.0
    assert refit.fit_seconds > 0


def test_experiment_layout():
    assert 0 < DRIFT_AT < CHUNKS
