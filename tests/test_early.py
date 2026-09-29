import numpy as np

from logsentinel.features.sequences import from_sessions
from logsentinel.models.bundle import Scorer, train_bundle
from logsentinel.models.early import attach_early
from logsentinel.stream.sessionizer import Sessionizer


def test_sessionizer_age_deadline_and_snapshot():
    sz = Sessionizer(lambda line: {"x": 1, "y": 2, "z": 3}[line], age_s=30)
    sz.add("a", "x", 1, 1, log_t=100)
    sz.add("b", "y", 2, 2, log_t=105)
    sz.add("a", "y", 3, 3, log_t=120)
    a = sz.add("a", "z", 4, 4, log_t=140)          # 40 s after the first line: counts, but not in the snapshot
    assert a.n == 3 and dict(a.counts) == {1: 1, 2: 1, 3: 1} and dict(a.snap) == {1: 1, 2: 1}
    assert sz.pop_due(129) == []                    # a's deadline is 130 (strictly after)
    assert [k for k, _ in sz.pop_due(131)] == ["a"]
    assert [k for k, _ in sz.pop_due(float("inf"))] == ["b"]
    assert sz.pop_due(float("inf")) == []


def test_age_check_flags_incomplete_sessions_and_spares_normal(tiny_cf_short):
    cf, sessions = tiny_cf_short
    b = train_bundle(cf, "hdfs", "drain", "pca")
    seqs = from_sessions(sessions, Scorer(b))
    b = attach_early(b, seqs, age_s=3, model="pca", gate=10)
    e = b.early
    assert e.age_s == 3 and b.meta["early"]["val_union_f1"] > 0.9
    sc = Scorer(b)
    test = [s for s in sessions if s.split == "test"]
    from collections import Counter
    snaps = []
    for s in test:
        c = Counter()
        for line in s.lines:
            if int(line[7:13]) - int(s.lines[0][7:13]) <= 3:     # same 3-second snapshot as training
                c[sc.line_col(line)] += 1
        snaps.append(c)
    flag = sc.score_snapshots(snaps) >= e.threshold
    y = np.array([s.label for s in test])
    short = np.array([len(s.lines) == 2 for s in test])
    assert flag[short].all()                        # every incomplete session is caught by the age check
    assert not flag[(y == 0)].any()                 # and no normal session is
