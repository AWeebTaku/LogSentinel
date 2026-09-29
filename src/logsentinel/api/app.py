"""REST API (FastAPI): alert inbox + lifecycle, model registry (+ training jobs), runs.

UI-agnostic JSON over HTTP with CORS for local dev servers; OpenAPI docs at /docs. Binds to localhost and has
no authentication: do not expose it beyond the machine without adding auth in front.
Bundles are joblib (pickle) files, so registering/importing is restricted to paths inside this project.
"""
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..common.config import ROOT
from ..store import db
from . import jobs

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]


class AlertPatch(BaseModel):
    status: Literal["open", "acknowledged", "resolved", "false_positive"]
    note: str = Field("", max_length=2000)
    actor: str = Field("user", max_length=100)


class RegisterModel(BaseModel):
    path: str
    name: str | None = None
    metrics: dict | None = None


class TrainRequest(BaseModel):
    dataset: Literal["hdfs"] = "hdfs"
    mode: Literal["chronological", "random"] = "chronological"
    parser: Literal["regex", "drain"] = "drain"
    model: Literal["iforest", "pca", "ae"] = "pca"
    threshold: Literal["percentile99", "three_sigma", "tuned_val"] = "tuned_val"
    early_age: int = Field(0, ge=0, le=3600, description="log-seconds for the age check; 0 = none")
    early_model: Literal["iforest", "pca", "ae"] = "ae"
    seed: int = 0
    name: str | None = Field(None, pattern=r"^[A-Za-z0-9._-]{1,80}$")


class StartSource(BaseModel):
    rate: int = Field(2000, ge=10, le=200_000, description="events/s (the spike scenario runs 10x this in the middle)")
    sessions: int = Field(10000, ge=100, le=172_519, description="test sessions to replay")
    workers: int = Field(1, ge=1, le=4)
    scenario: Literal["normal", "spike"] = "normal"
    bundle: str = Field("active:hdfs", pattern=jobs.BUNDLE_RE)


class InjectRequest(BaseModel):
    scenario: Literal["anomaly_burst"] = "anomaly_burst"
    count: int = Field(100, ge=1, le=2000, description="anomalous sessions to inject")


class ExperimentRequest(BaseModel):
    preset: Literal["stream_benchmark", "offline_report", "offline_subset"]
    rate: int = Field(5000, ge=0, le=200_000, description="stream_benchmark: events/s, 0 = burst")
    sessions: int = Field(5000, ge=100, le=172_519)
    workers: int = Field(1, ge=1, le=4)
    bundle: str = Field("active:hdfs", pattern=jobs.BUNDLE_RE)
    datasets: list[Literal["hdfs", "bgl", "thunderbird"]] = ["bgl"]
    modes: list[Literal["chronological", "random"]] = ["chronological"]
    parsers: list[Literal["raw", "regex", "drain"]] = ["regex", "drain"]
    models: list[Literal["iforest", "pca", "ae"]] = ["iforest", "pca"]
    seeds: list[int] = Field([0], min_length=1, max_length=5)


class ImportRun(BaseModel):
    kind: Literal["stream", "offline"]
    path: str = Field(description="results directory containing summary.json, relative to the project root")


def _inside(path: str, base: Path) -> Path:
    p = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if not p.is_relative_to(base.resolve()):
        raise HTTPException(400, f"path must be inside {base.relative_to(ROOT)}/")
    return p


