"""SQLite storage: alerts (+ audit trail), model registry, runs. Stdlib only, no ORM.

WAL mode lets the sink service write while the API reads. Every function opens a short-lived connection,
so nothing is shared across threads/processes. Path: $LOGSENTINEL_DB or data/logsentinel.db.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from ..common.config import ROOT

STATUSES = ("open", "acknowledged", "resolved", "false_positive")
# alert lifecycle: what each status may move to (no self-transitions)
TRANSITIONS = {
    "open": ("acknowledged", "resolved", "false_positive"),
    "acknowledged": ("open", "resolved", "false_positive"),
    "resolved": ("open",),
    "false_positive": ("open",),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run TEXT NOT NULL,                 -- engine consumer group / run id
  session_key TEXT NOT NULL,         -- e.g. HDFS block id
  model TEXT,                        -- bundle name that raised it
  kind TEXT NOT NULL,                -- incremental | deadline | deadline_eos
  score REAL NOT NULL,
  threshold REAL,
  n_lines INTEGER,
  evidence_log_s REAL,               -- log time between session start and the evidence
  worker INTEGER,
  t_trigger_send_ns INTEGER,
  ingest_lag_ms REAL,                -- sink receive time - trigger send time
  status TEXT NOT NULL DEFAULT 'open',
  note TEXT NOT NULL DEFAULT '',
  created_ns INTEGER NOT NULL,
  updated_ns INTEGER NOT NULL,
  UNIQUE (run, session_key)          -- Kafka is at-least-once: replays must not duplicate alerts
);
CREATE INDEX IF NOT EXISTS alerts_status ON alerts (status, id);
CREATE TABLE IF NOT EXISTS alert_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id INTEGER NOT NULL REFERENCES alerts(id),
  ts_ns INTEGER NOT NULL, from_status TEXT, to_status TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, version INTEGER NOT NULL,
  path TEXT NOT NULL, dataset TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'registered',   -- registered | active | archived
  meta TEXT NOT NULL, metrics TEXT,            -- JSON: training meta, optional offline metrics
  created_ns INTEGER NOT NULL,
  UNIQUE (name, version)
);
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run TEXT NOT NULL, worker INTEGER NOT NULL, ts_ns INTEGER NOT NULL,
  events INTEGER, rate_eps REAL, open_sessions INTEGER, alerts INTEGER, alerts_interval INTEGER, lag INTEGER,
  batch_ms_p95 REAL, alert_lat_p50 REAL, alert_lat_p95 REAL, alert_lat_p99 REAL, watermark REAL
);
CREATE INDEX IF NOT EXISTS metrics_run_ts ON metrics (run, ts_ns);
CREATE TABLE IF NOT EXISTS injections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run TEXT NOT NULL, scenario TEXT NOT NULL, count INTEGER NOT NULL,
  keys TEXT NOT NULL,                          -- JSON list of injected session keys
  stream_time REAL, t_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL,     -- train | stream | offline
  status TEXT NOT NULL, params TEXT NOT NULL, summary TEXT,
  pid INTEGER, run_dir TEXT, model_id INTEGER REFERENCES models(id),
  created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("LOGSENTINEL_DB", ROOT / "data" / "logsentinel.db"))


@contextmanager
def connect(path: Path | None = None):
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30, check_same_thread=False)   # one request at a time per connection; FastAPI hops worker threads
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def _now() -> int:
    return time.time_ns()


# ---- alerts -----------------------------------------------------------------------------------------

def insert_alerts(con, alerts: list[dict], ingested_ns: int | None = None) -> int:
    """Insert engine alert payloads; duplicates (same run + session) are ignored. Returns rows inserted."""
    ing = ingested_ns or _now()
    n0 = con.total_changes
    for a in alerts:
        sent = a.get("t_trigger_send_ns")
        con.execute(
            """INSERT OR IGNORE INTO alerts (run, session_key, model, kind, score, threshold, n_lines,
               evidence_log_s, worker, t_trigger_send_ns, ingest_lag_ms, created_ns, updated_ns)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a.get("run", ""), a["id"], a.get("model"), a.get("kind", "incremental"), float(a["score"]),
             a.get("threshold"), a.get("n_lines"), a.get("evidence_log_s"), a.get("worker"), sent,
             (ing - sent) / 1e6 if sent else None, ing, ing))
    return con.total_changes - n0


