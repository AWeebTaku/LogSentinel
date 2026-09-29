import json
import re

import pytest
from fastapi.testclient import TestClient

from logsentinel.api import jobs
from logsentinel.api.app import create_app
from logsentinel.common.config import ROOT
from logsentinel.store import db
from logsentinel.stream import inject
from logsentinel.stream.source import plan_segments
from logsentinel.stream.wire import format_hdfs_time, hdfs_key, hdfs_log_time

LINE = "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-77 src: /10.0.0.1:5 dest: /10.0.0.2:5"
POOL = [{"id": "blk_-77", "lines": [LINE, "081109 203519 35 INFO dfs.FSNamesystem: addStoredBlock blk_-77 size 5",
                                    "081109 203540 35 ERROR dfs.DataNode: exception for blk_-77"]},
        {"id": "blk_-88", "lines": [LINE.replace("blk_-77", "blk_-88")]}]


def test_format_hdfs_time_inverts_hdfs_log_time():
    for prefix in ("081109 203518", "081111 000000", "081110 235959"):
        assert format_hdfs_time(hdfs_log_time(prefix + " x")) == prefix


def test_burst_uses_fresh_keys_current_time_and_keeps_session_order():
    t = hdfs_log_time("081110 120000 x")
    events, keys = inject.build_burst(POOL, 6, t, tag=7, seed=1)
    assert len(set(keys)) == 6 and all(re.fullmatch(r"blk_9\d+", k) for k in keys)
    lines = [json.loads(v) for _, v in events]
    assert all(ln.startswith("081110 120000 ") for ln in lines)          # every line stamped "now": no watermark jump
    assert all(hdfs_log_time(ln) == t for ln in lines)
    assert all("blk_-77" not in ln and "blk_-88" not in ln for ln in lines)   # original ids fully replaced
    for (k, v), ln in zip(events, lines, strict=True):
        assert hdfs_key(ln) == k.decode()                                  # routed by the new block id
    by = {}
    for k, v in events:
        by.setdefault(k, []).append(json.loads(v))
    for ls in by.values():                                                 # per-session line order is preserved
        originals = next(p["lines"] for p in POOL if len(p["lines"]) == len(ls))
        assert [x[13:].split(" ", 2)[2][:8] for x in ls] == [o[13:].split(" ", 2)[2][:8] for o in originals]


def test_plan_segments():
    assert plan_segments(1000, 500, "normal") == [(1000, 500)]
    seg = plan_segments(1000, 500, "spike")
    assert seg == [(400, 500), (200, 5000), (400, 500)] and sum(n for n, _ in seg) == 1000
    with pytest.raises(ValueError):
        plan_segments(10, 1, "drift")


@pytest.fixture
def con(tmp_path):
    with db.connect(tmp_path / "s.db") as c:
        yield c


def m(run, ts_s, rate, lag=0, wm=None, worker=0, p99=None, opens=10):
    return {"run": run, "worker": worker, "ts_ns": ts_s * 10**9 + 5, "events": 1, "rate_eps": rate,
            "open_sessions": opens, "alerts": 0, "alerts_interval": 0, "lag": lag, "batch_ms_p95": 3.0,
            "alert_lat_p99": p99, "watermark": wm}


def test_metrics_series_sums_workers_per_second(con):
    db.insert_metrics(con, [m("r", 100, 500, 10, 5.0, 0, 40.0), m("r", 100, 700, 20, 9.0, 1, 90.0),
                            m("r", 101, 600, 0, None, 0), m("other", 100, 1)])
    s = db.metrics_series(con, "r")
    assert [x["t"] for x in s] == [100, 101]
    assert s[0]["rate_eps"] == 1200 and s[0]["lag"] == 30 and s[0]["alert_lat_p99"] == 90.0
    assert s[0]["watermark"] == 9.0 and s[0]["open_sessions"] == 20
    assert db.metrics_series(con, "r", since_ns=100 * 10**9 + 10)[0]["t"] == 101