def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="LogSentinel API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    app.state.db = db_path

    def get_con():
        with db.connect(app.state.db) as con:
            yield con

    @app.get("/health")
    def health(con=Depends(get_con)):
        return {"status": "ok", "alerts": con.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
                "models": con.execute("SELECT COUNT(*) FROM models").fetchone()[0]}

    # ---- alerts ----
    @app.get("/alerts")
    def alerts(status: Literal["open", "acknowledged", "resolved", "false_positive"] | None = None,
               kind: str | None = None, run: str | None = None, min_score: float | None = None,
               after_id: int = Query(0, ge=0, description="keyset cursor: return alerts with id greater than this"),
               limit: int = Query(50, ge=1, le=500),
               order: Literal["asc", "desc"] = Query("asc", description="desc = newest first (for inboxes)"),
               con=Depends(get_con)):
        items = db.list_alerts(con, status, kind, run, min_score, after_id, limit, order == "desc")
        return {"items": items, "next_after_id": items[-1]["id"] if len(items) == limit and order == "asc" else None}

    @app.get("/alerts/stats")
    def stats(run: str | None = None, con=Depends(get_con)):
        return db.alert_stats(con, run) | {"score_histogram": db.score_histogram(con, run)}

    @app.get("/alerts/{alert_id}")
    def alert(alert_id: int, con=Depends(get_con)):
        a = db.get_alert(con, alert_id)
        if a is None:
            raise HTTPException(404, "alert not found")
        return a

    @app.patch("/alerts/{alert_id}")
    def patch_alert(alert_id: int, body: AlertPatch, con=Depends(get_con)):
        try:
            a = db.set_alert_status(con, alert_id, body.status, body.actor, body.note)
        except db.TransitionError as e:
            raise HTTPException(409, {"message": str(e), "allowed": list(e.allowed)}) from e
        if a is None:
            raise HTTPException(404, "alert not found")
        return a

    # ---- model registry ----
    @app.get("/models")
    def models(dataset: str | None = None, con=Depends(get_con)):
        return {"items": db.list_models(con, dataset)}

    @app.get("/models/active")
    def active(dataset: str, con=Depends(get_con)):
        m = db.active_model(con, dataset)
        if m is None:
            raise HTTPException(404, f"no active model for dataset {dataset!r}")
        return m

    @app.post("/models/register", status_code=201)
    def register(body: RegisterModel, con=Depends(get_con)):
        path = _inside(body.path, ROOT / "models")
        try:
            return db.register_model(con, path, body.name, body.metrics)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e

    @app.post("/models/train", status_code=202)
    def train(body: TrainRequest, con=Depends(get_con)):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = body.name or f"{body.dataset}-{body.parser}-{body.model}{f'-early{body.early_age}' if body.early_age else ''}-{stamp}"
        if (ROOT / "models" / name).exists():
            raise HTTPException(409, f"models/{name} already exists")
        run_id = f"train-{stamp}-{os.urandom(2).hex()}"
        rd = ROOT / "results" / "train" / run_id
        cmd = [sys.executable, "-m", "logsentinel.models.train", "--dataset", body.dataset, "--mode", body.mode,
               "--parser", body.parser, "--model", body.model, "--threshold", body.threshold,
               "--seed", str(body.seed), "--out", str(ROOT / "models" / name)]
        if body.early_age:
            cmd += ["--early-age", str(body.early_age), "--early-model", body.early_model]
        pid = jobs.launch(cmd, rd)
        return db.create_run(con, run_id, "train", body.model_dump() | {"name": name}, pid=pid, run_dir=str(rd))

    @app.get("/models/{model_id}")
    def model(model_id: int, con=Depends(get_con)):
        m = db.get_model(con, model_id)
        if m is None:
            raise HTTPException(404, "model not found")
        return m

    @app.post("/models/{model_id}/activate")
    def activate(model_id: int, con=Depends(get_con)):
        m = db.activate_model(con, model_id)
        if m is None:
            raise HTTPException(404, "model not found")
        return m

    @app.put("/models/{model_id}/metrics")
    def put_metrics(model_id: int, metrics: dict, con=Depends(get_con)):
        m = db.update_model_metrics(con, model_id, metrics)
        if m is None:
            raise HTTPException(404, "model not found")
        return m

    # ---- live metrics ----
    @app.get("/metrics")
    def metrics(run: str, since_ns: int = 0, limit: int = Query(300, ge=1, le=3600), con=Depends(get_con)):
        return {"items": db.metrics_series(con, run, since_ns, limit)}

    # ---- sources (live pipeline sessions) ----
    @app.post("/sources/start", status_code=202)
    def start_source(body: StartSource, con=Depends(get_con)):
        if not jobs.kafka_up():
            raise HTTPException(503, "Kafka is not running on 127.0.0.1:9092 (scripts/kafka.sh start)")
        busy = jobs.running_job(con)
        if busy:
            raise HTTPException(409, f"{busy['kind']} {busy['id']!r} is already running; stop it first")
        if body.bundle.startswith("active:") and db.active_model(con, body.bundle.split(":", 1)[1]) is None:
            raise HTTPException(409, "no active model: register and activate one under Models first")
        run_id = f"src-{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(2).hex()}"
        rd = ROOT / "results" / "sources" / run_id
        params = body.model_dump()
        pid = jobs.launch([sys.executable, "-m", "logsentinel.stream.source", "--run-id", run_id,
                           "--params", json.dumps(params)], rd)
        return db.create_run(con, run_id, "source", params, pid=pid, run_dir=str(rd))

    @app.get("/sources/current")
    def current_source(con=Depends(get_con)):
        runs = [jobs.refresh(con, r) for r in db.list_runs(con, "source")]
        run = next((r for r in runs if r["status"] == "running"), runs[0] if runs else None)
        return {"run": run, "progress": jobs.progress(run) if run else {}}

    @app.post("/sources/{run_id}/stop")
    def stop_source(run_id: str, con=Depends(get_con)):
        run = db.get_run(con, run_id)
        if run is None or run["kind"] != "source":
            raise HTTPException(404, "source not found")
        run = jobs.refresh(con, run)
        if run["status"] != "running":
            raise HTTPException(409, f"source is {run['status']}, not running")
        try:
            os.kill(run["pid"], signal.SIGTERM)      # the supervisor stops the replay and drains the engines
        except ProcessLookupError:
            pass
        return run

    @app.post("/sources/{run_id}/inject", status_code=202)
    def inject(run_id: str, body: InjectRequest, con=Depends(get_con)):
        from ..stream import inject as inj
        from ..stream import pools
        run = db.get_run(con, run_id)
        run = jobs.refresh(con, run) if run else None
        if run is None or run["kind"] != "source":
            raise HTTPException(404, "source not found")
        if run["status"] != "running" or jobs.progress(run).get("phase") != "running":
            raise HTTPException(409, "the source is not streaming right now")
        wm = db.latest_watermark(con, run_id)
        if wm is None:
            raise HTTPException(409, "no live metrics yet from this source; try again in a few seconds")
        try:
            pool = pools.load()
        except FileNotFoundError as e:
            raise HTTPException(409, str(e)) from e
        tag = (con.execute("SELECT COALESCE(MAX(id), 0) FROM injections").fetchone()[0] + 1) % 1000
        events, keys = inj.build_burst(pool, body.count, wm, tag)
        inj.send(events, "127.0.0.1:9092")
        return {"injection_id": db.record_injection(con, run_id, body.scenario, keys, wm), "count": len(keys),
                "lines": len(events), "stream_time": wm}

    @app.get("/sources/{run_id}/injections")
    def injections(run_id: str, con=Depends(get_con)):
        return {"items": db.injection_results(con, run_id)}

    # ---- experiments ----
    @app.post("/experiments/run", status_code=202)
    def run_experiment(body: ExperimentRequest, con=Depends(get_con)):
        if body.preset == "stream_benchmark":
            if not jobs.kafka_up():
                raise HTTPException(503, "Kafka is not running on 127.0.0.1:9092 (scripts/kafka.sh start)")
            busy = jobs.running_job(con)
            if busy:
                raise HTTPException(409, f"{busy['kind']} {busy['id']!r} is running and shares the Kafka topics")
            if body.bundle.startswith("active:") and db.active_model(con, body.bundle.split(":", 1)[1]) is None:
                raise HTTPException(409, "no active model: register and activate one under Models first")
        run_id = f"exp-{body.preset}-{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(2).hex()}"
        cmd, artifacts = jobs.experiment_command(body.preset, body.model_dump(), run_id)
        rd = ROOT / "results" / "experiments" / run_id
        pid = jobs.launch(cmd, rd)
        return db.create_run(con, run_id, "experiment", body.model_dump() | {"artifacts": str(artifacts.relative_to(ROOT))},
                             pid=pid, run_dir=str(rd))

    @app.get("/experiments/{run_id}/files")
    def experiment_files(run_id: str, con=Depends(get_con)):
        run = db.get_run(con, run_id)
        if run is None or run["kind"] != "experiment":
            raise HTTPException(404, "experiment not found")
        return {"items": jobs.list_artifacts(ROOT / run["params"]["artifacts"])}

    @app.get("/files")
    def files(path: str):
        p = _inside(path, ROOT / "results")
        if not p.is_file() or p.suffix not in jobs.ARTIFACT_SUFFIXES:
            raise HTTPException(404, "file not found")
        return FileResponse(p)

    # ---- runs ----
    @app.get("/runs")
    def runs(kind: str | None = None, con=Depends(get_con)):
        return {"items": [jobs.refresh(con, r) for r in db.list_runs(con, kind)]}

    @app.get("/runs/{run_id}")
    def run(run_id: str, con=Depends(get_con)):
        r = db.get_run(con, run_id)
        if r is None:
            raise HTTPException(404, "run not found")
        return jobs.refresh(con, r)

    @app.get("/runs/{run_id}/log")
    def run_log(run_id: str, tail: int = Query(200, ge=1, le=5000), con=Depends(get_con)):
        r = db.get_run(con, run_id)
        if r is None:
            raise HTTPException(404, "run not found")
        log = Path(r["run_dir"] or "") / "log"
        # a job that has just started has no log yet: that is an empty log, not an error
        return {"lines": log.read_text(errors="replace").splitlines()[-tail:] if log.is_file() else []}

    @app.post("/runs/import", status_code=201)
    def import_run(body: ImportRun, con=Depends(get_con)):
        d = _inside(body.path, ROOT / "results")
        if not (d / "summary.json").exists():
            raise HTTPException(404, f"{body.path}/summary.json not found")
        if db.get_run(con, d.name):
            raise HTTPException(409, f"run {d.name!r} already imported")
        params = json.loads((d / "env.json").read_text()).get("args", {}) if (d / "env.json").exists() else {}
        return db.create_run(con, d.name, body.kind, params, status="finished", run_dir=str(d),
                             summary=json.loads((d / "summary.json").read_text()))

    dist = ROOT / "ui" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")   # last: API routes win
    return app


app = create_app()