def list_alerts(con, status=None, kind=None, run=None, min_score=None, after_id=0, limit=50,
                newest_first=False) -> list[dict]:
    q, args = "SELECT * FROM alerts WHERE id > ?", [after_id]
    for col, val, op in (("status", status, "="), ("kind", kind, "="), ("run", run, "="), ("score", min_score, ">=")):
        if val is not None:
            q += f" AND {col} {op} ?"
            args.append(val)
    q += f" ORDER BY id {'DESC' if newest_first else ''} LIMIT ?"
    return [dict(r) for r in con.execute(q, [*args, limit])]


def get_alert(con, alert_id: int) -> dict | None:
    r = con.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["events"] = [dict(e) for e in con.execute(
        "SELECT ts_ns, from_status, to_status, actor, note FROM alert_events WHERE alert_id=? ORDER BY id",
        (alert_id,))]
    return d


class TransitionError(ValueError):
    def __init__(self, cur: str, new: str):
        self.allowed = TRANSITIONS[cur]
        super().__init__(f"cannot move alert from {cur!r} to {new!r}; allowed: {list(self.allowed)}")


def set_alert_status(con, alert_id: int, new: str, actor: str = "user", note: str = "") -> dict | None:
    row = con.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()
    if row is None:
        return None
    cur = row["status"]
    if new not in TRANSITIONS.get(cur, ()):
        raise TransitionError(cur, new)
    ts = _now()
    con.execute("UPDATE alerts SET status=?, note=CASE WHEN ?='' THEN note ELSE ? END, updated_ns=? WHERE id=?",
                (new, note, note, ts, alert_id))
    con.execute("INSERT INTO alert_events (alert_id, ts_ns, from_status, to_status, actor, note) VALUES (?,?,?,?,?,?)",
                (alert_id, ts, cur, new, actor, note))
    return get_alert(con, alert_id)


