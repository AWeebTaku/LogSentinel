# Spark engine: status and how to use it if you ever need it

Not wired into the product. This is a note for later, not a how-to for today.

## What exists

`src/logsentinel/stream/spark_engine.py` (254 lines) is a second implementation of the detection
engine, written for the research paper's Python-vs-Spark comparison. It is real, working code, not
a stub:

- Reads `logs-raw` from Kafka via Spark Structured Streaming, parses lines, featurizes with
  `mapInPandas`, and scores each session with `applyInPandasWithState` (the same Drain/TF-IDF +
  PCA/IForest/AE scoring logic as the plain Python engine, `src/logsentinel/stream/engine.py`).
- Publishes alerts to the same `alerts-critical` Kafka topic the Python engine uses, in the same
  JSON shape. `logsentinel.alerts.sink` doesn't care which engine produced an alert, so if you ran
  it standalone, those alerts would already show up correctly in the DB and the Alerts UI.
- Uses Spark's own checkpointing (`<run-dir>/checkpoint`) for state recovery, though the current
  callers (`experiments/e6.py`, `experiments/harness.py`) always wipe it at the start of a run,
  so that recovery path has never actually been exercised end to end.

It is only ever invoked today from the benchmark/experiment scripts
(`src/logsentinel/experiments/e6.py`, `harness.py`) — never from `src/logsentinel/stream/source.py`,
which is what the UI's "Start a run" actually launches. There is no way to pick it from the app.

## What the benchmark found (why it's not wired in)

Running Spark in `local[N]` mode (one machine, a handful of threads) against the plain Python
engine, on this project's exact workload (Drain parsing + lightweight per-session scoring, not
heavy batch computation): Python sustained ~50,000 events/s; Spark local[2] sustained ~3,000, with
120-250x higher latency, on byte-identical detections. See
`../logsentinel-research/docs/comparative-study/` and the research paper's Spark comparison section
for the full numbers.

That result is real but narrow: it says Spark's overhead isn't worth it *at this scale, on one
machine* — not that Spark is never worth it. Spark's actual value is distributing work across a
cluster; a local-mode benchmark can't show that. See the chat discussion in this project's history
(2026-11-03) for the longer reasoning, summarized:

- Horizontal scale without Spark: Kafka partitions + more Python engine worker processes (the
  existing "Engine workers" setting) is the standard way to scale this kind of lightweight,
  per-key streaming work, and doesn't need Spark at all.
- Spark would only become genuinely worth adding if: log volume actually exceeds what a handful
  of Python processes can handle on the hardware available, or the deployment already has a real
  multi-node Spark cluster to run it on (not local mode) and wants to reuse that platform's ops
  tooling.
- Separately, the plain Python engine has its own real gap worth knowing about either way: Kafka
  offsets auto-commit on a timer and open-session state lives only in process memory, so a crash
  loses in-flight session context (not stored data — raw logs are still retained in Kafka, just
  the engine's own progress). Spark's checkpointing would handle that better if it were ever
  actually exercised (see "always wipes checkpoint" above).

## If you do want to wire it in later

Two things are missing for feature parity with the Python engine inside the actual app:

1. **No live metrics.** `spark_engine.py` never publishes to the `logsentinel-metrics` topic (no
   `rate_eps`/`lag`/`watermark`). Without that, the Dashboard would stay blank for a Spark-run
   source, and "Inject anomaly burst" would never work (it requires a recent watermark — see
   `POST /sources/{run_id}/inject` in `src/logsentinel/api/app.py`). Would need a periodic
   `foreachBatch` or a side producer publishing the same shape `engine.py`'s `publish_metrics`
   sends.
2. **No wiring to the product.** `StartSource` (`src/logsentinel/api/app.py`) and
   `src/logsentinel/stream/source.py` would need an engine-choice parameter, and `source.py` would
   need to branch between launching `logsentinel.stream.engine` and
   `logsentinel.stream.spark_engine`. The Source admin page would need a dropdown for it.

## Setup, if you want to run/benchmark it as-is today (outside the app)

- `pip install pyspark` — deliberately not in `requirements.txt`/`pyproject.toml` (it's heavy and
  only this file imports it, lazily, inside `main()`).
- Needs a JDK; it reuses whatever `scripts/kafka.sh setup` already fetched
  (`JAVA_HOME` defaults to `~/.local/share/logsentinel/jdk`, same JDK 17 Kafka itself uses — no
  separate install).
- No pinned PySpark version anywhere in this repo; whatever version `pip install pyspark` gives you
  is what was last validated against (the benchmark docs in `logsentinel-research/` note the
  specific version that produced those numbers).
- Invoke it the same way the experiments do:
  `python -m logsentinel.stream.spark_engine --bundle <bundle dir> --run-dir <dir> --run-id <id>
  [--cores N] [--shuffle-partitions N] [--max-offsets-per-trigger N]`
  — or just run `experiments/e6.py`/`harness.py` with the Spark engine variant, which already
  knows how to drive it (see `ENGINES` in `experiments/e6.py`).
