import itertools
import json
import socket
import subprocess
import sys
from collections import Counter

import numpy as np
import pytest
from synth import make_sessions

from logsentinel.models.bundle import Bundle, Scorer, offline_scores, train_bundle
from logsentinel.stream.sessionizer import Sessionizer
from logsentinel.stream.wire import hdfs_key


@pytest.mark.parametrize("parser", ["regex", "drain"])
def test_bundle_roundtrip_and_scorer_matches_offline(tiny_cf, tmp_path, parser):
    b = train_bundle(tiny_cf, "hdfs", parser, "pca")
    b.save(tmp_path / "b")
    b2 = Bundle.load(tmp_path / "b")                       # ParserRuntime rebuilt from its args
    assert b2.parser.n_cols == b.parser.n_cols and b2.threshold == b.threshold

    off, y = offline_scores(b2, tiny_cf, "test")
    sc = Scorer(b2)
    sessions = {s.id: s for s in make_sessions() if s.split == "test"}
    ids = [tiny_cf.ids[i] for i in tiny_cf.rows("test")]
    counts = []
    for sid in ids:
        c = Counter()
        for line in sessions[sid].lines:
            c[sc.line_col(line)] += 1
        counts.append(c)
    assert np.allclose(sc.score_counts(counts), off, atol=1e-6)      # serve == offline, by construction
    # and the detector actually separates the injected anomalies (novel ERROR line)
    assert off[y == 1].min() > off[y == 0].max() or (off[y == 1] >= b2.threshold).all()


def test_sessionizer_accumulates_per_key():
    sz = Sessionizer(lambda line: len(line) % 3)
    a = sz.add("k1", "aa", 1, 10)
    b = sz.add("k1", "bbb", 2, 20)
    sz.add("k2", "c", 3, 30)
    assert a is b and a.n == 2 and a.last_recv == 20 and a.last_send == 2
    assert sum(a.counts.values()) == 2 and set(sz.open) == {"k1", "k2"}


def test_hdfs_key_uses_first_block():
    assert hdfs_key("x blk_-12 y blk_5") == "blk_-12"
    assert hdfs_key("no block here") is None


def _broker_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 9092), timeout=1).close()
        return True
    except OSError:
        return False


@pytest.mark.e2e
@pytest.mark.skipif(not _broker_up(), reason="Kafka not running: scripts/kafka.sh start")
def test_end_to_end_through_kafka(tiny_cf_short, tmp_path):
    """Replay synthetic sessions through real Kafka into a real engine subprocess: alerts must be exactly
    the injected anomalies, and final scores must equal the offline scores."""
    from logsentinel.features.sequences import from_sessions
    from logsentinel.models.early import attach_early
    from logsentinel.stream.admin import ensure_topics
    from logsentinel.stream.producer import replay

    tiny_cf, sessions = tiny_cf_short
    b = train_bundle(tiny_cf, "hdfs", "drain", "pca")
    b = attach_early(b, from_sessions(sessions, Scorer(b)), age_s=3, model="pca", gate=10)
    b.save(tmp_path / "bundle")
    test = [s for s in sessions if s.split == "test"]
    ensure_topics("127.0.0.1:9092", 3, recreate=True)
    ready = tmp_path / "ready"
    eng = subprocess.Popen([sys.executable, "-m", "logsentinel.stream.engine", "--bundle", str(tmp_path / "bundle"),
                            "--group", "pytest-e2e", "--run-dir", str(tmp_path), "--ready-file", str(ready),
                            "--min-lines", "10", "--exit-after-idle-s", "30"])
    try:
        for _ in range(200):
            if ready.exists():
                break
            __import__("time").sleep(0.1)
        assert ready.exists(), "engine never got its partitions"
        # interleave sessions line by line, like a real log
        events = [(s.id.encode(), json.dumps(line).encode())
                  for lines in itertools.zip_longest(*[s.lines for s in test])
                  for s, line in zip(test, lines, strict=True) if line is not None]
        replay(events, "127.0.0.1:9092", None, 3)
        assert eng.wait(timeout=60) == 0
    finally:
        eng.kill()
    recs = {r["id"]: r for r in map(json.loads, (tmp_path / "worker-0.jsonl").read_text().splitlines())}
    assert set(recs) == {s.id for s in test}
    assert {k for k, r in recs.items() if r["alerted"]} == {s.id for s in test if s.label}
    off, _ = offline_scores(b, tiny_cf, "test")
    for sid, o in zip([tiny_cf.ids[i] for i in tiny_cf.rows("test")], off, strict=True):
        assert abs(recs[sid]["final_score"] - o) < 1e-6
