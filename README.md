# LogSentinel

LogSentinel is a real-time log anomaly detection system. It ingests a stream of application/system
logs, parses them into templates, vectorizes them, and scores them with unsupervised machine-learning
models — trained only on normal traffic, with no labeled attacks required — to raise alerts through a
REST API and a live operator dashboard.

It was built as both a working application and a measurement instrument: every part of the pipeline
(ingestion, parsing, scoring, alerting) is timed and counted, so throughput, latency, and detection
quality are things the app actually produces, not numbers asserted in a slide deck.

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

## Requirements

| Requirement | Why | Notes |
|---|---|---|
| **Python 3.12+** | runs the API, streaming engine, and ML pipeline | see per-OS install steps below |
| **Node.js 20.19+ (LTS 22 or 24 recommended)** | builds the web UI | Vite 8 refuses to run on older Node |
| **Java 17** | required by Kafka | auto-downloaded on native Linux x86-64; not needed on your host if you use Docker Compose, since it runs inside the container |
| **git** | cloning the repo | |
| **~250 MB free disk** | sample datasets (HDFS_v1 + BGL) | only needed if you train a model / run streaming |
| **~1.5 GB free disk** | Python venv + Node modules + Kafka/JDK download | |
| **~3 GB free disk, optional** | Thunderbird dataset | only if you opt into it — not needed for streaming/the demo, offline experiments only |

**Supported setups at a glance:**

| OS | Kafka / streaming | Notes |
|---|---|---|
| Linux x86-64 (Ubuntu, Debian, Fedora, Arch, …) | native, no Docker | fully tested path |
| macOS | Docker Compose | app runs natively; Kafka runs in a container |
| Windows | WSL2 (recommended) or Docker Compose | native Windows Python is not recommended — see below |

---

## 1. Install Python 3.12

Pick your platform. Skip this section if `python3.12 --version` (or `python3 --version` showing
3.12+) already works.

### Ubuntu / Debian

```bash
sudo apt update
# Ubuntu 24.04+/Debian 13+ ship 3.12 directly:
sudo apt install -y python3.12 python3.12-venv python3.12-dev git build-essential

# Older Ubuntu/Debian: add the deadsnakes PPA first (Ubuntu only)
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev git build-essential
```

### Fedora / RHEL / CentOS Stream

```bash
sudo dnf install -y python3.12 git @development-tools
```

### Arch Linux / Manjaro

Arch's `python` package tracks the latest CPython release, which usually satisfies `>=3.12` on its
own:

```bash
sudo pacman -Sy python python-pip git base-devel
python --version   # confirm it's 3.12 or newer
```

If you need exactly 3.12 (e.g. Arch has already moved to 3.13+), use
[pyenv](https://github.com/pyenv/pyenv) instead:

```bash
sudo pacman -S pyenv   # or the install script: curl https://pyenv.run | bash
pyenv install 3.12.14
pyenv local 3.12.14     # sets this version for the logsentinel/ directory
```

> **pyenv gotcha:** `pyenv install` does not automatically make `python3.12` runnable as a bare
> command. If `python3.12 -m venv .venv` fails with "command not found" even though
> `pyenv versions` lists 3.12.x, either run `pyenv global 3.12.14` (or `pyenv local 3.12.14` inside
> the repo) first, or call the interpreter directly:
> `~/.pyenv/versions/3.12.14/bin/python3.12 -m venv .venv`.

### openSUSE

```bash
sudo zypper install -y python312 python312-devel git patterns-devel-base-devel_basis
```

### macOS

```bash
# Install Homebrew first if you don't have it: https://brew.sh
brew install python@3.12 git
```

### Windows

Only needed if you're going the **native Windows Python** route (Docker Compose for Kafka — see
the Windows section below). If you're using **WSL2** (recommended), install Python inside the WSL2
Ubuntu distro using the Ubuntu/Debian instructions above instead.

```powershell
winget install -e --id Python.Python.3.12
```

