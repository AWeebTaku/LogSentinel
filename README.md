# LogSentinel

<!-- badges:start -->
[![CI](https://github.com/AWeebTaku/LogSentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/AWeebTaku/LogSentinel/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/AWeebTaku/LogSentinel/blob/main/LICENSE) ![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) ![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?logo=apachekafka&logoColor=white) ![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=white)
<!-- badges:end -->

LogSentinel is a real-time log anomaly detection system. It ingests a stream of application/system
logs, parses them into templates, vectorizes them, and scores them with unsupervised machine-learning
models — trained only on normal traffic, with no labeled attacks required — to raise alerts through a
REST API and a live operator dashboard.

It was built as both a working application and a measurement instrument: every part of the pipeline
(ingestion, parsing, scoring, alerting) is timed and counted, so throughput, latency, and detection
quality are things the app actually produces, not numbers asserted in a slide deck.

**New here?** See [Results](#results) below, or skip straight to [Quick start](#quick-start).

<details>
<summary><strong>Contents</strong></summary>

- [Results](#results)
- [Features](#features)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Testing](#testing)
- [More](#more)

</details>

## Results

One-page write-up with the key chart: **[aweebtaku.github.io/LogSentinel](https://aweebtaku.github.io/LogSentinel/)**
(built from [docs/index.html](docs/index.html), served by GitHub Pages).

Headline: on 69 matched runs, the plain-Python engine matched Spark's detections exactly while
sustaining ~50,000 events/s against Spark `local[2]`'s ~3,000 — 120-250x less added latency (see
[note.md](note.md) for the full caveat on what that result does and doesn't say about Spark at
cluster scale). The same page also reports detection quality (F1 per dataset/detector, including
where LogSentinel's classical detectors lose cleanly to sequence-aware LogBERT) and an honest
limits section — not just the favorable half.

## Features

- **Streaming ingestion** over Apache Kafka: a replayable producer feeds raw log lines through a
  parsing → feature-extraction → scoring pipeline in real time.
- **Unsupervised detection**: Isolation Forest, PCA reconstruction error, and a small autoencoder,
  all trained on normal sessions only, behind one common model interface.
- **Log template parsing** with Drain, so scoring is robust to the noisy, high-cardinality text in
  raw log lines instead of matching on raw strings.
- **Operator web UI** (React + IBM Carbon) with a live dashboard, an alert inbox (acknowledge /
  resolve / mark false-positive), source/replay controls, and model management.
- **REST API** (FastAPI) backing the UI and available for external integration — see
  [docs/app/api.md](docs/app/api.md) and [docs/app/ui.md](docs/app/ui.md).
- **SQLite storage** for alerts, the model registry, and run metadata — no external database to
  stand up.
- **One-command launcher** (`main.py`) that builds the UI, brings up Kafka, and starts the API —
  with separate `make staging`/`make production` targets for genuinely isolated admin/operator
  instances (own Kafka, own database), and `make live-feed` to simulate a real system producing logs.

## Architecture

```
producer/replay → Kafka (logs-raw) → parsing (Drain) → feature extraction → model scoring
                                                                                  │
                                                                                  ▼
                                                                          alerts-critical (Kafka)
                                                                                  │
                                                                                  ▼
                                                              alert sink → SQLite ← FastAPI ← Web UI
```

A trained model bundle (parser + vectorizer + detector + threshold) is produced offline by
`logsentinel.models.train` and loaded by the streaming engine at runtime; the UI and API can
register and promote a new bundle without restarting the stream.

A second, Spark Structured Streaming implementation of the same engine exists
(`src/logsentinel/stream/spark_engine.py`) but is **research-only, not wired into the app** — it
was built to benchmark Python vs. Spark at this project's scale, not to run in production here.
See [note.md](note.md) for what it does, the benchmark result, and what's missing to wire it in.

## Project structure

```
logsentinel/
├── main.py                  # one-command launcher: builds the UI, starts Kafka, starts the API
├── pyproject.toml           # package metadata + dependency list (pip install -e .)
├── requirements.txt         # plain pip-installable dependency list (mirrors pyproject.toml)
├── Makefile                 # make data/test/lint/ui, and staging/production/live-feed/promote/clean
├── docker-compose.yml       # Kafka via Docker, for platforms without scripts/kafka.sh
├── scripts/kafka.sh         # native (no-Docker) Kafka bootstrap for Linux x86-64
├── configs/data.yaml        # dataset download/split configuration
├── docs/
│   └── app/
│       ├── api.md           # REST API endpoints and lifecycle
│       └── ui.md            # UI behavior and local frontend development
├── src/logsentinel/         # the application package
│   ├── data/                 # dataset download, HDFS/BGL loaders, session building, splits
│   ├── parsing/               # log line normalization and Drain-based template parsing
│   ├── features/              # TF-IDF / count vectorization over parsed templates
│   ├── models/                # detector implementations, thresholds, training, model registry
│   ├── stream/                 # Kafka producer/consumer, the streaming engine, session state
│   ├── alerts/                 # the alert sink service that persists detections
│   ├── api/                     # FastAPI app: alerts, models, runs; serves the built UI
│   ├── store/                   # SQLite access layer
│   ├── common/                  # shared config, logging, environment-capture helpers
│   └── experiments/             # offline evaluation and benchmark harness (used to produce
│                                 # research results; not required to run the application)
├── ui/                       # React + TypeScript + IBM Carbon web frontend (built by main.py)
│   ├── src/                   # pages, components, API client
│   └── e2e/smoke.mjs          # Playwright end-to-end smoke test
└── tests/                    # pytest unit and integration tests
```

`src/logsentinel/experiments/` and its outputs, the research paper, the defense deck, and detailed
experiment result docs are kept in the project's private/thesis copy and are not part of this public
repository — they aren't needed to install or run the application.

## Quick start

Full per-OS install steps, Thunderbird details, Spark experiment setup, and troubleshooting live in
[docs/install.md](docs/install.md). This is the fast path on **Linux x86-64** (the fully-tested
platform — macOS/Windows notes are in that doc too).

Already have Python 3.12 + Node installed and the repo cloned? `make demo` builds the sample
dataset and a model if they're not already there, then launches the admin UI — open
`http://localhost:8000/`, go to Source, click **Start source**.

From scratch:

```bash
git clone https://github.com/AWeebTaku/LogSentinel.git logsentinel && cd logsentinel

python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -e '.[dev]'

make data                                   # downloads + builds HDFS_v1 + BGL sessions (~244 MB)
python -m logsentinel.models.train --dataset hdfs --parser drain --model pca \
  --early-age 30 --early-model ae --out models/hdfs-drain-pca-early
python -m logsentinel.stream.pools
python -m logsentinel.promote models/hdfs-drain-pca-early --to data/logsentinel.db

make staging                                # admin UI -> http://localhost:8000/
```

Open `http://localhost:8000/`, go to **Source**, click **Start source** — that replays real HDFS
logs through the full pipeline (Kafka, bootstrapped automatically on Linux) and raises real alerts
on the Dashboard.

Two roles exist beyond this: `make staging` (admin: train, test, inject) and `make production`
(operator: watch-only, its own Kafka/DB, no training/testing routes even via direct API call). See
[docs/install.md](docs/install.md#6-run-the-app--operator-vs-admin) for running them side by side,
feeding a real/simulated log source, promoting a model to production, and the feedback-retraining
loop.

---

## Testing

```bash
python -m pip install -e '.[dev]'     # once, installs pytest/ruff/httpx2

make test                              # Python unit tests
make lint                              # ruff
cd ui && npm test && npm run typecheck # UI unit tests + type-checking

pytest -m e2e                          # needs a running Kafka broker (scripts/kafka.sh start / docker compose up)
```

---

## More

- [docs/install.md](docs/install.md) — full per-OS setup, dataset details, troubleshooting, deployment note.
- [docs/app/api.md](docs/app/api.md) — REST API endpoints and lifecycle.
- [docs/app/ui.md](docs/app/ui.md) — UI behavior and local frontend development.
- [note.md](note.md) — Spark engine: what exists, the benchmark result, why it's research-only.