def test_metrics_retention_and_latest_watermark(con):
    now_s = 10_000_000
    db.insert_metrics(con, [m("r", now_s - 7 * 3600, 1)])
    db.insert_metrics(con, [m("r", now_s, 1, wm=123.0)])
    assert [x["t"] for x in db.metrics_series(con, "r")] == [now_s]           # 7 h old sample pruned
    assert db.latest_watermark(con, "r") is None                              # too old relative to real "now"


def test_score_histogram_and_injection_results(con):
    db.insert_alerts(con, [{"id": f"blk_{i}", "score": i / 10, "run": "r", "t_trigger_send_ns": 1} for i in range(1, 11)])
    h = db.score_histogram(con, "r", bins=5)
    assert sum(h["counts"]) == 10 and len(h["edges"]) == 6 and h["counts"][0] == 2
    # two detectors with different score scales: the ratio to each alert's own threshold puts them on one axis
    db.insert_alerts(con, [{"id": "pca", "score": 1.2, "threshold": 0.6, "run": "mix", "t_trigger_send_ns": 1},
                           {"id": "ae", "score": 0.06, "threshold": 0.03, "run": "mix", "t_trigger_send_ns": 1}])
    m = db.score_histogram(con, "mix", bins=4)
    assert m["counts"] == [2, 0, 0, 0] and m["edges"][0] == pytest.approx(2.0)
    assert db.score_histogram(con, "nope") == {"edges": [], "counts": []}
    db.record_injection(con, "r", "anomaly_burst", ["blk_1", "blk_2", "blk_999"], 1.0)
    (res,) = db.injection_results(con, "r")
    assert res["count"] == 3 and res["detected"] == 2 and res["time_to_alert_ms_max"] is not None


def _run(tmp_path, kind, status="running", params=None, pid=999_999_999):
    d = tmp_path / kind
    d.mkdir(exist_ok=True)
    return {"id": kind, "kind": kind, "status": status, "params": params or {}, "pid": pid, "run_dir": str(d)}


def test_job_refresh_states(con, tmp_path):
    db.create_run(con, "source", "source", {}, pid=1, run_dir=str(tmp_path / "source"))
    r = _run(tmp_path, "source")
    assert jobs.refresh(con, r)["status"] == "lost"                            # no exit file, pid gone
    db.update_run(con, "source", status="running")
    (tmp_path / "source" / "progress.json").write_text('{"phase": "stopped"}')
    (tmp_path / "source" / "exit").write_text("0\n")
    assert jobs.refresh(con, db.get_run(con, "source"))["status"] == "stopped"
    db.update_run(con, "source", status="running")
    (tmp_path / "source" / "progress.json").write_text('{"phase": "finished"}')
    (tmp_path / "source" / "summary.json").write_text('{"sessions_scored": 7}')
    done = jobs.refresh(con, db.get_run(con, "source"))
    assert done["status"] == "succeeded" and done["summary"] == {"sessions_scored": 7}   # loaded for the UI
    db.update_run(con, "source", status="running")
    (tmp_path / "source" / "exit").write_text("1\n")
    assert jobs.refresh(con, db.get_run(con, "source"))["status"] == "failed"
    done = db.get_run(con, "source")
    assert jobs.refresh(con, done) is done                                     # non-running jobs are left alone


def test_experiment_commands():
    cmd, art = jobs.experiment_command("stream_benchmark", {"bundle": "active:hdfs", "rate": 100, "sessions": 500,
                                                            "workers": 2}, "exp-x")
    assert cmd[2:4] == ["logsentinel.experiments.stream_e2e", "--bundle"] and "--run-id" in cmd
    assert art == ROOT / "results" / "stream" / "exp-x"
    cmd, art = jobs.experiment_command("offline_subset", {"datasets": ["bgl"], "modes": ["chronological"],
                                       "parsers": ["regex"], "models": ["pca"], "seeds": [0, 1]}, "exp-y")
    assert cmd[:2] == ["sh", "-c"] and "experiments.offline" in cmd[2] and "&& " in cmd[2] and "--seeds 0 1" in cmd[2]
    assert art == ROOT / "results" / "offline"