or download the installer from [python.org/downloads](https://www.python.org/downloads/) and make
sure "Add python.exe to PATH" is checked during install.

---

## 2. Install Node.js

Needed everywhere the UI is built. The easiest cross-platform option is
[nvm](https://github.com/nvm-sh/nvm) (Linux/macOS) or
[nvm-windows](https://github.com/coreybutler/nvm-windows) (Windows), since distro package managers
often ship an outdated Node that Vite 8 will refuse to run.

### Linux (any distro) / macOS — via nvm

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
# restart your shell, then:
nvm install 22
nvm use 22
```

### Linux — via distro package manager (alternative)

```bash
# Ubuntu / Debian (NodeSource, gives a current LTS — apt's own nodejs package is usually too old)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Fedora
sudo dnf module install -y nodejs:22

# Arch Linux (Arch ships a current Node already)
sudo pacman -S nodejs npm
```

### macOS — via Homebrew (alternative)

```bash
brew install node@22
```

### Windows

```powershell
winget install -e --id OpenJS.NodeJS.LTS
```

or via nvm-windows, or inside WSL2 using the Linux instructions above.

---

## 3. Clone and install LogSentinel

Same on every platform once Python and Node are ready. On native Windows PowerShell, replace
`source .venv/bin/activate` with `.venv\Scripts\Activate.ps1` and use `python` instead of `python3.12`
if that's what `winget`/the installer put on your PATH.

```bash
git clone https://github.com/AWeebTaku/LogSentinel.git logsentinel
cd logsentinel

python3.12 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -e .

# optional, only needed for running tests/lint (pytest, ruff):
python -m pip install -e '.[dev]'
```

---

## 4. Set up Kafka

This step only gets Kafka itself ready. How to actually start and use the app (which launches
Kafka for you on Linux) is step 6, once you have a trained model to run it against.

### Linux x86-64 (native, recommended, no Docker)

Nothing to install manually — `python main.py` (step 6) bootstraps a checksum-verified Java 17 +
Kafka 3.9.1 under `~/.local/share/logsentinel` on first run. If you'd rather drive Kafka directly:

```bash
scripts/kafka.sh setup     # one-time: download + verify JDK 17 and Kafka
scripts/kafka.sh start     # start the broker
scripts/kafka.sh status    # check it's up
scripts/kafka.sh stop      # stop it
scripts/kafka.sh reset     # wipe local broker storage (see Troubleshooting below)
```

### macOS

The native Kafka bootstrap script downloads Linux x86-64 binaries, so it doesn't run on macOS.
Use Docker Compose instead; the app itself still runs natively:

```bash
# Install Docker Desktop first: https://www.docker.com/products/docker-desktop/
docker compose up -d               # starts Kafka on 127.0.0.1:9092
```

Once it's up (`docker compose ps`), the app's Source/Dashboard streaming features work against it
normally in step 6 — it only needs something listening on `127.0.0.1:9092`, it doesn't care
whether that's the native bootstrap or a container. (`main.py`'s own Kafka bootstrap is Linux-only,
so pass `--no-streaming` to any `python main.py` command in step 6 — Kafka's already up via Docker.)

Stop it with `docker compose down` when done.

### Windows

The native Kafka bootstrap script is a Bash script using Linux-only process controls
(`taskset`), and `confluent-kafka`'s Python C-extension is far better supported on Linux/macOS
than on native Windows. For both reasons, **WSL2 is the recommended path**; native
Windows + Docker works but is less exercised.

**Option A — WSL2 (recommended):**

```powershell
wsl --install                      # installs WSL2 + Ubuntu; reboot if prompted
```

Then open the Ubuntu shell and follow the **Ubuntu/Debian** instructions from steps 1–4 above
exactly as if it were native Linux — WSL2 Ubuntu is x86-64 Linux as far as this project is
concerned, so `python main.py` (step 6) works with the same automatic Kafka bootstrap.

**Option B — native Windows + Docker Desktop:**

```powershell
# Install Docker Desktop first: https://www.docker.com/products/docker-desktop/
docker compose up -d
```

Same as macOS: pass `--no-streaming` to any `python main.py` command in step 6.

---

## 5. Download the sample dataset and train a model

The UI and API run without any dataset, but the Source/Models pages and live streaming need a
trained model bundle. This downloads and MD5-verifies HDFS_v1 + BGL from LogHub (~244 MB combined)
and builds time-ordered train/val/test session splits:

```bash
make data
```

Equivalent, if you don't have `make` (e.g. native Windows PowerShell):

```bash
python -m logsentinel.data.download      # downloads data/raw/{HDFS_v1,BGL}.zip, verifies MD5, extracts
python -m logsentinel.data.build         # writes data/processed/*.sessions.jsonl.gz (train/val/test splits)
```

`download.py` also supports fetching a subset, or the optional, much larger Thunderbird dataset:

```bash
python -m logsentinel.data.download --only hdfs      # just HDFS_v1 (~187 MB)
python -m logsentinel.data.download --only bgl        # just BGL (~57 MB)
```

**Thunderbird is opt-in and not needed for streaming, training, or the demo** — HDFS is the only
dataset the live app (Source/Models/streaming) actually uses. It's only relevant if you want to
reproduce the offline detection-quality experiments (`logsentinel.experiments.offline`) across all
three datasets. It's also much bigger: the full corpus is ~2 GB compressed / ~30 GB raw, so
`download.py` streams only a configurable line prefix and stops — no MD5 check, since the archive is
never fully read. The default prefix (`configs/data.yaml`, `thunderbird.max_lines`) is 20,000,000
lines (~2-3 weeks of logs), which downloads to **~3 GB** on disk:

```bash
python -m logsentinel.data.download --only thunderbird          # uses the configured default (20M lines)
python -m logsentinel.data.build --only thunderbird              # writes data/processed/thunderbird.*.sessions.jsonl.gz

# or a smaller/larger prefix explicitly:
python -m logsentinel.data.download --only thunderbird --tb-lines 5000000
```

Train a model bundle (default: HDFS_v1, Drain parser, PCA detector, validation-tuned threshold):

```bash
python -m logsentinel.models.train --dataset hdfs --parser drain --model pca
```

Or the fuller bundle with an "early/incomplete session" detector attached (recommended for a live
demo — HDFS sessions can live for hours, so this catches anomalies visible in only the first few
log lines):

```bash
python -m logsentinel.models.train --dataset hdfs --parser drain --model pca \
  --early-age 30 --early-model ae --out models/hdfs-drain-pca-early
```

Build the anomaly pool used by admin's "Inject anomaly burst" button:

```bash
python -m logsentinel.stream.pools
```

Finally, register and activate the bundle so the streaming engine actually uses it — no need for
the app to be running yet:

```bash
python -m logsentinel.promote models/hdfs-drain-pca-early --to data/logsentinel.db
```

(Or, once the app is running — step 6 — do the same thing from the admin UI's Models page:
register the bundle folder, then click **Activate**.)

---

## 6. Run the app — operator vs. admin

Two roles, two separate single-page apps, one Makefile command each:

- **Admin** — whoever *builds and maintains* the system: trains and validates models, runs test
  replays, reviews benchmark experiments. `make staging` → `http://localhost:8000/admin.html`.
  Full suite: Source replay (with scenario/injection controls), Models, Experiments, plus
  Dashboard and Alerts for context.
- **Operator** — whoever's job is just to *watch* the system run (a SOC/NOC analyst, whoever's on
  alert-triage duty, not necessarily the same person who set it up). `make production` →
  `http://localhost:8001/`. Dashboard, Alerts, and a trimmed Source page that only ever
  starts/stops its own engine — no training, no testing, no injection, no model picker (it always
  runs whatever was promoted to it). Those stay admin-only, refused server-side even by a direct
  API call, not just hidden in the nav.

Just want to see it work? `make staging`, open `http://localhost:8000/admin.html`, go to Source
and click **Start source** — that alone replays real HDFS logs through the whole pipeline and
raises real alerts, no second instance or external generator needed. The rest of this section is
for running it the way an actual deployment would: operator and admin genuinely separated.

`make staging` and `make production` are genuinely separate instances — each gets its own Kafka
broker, database, and model directory (`LOGSENTINEL_KAFKA_PORT`, `LOGSENTINEL_TOOLS`,
`LOGSENTINEL_DB` under the hood, see the Makefile) — so nothing one does can affect the other, and
a model trained in staging does **not** automatically reach production. Two things cross the gap
deliberately:

**Promoting a model**, once you're satisfied with its metrics on the admin Models page:
```bash
make promote BUNDLE=models/<bundle-name>
```
Registers it in production's own database and activates it — no need for production's API to be
reachable or switched out of operator mode. Both instances already share the same `models/` folder
on one machine, so there's nothing to copy; across separate machines, copy/rsync the bundle
directory first.

**Log traffic.** There's no real log shipper wired up yet, so operator's "Start source" never
produces anything itself (unlike admin's bounded test replay) — it only starts the detection
engine, watching whatever is already arriving on Kafka's `logs-raw` topic. To actually see it do
something, run an external generator that stands in for a real system producing logs, pointed at
the *same* Kafka broker as whichever instance you want fed:
```bash
LOGSENTINEL_KAFKA_PORT=9192 make live-feed     # feeds production (port 9192, per `make production`)
make live-feed                                 # feeds staging (default port 9092)
```
It runs forever (real HDFS log lines, reshuffled each lap, no fixed end) until you stop it —
exactly like a real external process would. When a real log shipper exists, it publishes to the
same topic and nothing else changes.

Putting it together, four terminals:

```bash
make staging                                    # admin UI, terminal 1
make production                                 # operator UI, terminal 2 (own Kafka + DB)
LOGSENTINEL_KAFKA_PORT=9192 make live-feed       # external log generator, terminal 3, feeding production
make promote BUNDLE=models/<bundle-name>         # terminal 4, once you've trained/picked a model in staging
```

`make production`'s `--app-mode operator` makes the backend itself refuse every train/inject/
experiment route (404) — starting/stopping its own engine stays available (that's an operator
action), but nothing that tests or trains is ever reachable, even by a direct API call. On two
separate machines, just run one instance per machine with the right `--app-mode`; none of the port/
env-var juggling matters since each machine only ever runs one instance.

Run `make clean` (or `python -m logsentinel.cleanup`, same thing) any time for a dry-run report of
old run history, trained model bundles, and generated data — it shows exactly what's there, with
sizes and ages, and deletes nothing until you add `--yes`. See `python -m logsentinel.cleanup
--help`.

The API's interactive docs are at `<host>/docs` on whichever instance (e.g.
<http://127.0.0.1:8000/docs>). Other `main.py` flags (used directly, or see the Makefile for how
`staging`/`production` set them): `--port 8080` (default 8000), `--no-build` (reuse an existing
`ui/dist` instead of rebuilding it), `--no-streaming` (skip Kafka, UI + API only).

---

## 7. Testing

```bash
python -m pip install -e '.[dev]'     # once, installs pytest/ruff/httpx2

make test                              # Python unit tests
make lint                              # ruff
cd ui && npm test && npm run typecheck # UI unit tests + type-checking

pytest -m e2e                          # needs a running Kafka broker (scripts/kafka.sh start / docker compose up)
```

---

## Troubleshooting

- **`python3.12: command not found` but pyenv/asdf shows it installed** — the version manager
  hasn't put it on `PATH` as a runnable command yet. Run `pyenv global 3.12.14` (or `pyenv local
  3.12.14` inside the repo), or call the interpreter by its full path, e.g.
  `~/.pyenv/versions/3.12.14/bin/python3.12 -m venv .venv`.
- **Dashboard shows `n/a` for throughput/lag and 0 alerts even though a source is "running"** —
  usually a stale Kafka broker: if the local broker has been running across many restarts/sessions,
  its topic metadata can get out of sync (you may see a log line like
  `Topic alerts-critical ... partition count changed from 3 to 0`). Fix: stop everything, then wipe
  the local broker storage and let it recreate topics fresh:
  ```bash
  scripts/kafka.sh stop
  rm -rf ~/.local/share/logsentinel/kafka-data ~/.local/share/logsentinel/kafka-logs
  make staging      # or: python main.py
  ```
- **Port 8000 (or 8001) already in use** — `make staging`/`make production` use fixed ports; call
  `python main.py --port 8080 --app-mode full` directly for a different one, or find and stop
  whatever's using the port (`lsof -i :8000` / `ss -ltnp | grep 8000` on Linux).
- **`make data` fails partway through a download** — the download is resumable and MD5-checked;
  just re-run `make data` (or `python -m logsentinel.data.download`). It skips files that already
  match the expected checksum and only re-fetches the incomplete one.
- **Thunderbird download interrupted** — it's streamed rather than MD5-checked (the full archive is
  never read), and only renames its output into place once the requested line count is fully read.
  An interrupted run leaves no corrupt `Thunderbird.log`, just an incomplete `.part` file — re-run
  `python -m logsentinel.data.download --only thunderbird` from scratch.
- **`pip install confluent-kafka` fails to build** — this usually means no prebuilt wheel exists
  for your exact platform/Python combination and it's falling back to a source build that needs
  `librdkafka`. Install it via your package manager first (`sudo apt install librdkafka-dev` /
  `sudo dnf install librdkafka-devel` / `brew install librdkafka`) and re-run pip install. This is
  one more reason native Windows is not the recommended path — use WSL2 instead.
- **UI build fails with a Vite/Node error** — check `node --version`; Vite 8 needs Node 20.19+
  (22 or 24 LTS recommended). Update via nvm (`nvm install 22 && nvm use 22`).

---

## Deployment note

LogSentinel is built for local/trusted-network use: the API has no authentication. A public
deployment would need an authenticated HTTPS reverse proxy, secured Kafka connectivity, and
persistent storage configured for the API, models, and database — none of that is set up here.
