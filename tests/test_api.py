import shutil
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from logsentinel.api.app import create_app
from logsentinel.common.config import ROOT
from logsentinel.models.bundle import train_bundle
from logsentinel.store import db


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "api.db"
    with db.connect(path) as con:
        db.insert_alerts(con, [{"id": f"blk_{i}", "score": 0.5, "kind": "incremental", "run": "r", "model": "m",
                                "t_trigger_send_ns": 1} for i in range(1, 6)])
    return TestClient(create_app(path))


@pytest.fixture
def bundle_dir(tiny_cf):
    d = ROOT / "models" / f"_pytest-{uuid.uuid4().hex[:8]}"
    train_bundle(tiny_cf, "hdfs", "regex", "pca").save(d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_health_and_openapi(api):
    assert api.get("/health").json() == {"status": "ok", "alerts": 5, "models": 0}
    assert "/alerts/{alert_id}" in api.get("/openapi.json").json()["paths"]


def test_alert_list_pagination_and_filters(api):
    r = api.get("/alerts", params={"limit": 2}).json()
    assert [a["id"] for a in r["items"]] == [1, 2] and r["next_after_id"] == 2
    r = api.get("/alerts", params={"limit": 2, "after_id": 4}).json()
    assert [a["id"] for a in r["items"]] == [5] and r["next_after_id"] is None
    r = api.get("/alerts", params={"order": "desc", "limit": 3}).json()
    assert [a["id"] for a in r["items"]] == [5, 4, 3] and r["next_after_id"] is None     # newest first, no asc cursor
    assert api.get("/alerts", params={"order": "sideways"}).status_code == 422
    assert api.get("/alerts", params={"status": "bogus"}).status_code == 422
    assert api.get("/alerts", params={"limit": 0}).status_code == 422


def test_alert_triage_flow_and_errors(api):
    r = api.patch("/alerts/1", json={"status": "acknowledged", "note": "on it", "actor": "ann"})
    assert r.status_code == 200 and r.json()["status"] == "acknowledged"
    r = api.patch("/alerts/1", json={"status": "false_positive"})
    assert r.status_code == 200
    r = api.patch("/alerts/1", json={"status": "resolved"})               # closed -> resolved is not allowed
    assert r.status_code == 409 and r.json()["detail"]["allowed"] == ["open"]
    assert api.patch("/alerts/999", json={"status": "resolved"}).status_code == 404
    assert api.patch("/alerts/2", json={"status": "nonsense"}).status_code == 422
    body = api.get("/alerts/1").json()
    assert [e["to_status"] for e in body["events"]] == ["acknowledged", "false_positive"]
    st = api.get("/alerts/stats").json()
    assert st["by_status"]["false_positive"] == 1 and st["false_positive_rate_triaged"] == 1.0
    assert api.get("/alerts/999").status_code == 404


def test_model_registry_endpoints(api, bundle_dir):
    r = api.post("/models/register", json={"path": f"models/{bundle_dir.name}", "metrics": {"f1": 0.5}})
    assert r.status_code == 201 and r.json()["version"] == 1
    mid = r.json()["id"]
    assert api.get("/models/active", params={"dataset": "hdfs"}).status_code == 404
    assert api.post(f"/models/{mid}/activate").json()["status"] == "active"
    assert api.get("/models/active", params={"dataset": "hdfs"}).json()["id"] == mid
    assert api.put(f"/models/{mid}/metrics", json={"f1": 0.7}).json()["metrics"] == {"f1": 0.7}
    assert [m["id"] for m in api.get("/models", params={"dataset": "hdfs"}).json()["items"]] == [mid]
    assert api.get("/models/999").status_code == 404


def test_registry_and_import_reject_paths_outside_project(api):
    assert api.post("/models/register", json={"path": "../../etc"}).status_code == 400
    assert api.post("/models/register", json={"path": "/tmp"}).status_code == 400
    assert api.post("/models/register", json={"path": "data"}).status_code == 400          # not under models/
    assert api.post("/models/register", json={"path": "models/does-not-exist"}).status_code == 404
    assert api.post("/runs/import", json={"kind": "stream", "path": "../.."}).status_code == 400


def test_import_run_from_results(api, tmp_path):
    d = ROOT / "results" / f"_pytest-{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True)
    try:
        (d / "summary.json").write_text('{"coverage": 1.0}')
        r = api.post("/runs/import", json={"kind": "stream", "path": f"results/{d.name}"})
        assert r.status_code == 201 and r.json()["summary"] == {"coverage": 1.0}
        assert api.post("/runs/import", json={"kind": "stream", "path": f"results/{d.name}"}).status_code == 409
        assert api.get(f"/runs/{d.name}").json()["status"] == "finished"
        assert [x["id"] for x in api.get("/runs", params={"kind": "stream"}).json()["items"]] == [d.name]
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(not (ROOT / "data/features/hdfs.chronological.meta.json.gz").exists(),
                    reason="needs `make data` + featurized HDFS")
def test_train_job_runs_async_and_registers_model(api):
    name = f"_pytest-{uuid.uuid4().hex[:8]}"
    r = api.post("/models/train", json={"parser": "regex", "model": "pca", "name": name})
    assert r.status_code == 202 and r.json()["status"] == "running"
    run_id = r.json()["id"]
    try:
        for _ in range(240):
            run = api.get(f"/runs/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(1)
        assert run["status"] == "succeeded", api.get(f"/runs/{run_id}/log").json()
        m = api.get(f"/models/{run['model_id']}").json()
        assert m["name"] == name and m["meta"]["model"] == "pca"
        assert api.post("/models/train", json={"name": name}).status_code == 409        # no overwriting
    finally:
        shutil.rmtree(ROOT / "models" / name, ignore_errors=True)
        shutil.rmtree(ROOT / "results" / "train" / run_id, ignore_errors=True)


def test_train_rejects_bad_parameters(api):
    assert api.post("/models/train", json={"model": "deepnet"}).status_code == 422
    assert api.post("/models/train", json={"name": "../evil"}).status_code == 422
    assert api.post("/models/train", json={"early_age": -1}).status_code == 422

