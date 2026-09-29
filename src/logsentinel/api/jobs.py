"""Background jobs (training, live sources, experiments): launch as detached processes, derive state from files.

A job's shell wrapper writes its exit code to <run_dir>/exit, so state survives API restarts:
  exit file present -> succeeded / failed (a stopped source reports its own phase)
  no exit file, pid gone -> lost
"""
import json
import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path

from ..common.config import ROOT
from ..store import db

JOB_KINDS = ("train", "source", "experiment")
BUNDLE_RE = r"^(active:[a-z0-9_-]+|models/[A-Za-z0-9._-]+)$"


def launch(cmd: list[str], run_dir: Path) -> int:
    """Start `cmd` under the runner (own session, survives the API). Returns the runner's pid."""
    run_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([sys.executable, "-m", "logsentinel.api.runner", str(run_dir), "--", *cmd],
                            start_new_session=True, cwd=ROOT)
    return proc.pid


def kafka_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 9092), timeout=1).close()
        return True
    except OSError:
        return False


def _alive(pid) -> bool:
    """True if the process is running. Finished children of this API process are reaped (a zombie still
    answers kill(pid, 0), which would make a dead job look alive forever)."""
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:            # not our child (e.g. the API was restarted): fall back to a signal probe
        pass
    except TypeError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def refresh(con, run: dict) -> dict:
    """Bring a job's stored status in line with what happened on disk (idempotent)."""
    if run["kind"] not in JOB_KINDS or run["status"] != "running":
        return run
    rd = Path(run["run_dir"])
    exit_f = rd / "exit"
    if not exit_f.exists():
        return run if _alive(run["pid"]) else db.update_run(con, run["id"], status="lost")
    ok = exit_f.read_text().strip() == "0"
    if run["kind"] == "train":
        if not ok:
            return db.update_run(con, run["id"], status="failed")
        m = db.register_model(con, ROOT / "models" / run["params"]["name"], run["params"]["name"])
        return db.update_run(con, run["id"], status="succeeded", model_id=m["id"])
    summary = _load_summary(run)
    extra = {"summary": summary} if summary is not None else {}
    if run["kind"] == "source" and ok and progress(run).get("phase") == "stopped":
        return db.update_run(con, run["id"], status="stopped", **extra)
    return db.update_run(con, run["id"], status="succeeded" if ok else "failed", **extra)


def _load_summary(run: dict) -> dict | None:
    """A finished source/experiment leaves summary.json (in its run dir, or its artifacts dir); store it on the run."""
    dirs = [Path(run["run_dir"] or "")]
    if run["params"].get("artifacts"):
        dirs.append(ROOT / run["params"]["artifacts"])
    for d in dirs:
        f = d / "summary.json"
        if f.is_file():
            try:
                return json.loads(f.read_text())
            except ValueError:
                return None
    return None


def progress(run: dict) -> dict:
    f = Path(run["run_dir"] or "") / "progress.json"
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {}


def running_job(con, kinds=("source", "experiment")) -> dict | None:
    """The job currently holding the Kafka topics (sources and stream benchmarks recreate them)."""
    for r in db.list_runs(con):
        if r["kind"] in kinds and refresh(con, r)["status"] == "running":
            return r
    return None


def experiment_command(preset: str, p: dict, run_id: str) -> tuple[list[str], Path]:
    """(command, artifact directory) for an experiment preset."""
    py = [sys.executable, "-m"]
    if preset == "stream_benchmark":
        cmd = [*py, "logsentinel.experiments.stream_e2e", "--bundle", p["bundle"], "--rate", str(p["rate"]),
               "--sessions", str(p["sessions"]), "--workers", str(p["workers"]), "--run-id", run_id]
        return cmd, ROOT / "results" / "stream" / run_id
    report = shlex.join([*py, "logsentinel.experiments.report"])
    if preset == "offline_report":
        return ["sh", "-c", report], ROOT / "results" / "offline"
    if preset == "offline_subset":
        grid = [*py, "logsentinel.experiments.offline", "--datasets", *p["datasets"], "--modes", *p["modes"],
                "--parsers", *p["parsers"], "--models", *p["models"], "--seeds", *map(str, p["seeds"]), "--force"]
        return ["sh", "-c", f"{shlex.join(grid)} && {report}"], ROOT / "results" / "offline"
    raise ValueError(preset)


ARTIFACT_SUFFIXES = {".png", ".md", ".csv", ".json", ".txt", ".log"}


def list_artifacts(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    out = []
    for f in sorted(directory.rglob("*")):
        if f.is_file() and f.suffix in ARTIFACT_SUFFIXES and "cells" not in f.parts and not f.name.startswith("worker-"):
            out.append({"path": str(f.relative_to(ROOT)), "size": f.stat().st_size})
    return out
