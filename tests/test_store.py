import pytest

from logsentinel.models.bundle import train_bundle
from logsentinel.store import db


def alert(i, run="r1", **kw):
    return {"id": f"blk_{i}", "score": 0.5 + i / 100, "kind": "incremental", "n_lines": 13, "run": run,
            "model": "m", "threshold": 0.4, "t_trigger_send_ns": 1_000_000_000, "worker": 0, **kw}


@pytest.fixture
def con(tmp_path):
    with db.connect(tmp_path / "t.db") as c:
        yield c


def test_insert_dedupes_replays_and_records_ingest_lag(con):
    assert db.insert_alerts(con, [alert(1), alert(2)], ingested_ns=1_005_000_000) == 2
    assert db.insert_alerts(con, [alert(1), alert(3)], ingested_ns=2_000_000_000) == 1   # replay of 1 ignored
    assert db.insert_alerts(con, [alert(1, run="r2")]) == 1                              # same block, other run
    a = db.get_alert(con, 1)
    assert a["ingest_lag_ms"] == pytest.approx(5.0) and a["status"] == "open" and a["events"] == []


def test_lifecycle_transitions_and_audit_trail(con):
    db.insert_alerts(con, [alert(1)])
    a = db.set_alert_status(con, 1, "acknowledged", actor="ann", note="looking")
    assert a["status"] == "acknowledged" and a["note"] == "looking"
    db.set_alert_status(con, 1, "false_positive", actor="ann")
    with pytest.raises(db.TransitionError) as e:
        db.set_alert_status(con, 1, "resolved")            # closed alerts must be reopened first
    assert e.value.allowed == ("open",)
    with pytest.raises(db.TransitionError):
        db.set_alert_status(con, 1, "false_positive")      # no self-transition
    db.set_alert_status(con, 1, "open", actor="bob")
    ev = db.get_alert(con, 1)["events"]
    assert [(x["from_status"], x["to_status"], x["actor"]) for x in ev] == [
        ("open", "acknowledged", "ann"), ("acknowledged", "false_positive", "ann"), ("false_positive", "open", "bob")]
    assert db.set_alert_status(con, 999, "resolved") is None


def test_filters_keyset_pagination_and_stats(con):
    db.insert_alerts(con, [alert(i, kind="deadline" if i % 2 else "incremental") for i in range(1, 8)])
    db.set_alert_status(con, 1, "resolved")
    db.set_alert_status(con, 2, "false_positive")
    db.set_alert_status(con, 3, "false_positive")
    page1 = db.list_alerts(con, limit=3)
    page2 = db.list_alerts(con, after_id=page1[-1]["id"], limit=3)
    assert [a["id"] for a in page1 + page2] == [1, 2, 3, 4, 5, 6]
    assert {a["id"] for a in db.list_alerts(con, status="open")} == {4, 5, 6, 7}
    assert all(a["kind"] == "deadline" for a in db.list_alerts(con, kind="deadline"))
    assert [a["id"] for a in db.list_alerts(con, min_score=0.56)] == [6, 7]
    st = db.alert_stats(con)
    assert st["total"] == 7 and st["by_status"]["false_positive"] == 2
    assert st["false_positive_rate_triaged"] == pytest.approx(2 / 3)


def test_model_registry_versions_and_single_active(con, tiny_cf, tmp_path):
    train_bundle(tiny_cf, "hdfs", "regex", "pca").save(tmp_path / "b1")
    m1 = db.register_model(con, tmp_path / "b1", "hdfs-x")
    m2 = db.register_model(con, tmp_path / "b1", "hdfs-x", metrics={"f1": 0.9})
    assert (m1["version"], m2["version"]) == (1, 2) and m2["metrics"] == {"f1": 0.9}
    assert m1["meta"]["parser"] == "regex" and m1["dataset"] == "hdfs"
    db.activate_model(con, m1["id"])
    db.activate_model(con, m2["id"])
    assert db.active_model(con, "hdfs")["id"] == m2["id"]
    assert db.get_model(con, m1["id"])["status"] == "registered"       # only one active per dataset
    with pytest.raises(FileNotFoundError):
        db.register_model(con, tmp_path / "nope")


def test_runs(con):
    db.create_run(con, "r1", "stream", {"rate": 1}, status="finished", summary={"f1": 0.9})
    assert db.get_run(con, "r1")["summary"] == {"f1": 0.9}
    db.update_run(con, "r1", status="archived")
    assert [r["id"] for r in db.list_runs(con, "stream")] == ["r1"] and db.list_runs(con, "train") == []
    with pytest.raises(KeyError):
        db.update_run(con, "r1", params={})


def test_stats_can_be_filtered_by_run(con):
    db.insert_alerts(con, [alert(1, run="a"), alert(2, run="a"), alert(3, run="b")], ingested_ns=1_002_000_000)
    assert db.alert_stats(con)["total"] == 3
    st = db.alert_stats(con, run="a")
    assert st["total"] == 2 and st["by_run"] == {"a": 2} and st["median_ingest_lag_ms"] == pytest.approx(2.0)
    assert db.alert_stats(con, run="zzz")["total"] == 0


def test_connection_can_be_used_from_another_thread(tmp_path):
    """Regression: FastAPI enters the connection dependency, runs the endpoint and exits it on different worker
    threads. sqlite3's default check_same_thread=True made that HTTP 500 under the UI's parallel polling."""
    from concurrent.futures import ThreadPoolExecutor
    cm = db.connect(tmp_path / "threads.db")
    con = cm.__enter__()                                             # created on this thread
    try:
        with ThreadPoolExecutor(1) as ex:
            assert ex.submit(lambda: con.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]).result() == 0
    finally:
        cm.__exit__(None, None, None)
