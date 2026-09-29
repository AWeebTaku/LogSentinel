# LogSentinel

LogSentinel is a real-time log anomaly detection system. It ingests a stream of application/system
logs, parses and vectorizes them, scores them with unsupervised machine-learning models (trained
only on normal traffic — no labeled attacks required), and raises alerts through a REST API and a
web dashboard.

## Features

- **Streaming ingestion** over Apache Kafka: a replayable producer feeds raw log lines through a
  parsing → feature-extraction → scoring pipeline in real time.
- **Unsupervised detection**: Isolation Forest, PCA reconstruction error, and a small autoencoder,
  all trained on normal sessions only, behind one common model interface.
- **Log template parsing** with Drain, so scoring is robust to the noisy, high-cardinality text
  in raw log lines.
- **Operator web UI** (React + IBM Carbon) with a live dashboard, an alert inbox (acknowledge /
  resolve / mark false-positive), source/replay controls, and model management.
- **REST API** (FastAPI) backing the UI and available for external integration — see
  [docs/api.md](docs/api.md).
- **SQLite storage** for alerts, model registry, and run metadata — no external database needed.
- **One-command launcher** (`main.py`) that builds the UI, starts Kafka, and starts the API.

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
promote a new bundle without restarting the stream.

## Requirements

- **Python 3.12+**
- **Node.js + npm** (for building the web UI; a current LTS release)
- **Java 17** for Kafka — on Linux x86-64, `main.py` downloads and verifies a private copy
  automatically; other platforms need Java installed manually or via Docker (see below)
- ~250 MB free disk space if you plan to download the sample datasets for training

## Setup

### Linux (x86-64) — native, recommended

```bash
git clone <this-repo-url> logsentinel
cd logsentinel
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -e .
```

Run everything (UI build + Kafka + API):

```bash
python main.py
```

Then open <http://127.0.0.1:8000>. The launcher downloads a checksum-verified Java 17 + Kafka
3.9.1 under `~/.local/share/logsentinel` on first run, builds the UI if needed, and prints a
"ready" message once the API is up.

To run without Kafka/streaming (UI + API only):

```bash
python main.py --no-streaming
```

### macOS

Native Kafka bootstrap (`scripts/kafka.sh`) targets Linux. On macOS, use Docker Compose for Kafka
and run the app itself natively. (`docker-compose.yml` has not been exercised on a real Mac by
the maintainer — the tested path is `scripts/kafka.sh` on Linux — but its config is a standard
single-node KRaft broker on the same port the app expects.)

```bash
git clone <this-repo-url> logsentinel
cd logsentinel
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -e .

docker compose up -d          # starts Kafka on 127.0.0.1:9092
python main.py --no-streaming # start the UI/API
# once Kafka is confirmed up, streaming features (Source page, live engine) work
# against it without needing scripts/kafka.sh
```

(Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) for macOS.)

### Windows

The native Kafka bootstrap script is a Bash script using Linux-only process controls, so Windows
needs one of:

- **WSL2 (recommended)**: install a WSL2 Ubuntu distribution, then follow the **Linux** steps
  above inside it.
- **Docker Desktop + native Python**: follow the **macOS** steps above — Docker Compose for Kafka,
  native `python main.py --no-streaming` for the app — from PowerShell or Command Prompt.

## Optional: datasets and model training

Streaming and the Source/Models UI pages need a trained model bundle. Download the sample dataset
and train one:

```bash
make data      # downloads and prepares HDFS/BGL sample data (~244 MB)
python -m logsentinel.models.train --dataset hdfs --parser drain --model pca
python -m logsentinel.stream.pools
```

## Testing

```bash
make test                            # Python unit tests
make lint                            # ruff
cd ui && npm test && npm run typecheck
pytest -m e2e                        # needs a running Kafka broker
```

## Project structure

```
logsentinel/
├── main.py                  # one-command launcher: builds UI, starts Kafka, starts the API
├── pyproject.toml           # package metadata + dependency list (pip install -e .)
├── requirements.txt         # plain pip-installable dependency list
├── Makefile                 # make data / make test / make lint / make ui shortcuts
├── docker-compose.yml       # Kafka via Docker, for platforms without scripts/kafka.sh
├── scripts/kafka.sh         # native (no-Docker) Kafka bootstrap for Linux x86-64
├── configs/data.yaml        # dataset download/split configuration
├── docs/
│   ├── api.md               # REST API endpoints and lifecycle
│   └── ui.md                # UI behavior and local frontend development
├── src/logsentinel/         # the application package
│   ├── data/                 # dataset download, HDFS/BGL loaders, session building, splits
│   ├── parsing/               # log line normalization and Drain-based template parsing
│   ├── features/              # TF-IDF / count vectorization over parsed templates
│   ├── models/                # detector implementations, thresholds, training, model registry
│   ├── stream/                 # Kafka producer/consumer, the streaming engine, session state
│   ├── alerts/                 # the alert sink service that persists detections
│   ├── api/                     # FastAPI app: alerts, models, runs, serves the built UI
│   ├── store/                   # SQLite access layer
│   ├── common/                  # shared config, logging, environment-capture helpers
│   └── experiments/             # offline evaluation and benchmark harness (used to produce
│                                 # the research results; not required to run the application)
├── ui/                       # React + TypeScript + IBM Carbon web frontend (built by main.py)
│   ├── src/                   # pages, components, API client
│   └── e2e/smoke.mjs          # Playwright end-to-end smoke test
└── tests/                    # pytest unit and integration tests
```

`src/logsentinel/experiments/` and its outputs, the research paper, the defense deck, and detailed
experiment result docs are kept in the project's private/thesis copy and are not part of this
public repository — they aren't needed to install or run the application.

## Deployment note

LogSentinel is built for local/trusted-network use: the API has no authentication. A public
deployment would need an authenticated HTTPS reverse proxy, secured Kafka connectivity, and
persistent storage configured for the API, models, and database — none of that is set up here.
