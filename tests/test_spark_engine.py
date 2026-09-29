import numpy as np
import pytest

from logsentinel.features.sequences import from_sessions
from logsentinel.models.bundle import Scorer, train_bundle
from logsentinel.models.early import attach_early
from logsentinel.stream import spark_engine as se


@pytest.fixture
def bundle_dir(tiny_cf_short, tmp_path):
    cf, sessions = tiny_cf_short
    b = train_bundle(cf, "hdfs", "drain", "pca")
    b = attach_early(b, from_sessions(sessions, Scorer(b)), age_s=3, model="ae", gate=10)
    b.save(tmp_path / "bundle")
    se._W.clear()
    yield tmp_path / "bundle", b
    se._W.clear()


def test_numpy_scoring_matches_the_sklearn_path(bundle_dir):
    """The Spark arm scores each session with NumPy; that must reproduce the Python engine's scores."""
    path, b = bundle_dir
    se._load(str(path))
    sc = Scorer(b)
    rng = np.random.default_rng(0)
    from collections import Counter
    for _ in range(50):
        counts = rng.integers(0, 8, size=sc.n_cols).astype(np.float64)
        counts[rng.integers(0, sc.n_cols)] += 1                       # never an all-zero vector
        c = Counter({i: int(v) for i, v in enumerate(counts) if v})
        assert se.score_session(counts) == pytest.approx(float(sc.score_counts([c])[0]), abs=1e-5)
        assert se.score_snapshot(counts) == pytest.approx(float(sc.score_snapshots([c])[0]), abs=1e-5)


def test_zero_vector_is_safe():
    assert np.all(se.tfidf_vec(np.zeros(4), np.ones(4)) == 0.0)


def test_log_time_expression_matches_the_python_definition():
    from logsentinel.stream.wire import hdfs_log_time
    line = "081110 235959 12 INFO x"
    y, m, d = int(line[0:2]), int(line[2:4]), int(line[4:6])
    sql = (d + 31 * m + 372 * y) * 86400 + int(line[7:9]) * 3600 + int(line[9:11]) * 60 + int(line[11:13])
    assert sql == hdfs_log_time(line)                                 # same arithmetic the Spark expression uses
