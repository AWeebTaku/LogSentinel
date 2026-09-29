import json
import os
import socket
import subprocess
import sys
import time

import pytest

from logsentinel.alerts.sink import commit_batch, ingest, parse
from logsentinel.store import db


def msg(i, **kw):
    return json.dumps({"id": f"blk_{i}", "score": 0.9, "kind": "deadline", "run": "r", "model": "m",
                       "t_trigger_send_ns": time.time_ns(), **kw}).encode()


def test_parse_skips_malformed_but_keeps_the_rest():
    good, bad = parse([msg(1), b"not json", b'{"id": "x"}', b"[1,2]", b'{"id":"y","score":"abc"}', msg(2)])
    assert [g["id"] for g in good] == ["blk_1", "blk_2"] and bad == 4


def test_ingest_is_idempotent(tmp_path):
    with db.connect(tmp_path / "s.db") as con:
        assert ingest(con, [msg(1), msg(2), b"junk"]) == (2, 1)
        assert ingest(con, [msg(1), msg(2), msg(3)]) == (1, 0)            # at-least-once replay: only 3 is new
        assert con.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 3


class _Msg:
    def __init__(self, p, o):
        self._p, self._o = p, o

    def topic(self):
        return "alerts-critical"

    def partition(self):
        return self._p

    def offset(self):
        return self._o


class _Consumer:
    def __init__(self, exc=None):
        self.exc, self.committed = exc, None

    def commit(self, offsets, asynchronous):
        if self.exc:
            raise self.exc
        self.committed = {(t.partition, t.offset) for t in offsets}


def test_commit_batch_commits_max_offset_plus_one_per_partition():
    c = _Consumer()
    assert commit_batch(c, [_Msg(0, 4), _Msg(0, 7), _Msg(1, 2), _Msg(0, 5)])
    assert c.committed == {(0, 8), (1, 3)}


def test_commit_failure_is_not_fatal():
    """Regression: recreating the topic made commit() raise _NO_OFFSET and killed the sink mid-run."""
    from confluent_kafka import KafkaError, KafkaException
    c = _Consumer(KafkaException(KafkaError(KafkaError._NO_OFFSET)))
    assert commit_batch(c, [_Msg(0, 1)]) is False


def _broker_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 9092), timeout=1).close()
        return True
    except OSError:
        return False


@pytest.mark.e2e
@pytest.mark.skipif(not _broker_up(), reason="Kafka not running: scripts/kafka.sh start")
def test_kafka_to_sqlite_through_the_sink(tmp_path):
    from confluent_kafka import Producer

    from logsentinel.stream.admin import ensure_topics
    from logsentinel.stream.wire import TOPIC_ALERTS

    ensure_topics("127.0.0.1:9092", 3, recreate=True)
    p = Producer({"bootstrap.servers": "127.0.0.1:9092"})
    for v in [msg(1), msg(2), b"garbage", msg(2), msg(3)]:                  # a poison message and a duplicate
        p.produce(TOPIC_ALERTS, value=v)
    p.flush(10)
    dbf = tmp_path / "sink.db"
    r = subprocess.run([sys.executable, "-m", "logsentinel.alerts.sink", "--group", f"t-{time.time_ns()}",
                        "--exit-after-idle-s", "3"], env=os.environ | {"LOGSENTINEL_DB": str(dbf)},
                       capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 0, r.stderr
    with db.connect(dbf) as con:
        rows = con.execute("SELECT session_key, ingest_lag_ms FROM alerts ORDER BY session_key").fetchall()
    assert [x["session_key"] for x in rows] == ["blk_1", "blk_2", "blk_3"]   # order across partitions is not defined
    assert all(x["ingest_lag_ms"] > 0 for x in rows)
    assert "malformed=1" in r.stdout