@pytest.fixture
def api(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(jobs, "launch", lambda cmd, rd: launched.append((cmd, rd)) or 4242)
    monkeypatch.setattr(jobs, "kafka_up", lambda: True)
    monkeypatch.setattr(jobs, "_alive", lambda pid: True)                    # the fake job counts as running
    killed = []
    monkeypatch.setattr("logsentinel.api.app.os.kill", lambda pid, sig: killed.append((pid, sig)))
    c = TestClient(create_app(tmp_path / "a.db"))
    c.launched, c.killed = launched, killed
    return c


def test_start_source_guards_and_launch(api, monkeypatch):
    monkeypatch.setattr(jobs, "kafka_up", lambda: False)
    assert api.post("/sources/start", json={}).status_code == 503
    monkeypatch.setattr(jobs, "kafka_up", lambda: True)
    assert api.post("/sources/start", json={}).status_code == 409             # no active model registered
    assert api.post("/sources/start", json={"rate": 1}).status_code == 422
    assert api.post("/sources/start", json={"bundle": "../../etc/passwd"}).status_code == 422
    assert api.post("/sources/start", json={"scenario": "drift"}).status_code == 422
    r = api.post("/sources/start", json={"bundle": "models/hdfs-drain-pca", "rate": 500, "scenario": "spike"})
    assert r.status_code == 202 and r.json()["kind"] == "source" and r.json()["pid"] == 4242
    cmd = api.launched[0][0]
    assert cmd[2] == "logsentinel.stream.source" and json.loads(cmd[-1])["scenario"] == "spike"
    assert api.post("/sources/start", json={"bundle": "models/hdfs-drain-pca"}).status_code == 409   # one at a time
    cur = api.get("/sources/current").json()
    assert cur["run"]["status"] == "running" and cur["progress"] == {}
    r2 = api.post("/sources/start", json={"bundle": "models/hdfs-drain-pca"})              # ids never collide
    assert r2.status_code == 409 and r.json()["id"].startswith("src-")


def test_inject_and_stop_guards(api, monkeypatch):
    import signal
    assert api.post("/sources/nope/inject", json={}).status_code == 404
    assert api.post("/sources/nope/stop").status_code == 404
    api.post("/sources/start", json={"bundle": "models/x"})
    run_id = api.get("/sources/current").json()["run"]["id"]
    assert api.post(f"/sources/{run_id}/inject", json={}).status_code == 409         # not streaming yet (no progress)
    assert api.post(f"/sources/{run_id}/inject", json={"count": 0}).status_code == 422
    assert api.get(f"/sources/{run_id}/injections").json() == {"items": []}
    assert api.post(f"/sources/{run_id}/stop").status_code == 200
    assert api.killed == [(4242, signal.SIGTERM)]                                    # the supervisor is asked to stop
    monkeypatch.setattr(jobs, "_alive", lambda pid: False)                           # process vanished: cannot stop
    assert api.post(f"/sources/{run_id}/stop").status_code == 409


def test_metrics_endpoint_and_stats_histogram(api, tmp_path):
    with db.connect(tmp_path / "a.db") as c:
        db.insert_metrics(c, [m("r1", 50, 100), m("r1", 51, 200)])
        db.insert_alerts(c, [{"id": "blk_1", "score": 0.5, "run": "r1", "t_trigger_send_ns": 1}])
    assert [x["rate_eps"] for x in api.get("/metrics", params={"run": "r1"}).json()["items"]] == [100, 200]
    assert api.get("/metrics").status_code == 422                                # run is required
    assert api.get("/alerts/stats", params={"run": "r1"}).json()["score_histogram"]["counts"][0] == 1


def test_experiment_endpoints_and_file_guards(api):
    assert api.post("/experiments/run", json={"preset": "nope"}).status_code == 422
    assert api.post("/experiments/run", json={"preset": "offline_subset", "models": ["gbm"]}).status_code == 422
    r = api.post("/experiments/run", json={"preset": "offline_report"})
    assert r.status_code == 202 and r.json()["params"]["artifacts"] == "results/offline"
    assert api.launched[-1][0][:2] == ["sh", "-c"]
    files = api.get(f"/experiments/{r.json()['id']}/files")
    assert files.status_code == 200 and isinstance(files.json()["items"], list)
    assert api.get("/experiments/zzz/files").status_code == 404
    assert api.get("/files", params={"path": "../../etc/passwd"}).status_code == 400
    assert api.get("/files", params={"path": "data/logsentinel.db"}).status_code == 400   # not under results/
    assert api.get("/files", params={"path": "results/does-not-exist.md"}).status_code == 404


def test_summarize_tolerates_injected_sessions(tiny_cf, tmp_path):
    """Regression: live-injected sessions have no dataset label and used to crash summarize() with a KeyError."""
    from logsentinel.experiments.stream_e2e import summarize
    from logsentinel.models.bundle import offline_scores, train_bundle

    b = train_bundle(tiny_cf, "hdfs", "regex", "pca")
    ids = [tiny_cf.ids[i] for i in tiny_cf.rows("test")]
    off, _ = offline_scores(b, tiny_cf, "test")
    t = 10**18
    recs = [{"id": k, "n": 12, "final_score": float(sc), "alerted": bool(sc >= b.threshold), "kind": "incremental",
             "alert_score": float(sc), "n_at_alert": 12, "evidence_log_s": 5.0, "t_trigger_send": t,
             "t_trigger_recv": t + 10**7, "t_scored": t + 2 * 10**7, "t_alert": t + 3 * 10**7}
            for k, sc in zip(ids, off, strict=True)]
    recs.append({**recs[0], "id": "blk_900100000", "alerted": True})          # an injected session
    (tmp_path / "worker-0.jsonl").write_text("\n".join(json.dumps(r) for r in recs))
    (tmp_path / "worker-0.stats.json").write_text(json.dumps({
        "events": 999, "sessions": len(recs), "alerts": 1, "eos": 3, "first_recv_ns": t, "last_recv_ns": t + 10**9,
        "score_seconds": 0.1, "threshold": b.threshold}))
    out = summarize(tmp_path, tiny_cf, ids, {"last_send_ns": t}, 1, b)
    assert out["injected_sessions"] == 1 and out["injected_alerted"] == 1
    assert out["sessions_scored"] == len(ids) and out["coverage"] == 1.0
    assert out["final_vs_offline_abs_diff"]["max"] == 0.0


def _wait_for(path, seconds=20):
    import time
    end = time.time() + seconds
    while time.time() < end and not path.exists():
        time.sleep(0.1)
    return path.exists()


def test_launch_writes_exit_code_and_log(tmp_path):
    import sys
    pid = jobs.launch([sys.executable, "-c", "print('hello'); raise SystemExit(3)"], tmp_path / "j")
    assert _wait_for(tmp_path / "j" / "exit")
    assert (tmp_path / "j" / "exit").read_text().strip() == "3"
    assert "hello" in (tmp_path / "j" / "log").read_text()
    import time
    time.sleep(0.3)
    assert jobs._alive(pid) is False                 # finished child is reaped, not left looking alive as a zombie


def test_sigterm_reaches_the_command_and_exit_is_recorded(tmp_path):
    import signal
    import sys
    import time
    code = ("import signal, sys, time\nsignal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
            "print('ready', flush=True)\ntime.sleep(60)")
    pid = jobs.launch([sys.executable, "-c", code], tmp_path / "j")
    log = tmp_path / "j" / "log"
    end = time.time() + 20
    while time.time() < end and not (log.exists() and "ready" in log.read_text()):
        time.sleep(0.1)
    assert jobs._alive(pid) is True
    import os
    os.kill(pid, signal.SIGTERM)                     # what POST /sources/{id}/stop does
    assert _wait_for(tmp_path / "j" / "exit")
    assert (tmp_path / "j" / "exit").read_text().strip() == "0"      # the command handled it and exited cleanly


def test_run_log_is_empty_before_the_job_writes_anything(api):
    r = api.post("/experiments/run", json={"preset": "offline_report"}).json()
    assert api.get(f"/runs/{r['id']}/log").json() == {"lines": []}          # no log file yet: not a 404
    assert api.get("/runs/does-not-exist/log").status_code == 404
