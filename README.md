# LogSentinel

LogSentinel is a real-time log anomaly detection application and research harness. It includes a FastAPI service,
a React/TypeScript operations UI, Kafka-backed streaming, model training, and offline experiments.

## Requirements

- Python 3.12 or newer
- Node.js and npm (Vite 8 requires a current Node.js release)
- Linux x86-64 for the included user-space Kafka bootstrap script; alternatively, use Docker Compose

The UI and API can run without datasets, trained models, or Kafka. Dataset downloads and generated models are only
needed for model training and streaming demos.

## Quick start

From a fresh clone, create an isolated Python environment and install the project:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Start the UI and API without Kafka:

```bash
python main.py --no-streaming
```

Open <http://127.0.0.1:8000>. The API's interactive documentation is at <http://127.0.0.1:8000/docs>.
The launcher installs UI dependencies from `ui/package-lock.json` and builds the UI on its first run. You can also
build it explicitly with `cd ui && npm ci && npm run build`.

## Enable streaming

The default launcher starts the full local stack, including Kafka and the alert sink:

```bash
python main.py
```

On Linux x86-64, the launcher bootstraps checksum-verified Java 17 and Kafka 3.9.1 under
`~/.local/share/logsentinel` the first time. To manage Kafka separately, run `scripts/kafka.sh setup` once, then
`scripts/kafka.sh start` and `scripts/kafka.sh stop`. Docker Compose is also provided in `docker-compose.yml`.

## Optional: data and model

Download and prepare the HDFS and BGL datasets (about 244 MB combined):

```bash
make data
```

Train an HDFS model bundle for streaming:

```bash
python -m logsentinel.models.train --dataset hdfs --parser drain --model pca
python -m logsentinel.stream.pools
```

Thunderbird is a much larger, opt-in dataset. See the downloader options with
`python -m logsentinel.data.download --help` before requesting it.

## Development checks

```bash
make test
make lint
cd ui && npm test && npm run typecheck
```

End-to-end tests require a running Kafka broker: `pytest -m e2e`.

## Project notes

- Data processing and split settings: [configs/data.yaml](configs/data.yaml)
- API endpoints and lifecycle: [docs/api.md](docs/api.md)
- UI behavior and local development: [docs/ui.md](docs/ui.md)
- Dataset caveats: [docs/threats-to-validity.md](docs/threats-to-validity.md)
- Research plan: [PLAN.md](PLAN.md)

## Deployment note

GitHub Pages cannot host the complete application: LogSentinel requires a Python API, Kafka for streaming, and
persistent storage for the database and model bundles. The API currently has no authentication and is intended for
local use; do not expose it directly to the public internet. A public deployment needs an authenticated HTTPS
reverse proxy, secured Kafka connectivity, and persistent storage configured for the API, models, and database.