def alert_stats(con, run: str | None = None) -> dict:
    where, args = ("WHERE run=?", [run]) if run else ("", [])

    def by(col):
        return {r[0]: r[1] for r in con.execute(f"SELECT {col}, COUNT(*) FROM alerts {where} GROUP BY {col}", args)}

    status = by("status")
    triaged = status.get("resolved", 0) + status.get("false_positive", 0)
    lags = [r[0] for r in con.execute(
        f"SELECT ingest_lag_ms FROM alerts {where} {'AND' if run else 'WHERE'} ingest_lag_ms IS NOT NULL "
        "ORDER BY ingest_lag_ms", args)]
    return {"total": sum(status.values()), "by_status": status, "by_kind": by("kind"), "by_run": by("run"),
            # share of triaged alerts an operator called false positives (feedback signal for threshold tuning)
            "false_positive_rate_triaged": (status.get("false_positive", 0) / triaged) if triaged else None,
            "median_ingest_lag_ms": lags[len(lags) // 2] if lags else None}


# ---- live metrics -----------------------------------------------------------------------------------

METRIC_COLS = ("events", "rate_eps", "open_sessions", "alerts", "alerts_interval", "lag", "batch_ms_p95",
               "alert_lat_p50", "alert_lat_p95", "alert_lat_p99", "watermark")
KEEP_METRICS_NS = 6 * 3600 * 10**9


def insert_metrics(con, rows: list[dict]) -> int:
    for m in rows:
        con.execute(f"INSERT INTO metrics (run, worker, ts_ns, {', '.join(METRIC_COLS)}) "
                    f"VALUES (?,?,?,{','.join('?' * len(METRIC_COLS))})",
                    (m["run"], int(m.get("worker", 0)), int(m["ts_ns"]), *(m.get(c) for c in METRIC_COLS)))
    if rows:                                                     # retention: keep the last 6 hours
        con.execute("DELETE FROM metrics WHERE ts_ns < ?", (max(int(m["ts_ns"]) for m in rows) - KEEP_METRICS_NS,))
    return len(rows)


def metrics_series(con, run: str, since_ns: int = 0, limit: int = 600) -> list[dict]:
    """One row per second, summed/maxed over workers (latency percentiles: max over workers, an upper bound)."""
    rows = con.execute(
        """SELECT ts_ns / 1000000000 AS t, SUM(rate_eps) AS rate_eps, SUM(lag) AS lag,
                  SUM(open_sessions) AS open_sessions, SUM(alerts) AS alerts, SUM(alerts_interval) AS alerts_interval,
                  MAX(batch_ms_p95) AS batch_ms_p95, MAX(alert_lat_p50) AS alert_lat_p50,
                  MAX(alert_lat_p95) AS alert_lat_p95, MAX(alert_lat_p99) AS alert_lat_p99,
                  MAX(watermark) AS watermark, SUM(events) AS events
           FROM metrics WHERE run=? AND ts_ns > ? GROUP BY t ORDER BY t DESC LIMIT ?""",
        (run, since_ns, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def latest_watermark(con, run: str, max_age_s: float = 15.0) -> float | None:
    r = con.execute("SELECT MAX(watermark) FROM metrics WHERE run=? AND ts_ns > ?",
                    (run, _now() - int(max_age_s * 1e9))).fetchone()
    return r[0]


def score_histogram(con, run: str | None = None, bins: int = 20) -> dict:
    """Histogram of score / threshold per alert (1.0 = exactly at the alert's own threshold).

    Incremental alerts (full-session detector) and deadline alerts (age-check detector) use different score
    scales, so raw scores are not comparable; the ratio to each alert's own threshold is."""
    where, args = ("WHERE run=?", [run]) if run else ("", [])
    ratios = [r["score"] / r["threshold"] if r["threshold"] else r["score"]
              for r in con.execute(f"SELECT score, threshold FROM alerts {where}", args)]
    if not ratios:
        return {"edges": [], "counts": []}
    lo, hi = min(ratios), max(ratios)
    width = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for v in ratios:
        counts[min(bins - 1, int((v - lo) / width))] += 1
    return {"edges": [lo + i * width for i in range(bins + 1)], "counts": counts}


# ---- injections -------------------------------------------------------------------------------------

def record_injection(con, run: str, scenario: str, keys: list[str], stream_time: float | None) -> int:
    cur = con.execute("INSERT INTO injections (run, scenario, count, keys, stream_time, t_ns) VALUES (?,?,?,?,?,?)",
                      (run, scenario, len(keys), json.dumps(keys), stream_time, _now()))
    return cur.lastrowid


def injection_results(con, run: str) -> list[dict]:
    """For each injection: how many injected sessions were alerted on, and how fast (wall clock)."""
    out = []
    for inj in con.execute("SELECT * FROM injections WHERE run=? ORDER BY id", (run,)):
        keys = json.loads(inj["keys"])
        got = {r["session_key"]: r["created_ns"] for r in con.execute(
            f"SELECT session_key, created_ns FROM alerts WHERE run=? AND session_key IN ({','.join('?' * len(keys))})",
            [run, *keys])} if keys else {}
        lags = sorted((t - inj["t_ns"]) / 1e6 for t in got.values())
        out.append({"id": inj["id"], "scenario": inj["scenario"], "count": inj["count"], "detected": len(got),
                    "time_to_alert_ms_p50": lags[len(lags) // 2] if lags else None,
                    "time_to_alert_ms_max": lags[-1] if lags else None})
    return out


# ---- model registry ---------------------------------------------------------------------------------

def _model(r) -> dict:
    d = dict(r)
    d["meta"] = json.loads(d["meta"])
    d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else None
    return d


def register_model(con, bundle_dir: Path, name: str | None = None, metrics: dict | None = None) -> dict:
    bundle_dir = Path(bundle_dir).resolve()
    meta_f = bundle_dir / "meta.json"
    if not (bundle_dir / "bundle.joblib").exists() or not meta_f.exists():
        raise FileNotFoundError(f"{bundle_dir} is not a bundle directory (needs bundle.joblib + meta.json)")
    meta = json.loads(meta_f.read_text())
    name = name or bundle_dir.name
    ver = (con.execute("SELECT MAX(version) FROM models WHERE name=?", (name,)).fetchone()[0] or 0) + 1
    cur = con.execute(
        "INSERT INTO models (name, version, path, dataset, meta, metrics, created_ns) VALUES (?,?,?,?,?,?,?)",
        (name, ver, str(bundle_dir), meta["dataset"], json.dumps(meta),
         json.dumps(metrics) if metrics else None, _now()))
    return get_model(con, cur.lastrowid)


def get_model(con, model_id: int) -> dict | None:
    r = con.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
    return _model(r) if r else None


def list_models(con, dataset: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM models", []
    if dataset:
        q, args = q + " WHERE dataset=?", [dataset]
    return [_model(r) for r in con.execute(q + " ORDER BY id", args)]


def activate_model(con, model_id: int) -> dict | None:
    """Make this the single active model for its dataset (the previous one goes back to 'registered')."""
    m = get_model(con, model_id)
    if m is None:
        return None
    con.execute("UPDATE models SET status='registered' WHERE dataset=? AND status='active'", (m["dataset"],))
    con.execute("UPDATE models SET status='active' WHERE id=?", (model_id,))
    return get_model(con, model_id)


def active_model(con, dataset: str) -> dict | None:
    r = con.execute("SELECT * FROM models WHERE dataset=? AND status='active'", (dataset,)).fetchone()
    return _model(r) if r else None


def update_model_metrics(con, model_id: int, metrics: dict) -> dict | None:
    con.execute("UPDATE models SET metrics=? WHERE id=?", (json.dumps(metrics), model_id))
    return get_model(con, model_id)


# ---- runs -------------------------------------------------------------------------------------------

def _run(r) -> dict:
    d = dict(r)
    d["params"] = json.loads(d["params"])
    d["summary"] = json.loads(d["summary"]) if d["summary"] else None
    return d


def create_run(con, run_id: str, kind: str, params: dict, status: str = "running", pid: int | None = None,
               run_dir: str | None = None, summary: dict | None = None) -> dict:
    ts = _now()
    con.execute("INSERT INTO runs (id, kind, status, params, summary, pid, run_dir, created_ns, updated_ns) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, kind, status, json.dumps(params), json.dumps(summary) if summary else None,
                 pid, run_dir, ts, ts))
    return get_run(con, run_id)


def get_run(con, run_id: str) -> dict | None:
    r = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _run(r) if r else None


def list_runs(con, kind: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM runs", []
    if kind:
        q, args = q + " WHERE kind=?", [kind]
    return [_run(r) for r in con.execute(q + " ORDER BY created_ns DESC", args)]


def update_run(con, run_id: str, **fields) -> dict | None:
    allowed = {"status", "summary", "model_id", "pid"}
    sets, args = [], []
    for k, v in fields.items():
        if k not in allowed:
            raise KeyError(k)
        sets.append(f"{k}=?")
        args.append(json.dumps(v) if k == "summary" and v is not None else v)
    con.execute(f"UPDATE runs SET {', '.join(sets)}, updated_ns=? WHERE id=?", [*args, _now(), run_id])
    return get_run(con, run_id)
