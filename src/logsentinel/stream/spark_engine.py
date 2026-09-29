"""Spark Structured Streaming arm (E6): the same detection logic as stream/engine.py, expressed in Spark.

    python -m logsentinel.stream.spark_engine --bundle models/hdfs-drain-pca-early --expected-rows N --run-dir DIR

Kafka logs-raw -> SQL parse -> mapInPandas (line -> feature column, vectorized per Arrow batch) -> event-time watermark ->
applyInPandasWithState per session key (counts, incremental scoring gated by --min-lines, alert once, event-time age check)
-> Kafka alerts-critical. Spark's per-key API cannot batch the scoring across sessions the way the Python engine does, so
each key is scored with a small NumPy routine that reproduces the sklearn path exactly (tested).

Known differences from the Python engine (they matter when comparing results):
  * no end-of-stream flush: sessions younger than the age when the stream stops never get their age check;
  * the age-check alert has no meaningful "trigger line", so only incremental alerts are compared on latency;
  * the watermark is global across the micro-batch, not per worker.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("JAVA_HOME", str(Path.home() / ".local/share/logsentinel/jdk"))

KAFKA_PKG = "org.apache.spark:spark-sql-kafka-0-10_2.13:{v}"
_W: dict = {}          # per Python worker process: loaded scorer and numpy tables


# ---- scoring: single-vector NumPy versions of the sklearn path (unit-tested against it) ---------------------------

def tfidf_vec(counts: np.ndarray, idf: np.ndarray) -> np.ndarray:
    """sklearn TfidfTransformer(sublinear_tf=True) for one dense count vector (L2 normalized)."""
    tf = np.where(counts > 0, 1.0 + np.log(np.maximum(counts, 1)), 0.0)
    v = tf * idf
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def pca_spe(x: np.ndarray, mean: np.ndarray, V: np.ndarray) -> float:
    c = x - mean
    p = V @ c
    return max(0.0, float(c @ c - p @ p))


def ae_mse(x: np.ndarray, coefs: list, intercepts: list) -> float:
    a = x
    for W, b in zip(coefs[:-1], intercepts[:-1], strict=True):
        a = np.maximum(a @ W + b, 0.0)
    out = a @ coefs[-1] + intercepts[-1]
    return float(np.mean((out - x) ** 2))


def _load(bundle_dir: str) -> dict:
    if not _W:
        from ..models.bundle import Bundle, Scorer
        b = Bundle.load(Path(bundle_dir))
        sc = Scorer(b)
        e = b.early
        _W.update(scorer=sc, n_cols=sc.n_cols, thr=b.threshold, idf=b.tfidf.idf_.astype(np.float64),
                  mean=b.detector.mean.astype(np.float64), V=b.detector.V.astype(np.float64),
                  early=e, age=e.age_s if e else None)
        if e:
            _W.update(e_thr=e.threshold, e_idf=e.tfidf.idf_.astype(np.float64), e_coefs=[w.astype(np.float64) for w in e.detector.m.coefs_],
                      e_int=[i.astype(np.float64) for i in e.detector.m.intercepts_])
    return _W


def score_session(counts: np.ndarray) -> float:
    w = _W
    return pca_spe(tfidf_vec(counts, w["idf"]), w["mean"], w["V"])


def score_snapshot(counts: np.ndarray) -> float:
    w = _W
    return ae_mse(tfidf_vec(counts, w["e_idf"]), w["e_coefs"], w["e_int"])


# ---- Spark pieces -------------------------------------------------------------------------------------------------

def make_functions(bundle_dir: str, min_lines: int, run_id: str, model_name: str):
    from pyspark.sql.streaming.state import GroupState  # noqa: F401  (type only)

    def featurize(batches):
        """mapInPandas: rows (key, t, l, log_t, event_time) -> adds `col` (feature column) computed per line."""
        w = _load(bundle_dir)
        line_col = w["scorer"].line_col
        for pdf in batches:
            pdf = pdf.copy()
            pdf["col"] = np.fromiter((line_col(x) for x in pdf["l"]), dtype=np.int32, count=len(pdf))
            yield pdf

    def step(key, pdf_iter, state):
        import pandas as pd
        w = _load(bundle_dir)
        n_cols, age = w["n_cols"], w["age"]
        k = key[0]
        if state.exists:
            counts_b, snap_b, n, first_log, last_send, alerted, checked = state.get
            counts = np.frombuffer(counts_b, dtype=np.int32).astype(np.float64)
            snap = np.frombuffer(snap_b, dtype=np.int32).astype(np.float64)
        else:
            counts, snap = np.zeros(n_cols), np.zeros(n_cols)
            n, first_log, last_send, alerted, checked = 0, None, 0, False, False
        out = []

        def alert(kind, score, thr, evidence, t_send):
            out.append({"key": k, "value": json.dumps({
                "id": k, "kind": kind, "score": score, "threshold": thr, "n_lines": int(n), "evidence_log_s": evidence,
                "t_trigger_send_ns": int(t_send), "run": run_id, "model": model_name, "worker": 0})})

        dbg = os.environ.get("LOGSENTINEL_SPARK_DEBUG")
        if dbg:
            with open(dbg, "a") as f:
                f.write(json.dumps({"key": k, "timed_out": bool(state.hasTimedOut), "n": int(n), "alerted": bool(alerted),
                                    "checked": bool(checked), "wm_ms": int(state.getCurrentWatermarkMs()),
                                    "snap_score": score_snapshot(snap) if (state.hasTimedOut and age is not None and snap.sum() > 0) else None,
                                    "e_thr": w.get("e_thr")}) + "\n")
        if state.hasTimedOut:                                         # event-time age check
            if not alerted and not checked:
                s = score_snapshot(snap)
                if s >= w["e_thr"]:
                    alert("deadline", s, w["e_thr"], age, last_send)
                    alerted = True
            checked = True
        else:
            touched = False
            for pdf in pdf_iter:
                cols, logs, ts = pdf["col"].to_numpy(), pdf["log_t"].to_numpy(), pdf["t"].to_numpy()
                if first_log is None:
                    first_log = int(logs.min())
                np.add.at(counts, cols, 1.0)
                if age is not None:
                    np.add.at(snap, cols[logs - first_log <= age], 1.0)
                n += len(pdf)
                last_send = max(last_send, int(ts.max()))
                touched = True
            if touched and not alerted and n >= min_lines:
                s = score_session(counts)
                if s >= w["thr"]:
                    alert("incremental", s, w["thr"], 0, last_send)
                    alerted = True
        state.update((counts.astype(np.int32).tobytes(), snap.astype(np.int32).tobytes(), int(n), int(first_log or 0),
                      int(last_send), bool(alerted), bool(checked)))
        if age is not None and not checked and first_log is not None:
            # fires once the watermark passes first line + age. Spark rejects a timeout earlier than the current watermark
            # (a session that started behind it is already due), so clamp to just after it: due at the next batch.
            state.setTimeoutTimestamp(max((first_log + age + 1) * 1000, state.getCurrentWatermarkMs() + 1))
        yield pd.DataFrame(out, columns=["key", "value"]) if out else pd.DataFrame({"key": [], "value": []}, dtype=str)

    return featurize, step


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--bootstrap", default="127.0.0.1:9092")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--run-id", default="spark")
    ap.add_argument("--expected-rows", type=int, default=0, help="stop after this many Kafka rows (events plus EOS markers)")
    ap.add_argument("--timeout-s", type=float, default=600.0)
    ap.add_argument("--min-lines", type=int, default=10)
    ap.add_argument("--cores", type=int, default=2, help="local[N]")
    ap.add_argument("--shuffle-partitions", type=int, default=2)
    ap.add_argument("--max-offsets-per-trigger", type=int, default=50_000)
    ap.add_argument("--ready-file", default=None)
    ap.add_argument("--spark-version", default=None)
    a = ap.parse_args()

    import pyspark
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.streaming.state import GroupStateTimeout
    from pyspark.sql.types import (
        BinaryType,
        BooleanType,
        IntegerType,
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    run_dir = Path(a.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(run_dir / "checkpoint", ignore_errors=True)   # always start clean: an old checkpoint resumes old offsets/state
    ver = a.spark_version or pyspark.__version__
    py = sys.executable                                   # workers MUST run the same interpreter as the driver
    os.environ["PYSPARK_PYTHON"] = os.environ["PYSPARK_DRIVER_PYTHON"] = py
    spark = (SparkSession.builder.master(f"local[{a.cores}]").appName("logsentinel-spark")
             .config("spark.jars.packages", KAFKA_PKG.format(v=ver)).config("spark.ui.enabled", "false")
             .config("spark.sql.shuffle.partitions", str(a.shuffle_partitions)).config("spark.driver.memory", "2g")
             .config("spark.pyspark.python", py).config("spark.pyspark.driver.python", py)
             .config("spark.sql.streaming.stateStore.maintenanceInterval", "60s")
             .config("spark.sql.execution.arrow.maxRecordsPerBatch", "20000").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    model_name = Path(a.bundle).name
    featurize, step = make_functions(a.bundle, a.min_lines, a.run_id, model_name)

    raw = (spark.readStream.format("kafka").option("kafka.bootstrap.servers", a.bootstrap).option("subscribe", "logs-raw")
           .option("startingOffsets", "earliest").option("maxOffsetsPerTrigger", a.max_offsets_per_trigger)
           .option("failOnDataLoss", "false").load())
    parsed = (raw.select(F.col("key").cast("string").alias("key"), F.from_json(F.col("value").cast("string"), "i long, t long, l string, eos int").alias("m"))
              .select("key", F.col("m.t").alias("t"), F.col("m.l").alias("l")).where(F.col("l").isNotNull()))
    # HDFS line prefix "YYMMDD HHMMSS" -> seconds on the same scale as stream/wire.py:hdfs_log_time
    log_t = ((F.substring("l", 5, 2).cast("int") + 31 * F.substring("l", 3, 2).cast("int") + 372 * F.substring("l", 1, 2).cast("int")) * 86400
             + F.substring("l", 8, 2).cast("int") * 3600 + F.substring("l", 10, 2).cast("int") * 60 + F.substring("l", 12, 2).cast("int"))
    enriched = parsed.withColumn("log_t", log_t.cast("long")).withColumn("event_time", F.timestamp_seconds("log_t"))
    in_schema = StructType([StructField("key", StringType()), StructField("t", LongType()), StructField("l", StringType()),
                            StructField("log_t", LongType()), StructField("event_time", TimestampType()), StructField("col", IntegerType())])
    featured = enriched.mapInPandas(featurize, schema=in_schema).withWatermark("event_time", "0 seconds")
    # bytes, not arrays: PySpark 4.2 fails to deserialize an ArrayType in the state schema (KeyError: 'elementType')
    state_schema = StructType([StructField("counts", BinaryType()), StructField("snap", BinaryType()),
                               StructField("n", LongType()), StructField("first_log", LongType()), StructField("last_send", LongType()),
                               StructField("alerted", BooleanType()), StructField("checked", BooleanType())])
    alerts = featured.select("key", "t", "log_t", "event_time", "col").groupBy("key").applyInPandasWithState(
        step, "key string, value string", state_schema, "update", GroupStateTimeout.EventTimeTimeout)
    q = (alerts.writeStream.format("kafka").option("kafka.bootstrap.servers", a.bootstrap).option("topic", "alerts-critical")
         .option("checkpointLocation", str(run_dir / "checkpoint")).outputMode("update").start())

    seen: dict[int, dict] = {}
    rows_total, ready, t0 = 0, False, time.time()
    try:
        while q.isActive and time.time() - t0 < a.timeout_s:
            for p in q.recentProgress:
                if p["batchId"] not in seen:
                    seen[p["batchId"]] = p
            if q.lastProgress and not ready:
                ready = True
                if a.ready_file:
                    Path(a.ready_file).write_text("1")
            rows_total = sum(p["numInputRows"] for p in seen.values())
            if a.expected_rows and rows_total >= a.expected_rows:
                zero = [p for p in seen.values() if p["numInputRows"] == 0 and p["batchId"] > max(b for b, p2 in seen.items() if p2["numInputRows"] > 0)]
                if zero:
                    break
            time.sleep(0.3)
    finally:
        for p in q.recentProgress:
            seen.setdefault(p["batchId"], p)
        q.stop()
        stats = {"rows": rows_total, "wall_s": time.time() - t0, "batches": [
            {"id": p["batchId"], "rows": p["numInputRows"], "ts": p["timestamp"], "dur_ms": p["batchDuration"] if "batchDuration" in p else p["durationMs"].get("triggerExecution"),
             "stages": p["durationMs"]} for p in sorted(seen.values(), key=lambda x: x["batchId"])], "spark": ver}
        (run_dir / "spark.stats.json").write_text(json.dumps(stats))
        spark.stop()


if __name__ == "__main__":
    main()
