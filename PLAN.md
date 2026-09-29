# LogSentinel — Project Plan: Real-Time Log Anomaly Detection App + Research Paper Data Engine

## 1. Context

Working title: **"Architecting an Elastic, High-Throughput Pipeline for Real-Time Distributed Log Analytics and Unsupervised Anomaly Detection"** (M.Sc. CS, Sem III–IV).

The goal is a fresh, product-style monitoring application. The application also has to be an instrument: every claim in the paper must be backed by numbers the app produces reproducibly. Earlier attempts made demos but did not produce defensible evidence, so the app is built around an experiment layer from day one.

Decisions taken: full product-style app · real LogHub data (HDFS_v1, BGL, Thunderbird) plus synthetic data for load tests · Kafka + Python consumers as the baseline engine, with Spark Structured Streaming as a compared variant · ~8 weeks.

## 2. What I found in the directory (audit)

| Item | What it is | Verdict |
|---|---|---|
| `Gemini Notebook.md` | Brainstorm of 4 capstone ideas, the chosen synopsis, lit review, methodology, 4-pane jury demo plan | Source of truth for **paper claims**. Keep as reference. |
| `Real-time distributed ... pipeline.txt` | Prompt + summary that generated `log-anomaly-pipeline/` | Requirements list is still good (see §3). |
| `Elastic ... thesis defense presentation.txt`, `.pptx` | Prompt + 10-slide deck | Benchmark slide is **illustrative placeholders** (its own summary says so). Must be regenerated from real results. |
| `Architecting ... .pdf/.docx` | Synopsis (abstract, scope, 10-ref lit review, methodology) | Paper skeleton. Same text as the Gemini notebook. |
| `log-anomaly-pipeline/` (+ `.zip`, same content) | Kafka (KRaft) + async producer + sklearn TF-IDF/IsolationForest + streaming consumer + alert service + benchmark suite (offline/e2e, threshold sweep). Synthetic HDFS-style data. | **Best prior attempt.** Good ideas to keep: shared `log_cleaner` (no train/serve skew), correlation IDs, offline vs e2e benchmark split, CSV+Markdown output. Weak: F1≈0.52 on synthetic data, per-record scoring, no real data. |
| `log-analytics-pipeline/` | Streamlit dashboard + Threat Simulator + Faker generator + `confluent-kafka` engine + unused `spark_processor.py` | **Demo quality, not research quality.** Details below. |
| `.venv`, `.claude_session` | Env / session artifacts | Ignore; do not carry over. |

Concrete defects in the second attempt (`log-analytics-pipeline`) that the new design must avoid:
- Model trained on 13 distinct messages ×100. The SQL-injection preset scored −0.4164 and was labeled "✅ OK" (its own `pipeline_alerts.json`), i.e. the detector does not detect the demo attack.
- Threshold `-0.55` is hard-coded in two files; no calibration, no labels, no metrics.
- Topic names are inconsistent (`system-logs`, `processed-logs-stream`), and `utilities/run_pipeline.py` points to files that do not exist.
- Spark code is never connected to the ML stage; the dashboard uses a JSON file as its "database"; the Threat Simulator bypasses Kafka entirely.
- `requirements.txt` is a full `pip freeze` (numpy 2.5 vs a model pickled elsewhere, etc.); the two attempts pin conflicting sklearn/numpy versions, so the `.joblib` files are not portable between them.

## 3. Gap analysis: paper claims vs. what exists

| Paper / slide claim | Status in existing code | What the new app must do |
|---|---|---|
| ≥ 50,000 events/s sustained | Producer tops out ~1–10k; engine transforms **one record at a time** | Micro-batch scoring (vectorize + score N records per call), multi-partition consumer group, measure honestly; report whatever is achieved with hardware specs |
| < 500 ms end-to-end latency | e2e mode exists, only tested on tiny loads | Latency percentiles at fixed load levels; separate broker, queueing, and model time |
| Spark/Flink Structured Streaming | Spark file is a windowed count only | Real Spark arm that runs the same model, compared against Python consumers |
| Drain template parsing | Not implemented (regex cleaner only) | Add Drain3 as the parser; ablate against regex cleaning |
| Isolation Forest **and** Autoencoder | Isolation Forest only | Add at least one comparator (Autoencoder or PCA/LOF baseline) |
| 3σ dynamic threshold | Percentile threshold from training data | Implement 3σ rule and compare to fixed percentile and label-tuned threshold |
| Concept-drift sliding window | Only a slide diagram | Implement periodic retrain/adapt; evaluate on a drift scenario |
| Horizontal scaling under spikes ("elastic") | 6-partition topic, single consumer | Scale consumers 1→N; spike-injection experiment |
| HDFS / Apache / CloudWatch data | Synthetic only | Real LogHub datasets |
| Accuracy | Line-level labels on synthetic data | HDFS_v1 labels are **per block session**, not per line: group by BlockId (session windows) and evaluate at session level |

Paper hygiene items to fix (do early, they are cheap):
- Scope says "exclude frontend" but the user now wants a full app → reword scope as "monitoring UI is a supporting artifact; evaluation focuses on pipeline and model".
- **Verify every citation** before it goes in the paper. Several entries (e.g. Bhimanapati & Chandu 2025, Trambadiya 2025, Gaikwad 2025, Le & Ivanov 2021, and venue/page details on LogClass and others) come from AI output and I cannot confirm them. Replace anything unverifiable with sources found via Google Scholar / DBLP; add the standard baselines (Loghub benchmark, "Deep Learning for Anomaly Detection in Log Data: A Survey", LogBERT, LogRobust, Drain).
- Regenerate the defense deck from real result files.

## 4. Product definition

**LogSentinel** ingests log streams, parses them, scores them with unsupervised models, raises alerts, and lets an operator triage. Everything measurable is exported for the paper.

User-facing features (product side):
1. Live dashboard: throughput, lag, latency percentiles, anomaly rate, score distribution.
2. Alert inbox: list, detail (raw log + parsed template + score + nearest normal template), acknowledge/resolve, false-positive marking (feeds evaluation and threshold tuning).
3. Source management: choose dataset / replay speed / synthetic scenario (normal, brute-force burst, traffic spike, drift).
4. Model management: train, list versions, promote, compare (offline metrics shown in UI).
5. Experiment runner page: launch a configured experiment, watch progress, download tables/figures.

Research-side features (paper side):
- Config-driven experiments (YAML), fixed seeds, environment capture (CPU, RAM, versions, git hash) stored with each run.
- Every run writes `results/<exp_id>/{metrics.json, tables.csv, table.md, figures/*.png, env.json}`.
- One command regenerates all paper tables/figures from stored results.

## 5. Architecture

```
datasets / synthetic generator
        │  (replay, rate-controlled, correlation id + label side-channel)
        ▼
  Kafka (KRaft) ── logs-raw (N partitions) ──► Engine A: Python consumer group (batch scoring)
        │                                  └─► Engine B: Spark Structured Streaming (same model)
        │                                              │
        │            parse (Drain3) → featurize → score → threshold
        ▼                                              ▼
  alerts-critical  ◄──────────────────────────────────┘
        │
        ▼
  API service (FastAPI) ── SQLite/Postgres (alerts, runs, models) ── Streamlit UI (or web UI)
        │
        └── metrics topic / Prometheus-style counters → dashboard + experiment recorder
```

Key rules:
- **One model interface** (`fit`, `score`, `save`, `load`) with implementations: IsolationForest (TF-IDF), + a second model (Autoencoder or LOF/PCA), and optionally a sequence model later. Both engines call the same code.
- **One parser/cleaner** used for train and serve (kept from the prior attempt).
- **Labels never travel on the hot path** except in explicit benchmark mode, through a separate field, so latency is not polluted and ground truth cannot leak into the model.
- **Timing points** stamped at: producer send, broker append, consumer receive, post-parse, post-score, alert publish. This decomposes latency for the paper.
- Score convention: higher = more anomalous (as in the earlier attempt); document once.
- A real database (SQLite to start) replaces the JSON file.

## 6. Repository layout (new, from scratch in `logsentinel/`)

```
logsentinel/
  README.md  PLAN.md  pyproject.toml  Makefile  docker-compose.yml  .env.example
  configs/            # experiment YAMLs (datasets, models, loads)
  src/logsentinel/
    common/           # config, logging, timing, schemas (pydantic), env capture
    data/             # loaders (HDFS_v1, BGL, Thunderbird), synthetic generator, splitter, replay
    parsing/          # Drain3 wrapper, regex cleaner
    features/         # TF-IDF, template-count vectors, session windows
    models/           # base interface, iforest, autoencoder/LOF, registry, thresholds (percentile, 3σ, tuned)
    stream/           # kafka producer (replay), python consumer engine, spark job
    alerts/           # alert sink, webhook, DB writer
    api/              # FastAPI: alerts, models, runs
    ui/               # Streamlit pages: dashboard, alerts, sources, models, experiments
    experiments/      # runner, metrics (P/R/F1/AUC/latency/throughput), report generator (md, csv, png)
  tests/              # unit tests + one small end-to-end smoke test
  data/  results/  models/   # gitignored, with README on how to fetch
```

Reuse from `log-anomaly-pipeline` (copy and refactor, do not import): `utils/log_cleaner.py` patterns, `log_producer.py` rate throttle + `--burst`, threshold sweep and percentile table logic in `run_experiments.py`, the KRaft `docker-compose.yml` (drop Kafka UI or keep as optional). Discard everything in `log-analytics-pipeline/` except the idea of a Threat Simulator (re-implement as "inject scenario" going through Kafka).

Tooling: Python 3.12 (the existing `.venv` is 3.14, which many ML/Spark wheels lack), `uv` or venv, pinned minimal dependencies (not `pip freeze`), `pytest`, `ruff`. Git-init the new repo at the start (the current directory is not a repo).

## 7. Experiments the paper will report (research questions)

| ID | Question | Method | Output |
|---|---|---|---|
| E1 | Detection quality: how good is unsupervised detection on real logs? | HDFS_v1 (session level), BGL/Thunderbird (time-window level); train on normal only; IForest vs comparator vs regex-only baseline | P/R/F1, AUC, PR curves table |
| E2 | Does template parsing help? | Regex cleaner vs Drain3 vs raw | Ablation table |
| E3 | Threshold strategy | Percentile vs 3σ vs label-tuned | F1 vs threshold curves |
| E4 | Throughput ceiling | Sweep offered load; batch size sweep; 1→N consumers | Throughput vs latency curve, saturation point |
| E5 | Latency breakdown | Timing stamps at each stage at 25/50/75% of saturation | P50/P95/P99 stacked table |
| E6 | Engine comparison | Python consumers vs Spark Structured Streaming, same model/data | Throughput/latency/setup-cost table |
| E7 | Elasticity under spikes | Inject 10× burst; measure lag recovery with fixed vs scaled consumers | Lag-over-time figure |
| E8 | Concept drift | Shift template distribution mid-stream; static model vs periodic retrain | F1-over-time figure |

Rules for honesty: report the hardware (single Arch machine), state that ">50k events/s" was a target, and report the achieved figure even if lower. Repeat runs (≥5) and report median ± spread. If the target is missed, the bottleneck analysis from E5 becomes a paper contribution.

## 8. Phased schedule (~8 weeks)

| Week | Deliverable | Exit criterion |
|---|---|---|
| 1 | Foundations: new repo, env, config/schemas, data loaders + download script, HDFS_v1 session builder, citation audit started | `make data` produces train/val/test splits; unit tests pass |
| 2 | Offline ML core: parsers (regex + Drain3), features, IForest + second model, thresholds, offline metrics | E1–E3 runnable offline with saved results |
| 3 (DONE) | Streaming baseline: Kafka compose, replay producer, batch-scoring consumer group, alert topic, timing stamps | End-to-end smoke test green; sustained ≥ 5k ev/s |
| 4 (DONE) | Backend + storage: FastAPI, DB, alert lifecycle, model registry | API tests pass; alerts persisted and triaged |
| 5 (DONE) | UI: dashboard, alert inbox, sources, models, experiment runner page | Demo flow works: start source → alert appears → resolve |
| 6 (DONE) | Performance experiments E4, E5, E7; tuning (batching, partitions, compression) | Throughput/latency figures generated by one command |
| 7 (DONE) | Spark arm (E6), drift (E8), comparator ablations | All eight experiments have result folders |
| 8 (DONE) | Paper + defense: regenerate tables/figures, write Results/Discussion/Threats to validity, rebuild the deck from real numbers, rehearse the 4-pane live demo | Draft paper complete; deck has no placeholders |

Contingency: if behind schedule, cut in this order: E8 drift → Spark arm (mention as future work) → second UI polish. E1, E4, E5 are the non-negotiable core.

## 9. Paper outline (auto-fed by the app)

1. Abstract · 2. Introduction & problem · 3. Related work (verified citations) · 4. System design (architecture, parsing, models, thresholds) · 5. Experimental setup (datasets, hardware, metrics, protocol) · 6. Results (E1–E8, each table/figure generated by `make report`) · 7. Discussion (limitations, threats to validity, what missed the target and why) · 8. Conclusion & future work · References.

A `paper/` folder in the repo holds the manuscript and a `figures/` symlink to `results/`; a small script maps each result file to a table/figure number so nothing is copied by hand.

## 10. Risks

- **50k ev/s on one laptop-class machine**: likely limited by Python and JSON serialization, not Kafka. Mitigations: batch scoring, compact serialization (e.g., msgpack/Avro), multiple consumer processes; otherwise report the ceiling.
- **HDFS_v1 is session-labeled**: needs session grouping; per-line metrics would be invalid.
- **Spark on local mode** adds JVM startup and overhead; compare fairly, and say so.
- **Scope creep from "full product"**: the UI and API are bounded by the feature list in §4; anything else goes to future work.
- **Unverified citations**: fix before any writing is finalized.

## 11. Verification (how we know the plan's outputs are real)

- `pytest` unit tests for parsers, features, metrics, threshold logic; one Docker-based smoke test (produce 1,000 labeled events → expect alerts + DB rows).
- Offline reproducibility: re-running an experiment with the same config and seed gives identical metrics.
- `make report` regenerates every paper table/figure from `results/` on a clean checkout.
- Live demo rehearsal: the 4-pane script from `Gemini Notebook.md` (attacker burst, stream engine stats, inference alerts, alert sink) runs end-to-end in under 2 minutes.

## 12. First actions after approval

1. Save this plan as `PLAN.md` in `/home/adu/Projects/SEM III-IV Research and Project/` (a copy of this file).
2. Create `logsentinel/`, `git init`, Python 3.12 env, minimal pinned dependencies.
3. Start Week 1 items: config/schemas, dataset download script, HDFS_v1 session builder.
4. Leave `log-anomaly-pipeline/` and `log-analytics-pipeline/` untouched as read-only reference (move to `archive/` only if you say so).

## Status log
- Week 1 done: repo, data loaders, HDFS/BGL/Thunderbird sessions, splits (chronological + random).
- Week 2 done: parsers (raw/regex/Drain3), features, IForest/PCA/AE, thresholds, E1-E3 results (docs/results-offline.md).
- Week 3 done: user-space Kafka, bundle + serve-time scorer (100% identical to offline), replay producer, engine workers,
  end-to-end benchmark (docs/results-stream.md): sustained 10k ev/s, event->alert p99 78 ms, burst capacity 60k ev/s/worker.
  Deviations: Kafka runs without Docker (no daemon access); streaming is HDFS only; sessions are scored incrementally
  with a min-lines gate because HDFS blocks live for hours. Open item raised then addressed after Week 3: early detection.
- After Week 3: early-detection gap addressed with an age-30s snapshot check (live F1 0.691 -> 0.923, recall 0.598 -> 0.986,
  latency p99 ~98 ms). Open: 1.4% live recall gap vs simulation (docs/results-stream.md).
- Week 4 done: SQLite store (alerts + audit trail, model registry, runs), alert sink service, FastAPI (docs/api.md),
  training jobs via API, registry-driven engine start (`--bundle active:hdfs`). Choices made with the user: separate sink,
  SQLite, React-style UI in Week 5 (Node is installed; this adds a JS toolchain to the Week 5 budget).
  Verified on the real chain (20k sessions): DB alert counts equal the engine's exactly (274/274, 272/272, 275/275 after
  a sink crash and restart); median sink lag 121 ms. Alert counts vary by ~1% between identical runs (deadline alerts
  depend on micro-batch/watermark timing), which is also a candidate for the unexplained live-vs-simulation recall gap.
- Week 5 done: React + Carbon UI (dashboard, alerts, source, models, experiments) served by the API; live metrics topic,
  source supervisor, scenario injection (anomaly burst), spike scenario, experiment runner, job runner. Verified with a real
  Chrome run of the demo flow (start source, live metrics, inject, alerts appear, triage, run summary, report rebuild).
  Bugs found by that test and fixed: dark theme not applied, checkbox double toggle, SQLite thread-affinity HTTP 500s under
  parallel polling, finished-run summaries not stored, stop signalling the shell instead of the job, zombie jobs looking
  alive, run ids colliding within a second, summarize() crashing on injected sessions. Not done: concept-drift scenario
  (Week 7), auth, push updates.
- Week 6 done: benchmark harness (pinning, live metrics, autoscaler, CPU per component, per-stage latency), 185 runs
  (docs/results-perf.md). One worker sustains 50k events/s (p99 111 ms), two sustain 70k; typical p99 about 100 ms below
  saturation (pooled p99 up to 617 ms because 2 of 55 runs had unexplained stalls), dominated by micro-batch update and the
  consumer fetch path, not scoring; 10x spike: scale-out cuts recovery
  from 20 s to 7.7 s but cannot avoid a queueing period. Found and fixed a racy worker-readiness check that let a
  consumer-group rebalance replay 200k messages during a run. Open: engine is at-least-once with auto-commit (session counts
  can double-count after a rebalance); results are single-host.
- E5 excursions investigated (after Week 6): JVM GC/safepoint logging, per-core CPU/frequency sampler, 30 instrumented runs and a
  cold-restart test. A cold broker makes the first paced run slow (p99 1.1-1.2 s, 3 of 3 restarts, producer-to-broker stage); cold runs
  are now flagged (broker uptime < 45 s), excluded from steady-state stats and reported separately, and the runner warms the broker.
  Two stalls in the original E5 runs (2 of 44 warm runs) remain unexplained. Warm-run pooled p99: 102 / 116 / 612 ms at 25 / 50 / 75% load.
- Week 7 (in progress): E8 concept drift done (docs/results-drift.md): a static model flags 100% of sessions once >=36% of lines are
  reworded; the unlabeled unseen-line share is a clean drift signal (0 false triggers); triggered retraining recovers in one chunk; periodic
  retraining on raw windows is unstable when anomalies are frequent. Simulated drift only; engine hot-swap not built.
- Week 7: ablations done (docs/results-ablations.md): Drain parameters do not matter; on BGL binary presence features beat tf-idf (PR-AUC 0.17 to 0.76,
  validation-selected), so E1's BGL numbers were pessimistic; on HDFS PCA at 99% variance beats the 95% default (F1 0.938 to 0.994) but is not
  applied to the streaming bundle.

- Week 7 done: E6 Spark vs Python (docs/results-e6.md, 69 runs, 5 reps, 0 incomplete). Python engine sustains 50,000 ev/s on this
  machine; Spark local[2] sustains only ~3,000 ev/s before backlog stops draining within two micro-batches. At shared rates Spark is
  ~120-250x higher latency, ~13x more CPU, ~7.6x more memory for byte-identical alert counts (same detections, pure overhead gap).
  Spark tuning (shuffle partitions 1/4, smaller max-offsets-per-trigger) did not help: the floor is Spark's own micro-batch interval
  (3-6s per batch, even empty ones), not a tunable parameter. Reading for the paper: the lit review's framing of Spark/Flink as
  necessary for the >50k ev/s target does not hold on a single host at this scale; say so explicitly in the discussion.
  Week 7 is now fully complete (E6, E8, ablations all done). Next: Week 8 (paper + defense deck).

## Resolved: mid-session pause (2026-09-28 to 2026-09-29)
Work was paused mid-E6 (6/69 runs, pre-fix code) at the user's request, then resumed and restarted E6 from a clean state (the 6
partial runs predated the TreeMonitor CPU-measurement fix, so keeping them would have mixed inconsistent methodology). See
`docs/RESUME.md` for the historical resume guide (now superseded — E6 is complete) and the full list of bugs found and fixed
during Week 7 development (PySpark version mismatch, ArrayType state schema, stale checkpoints, timeout-before-watermark,
the CPU-measurement bug, oracle-threshold fairness in E8, missing E8 sensitivity grid, misleading BGL ablation conclusion).
- Week 8 done: full paper draft (`paper/LogSentinel_Research_Paper.docx`, 24 pages, Abstract through References,
  corrected citations) and a 12-slide defense deck (`paper/LogSentinel_Defense.pptx`), both generated by script
  (`paper/build_paper.js`, `paper/build_deck.js`) directly from `docs/results-*.md`/`docs/perf`/`docs/drift`/
  `docs/ablations` — no illustrative or placeholder numbers, only the candidate's own identifying fields remain
  as `[...]`. Deck passed schema validation and a full 12-slide visual QA pass. Demo script written
  (`docs/demo-script.md`, UI variant + 4-pane terminal variant) and smoke-tested live end to end (real Kafka,
  real engine, real sink): 20,000-session replay produced 208 alerts, a 50-session injection produced +51 sink
  alerts within seconds. One bug caught by actually running the script rather than trusting inspection:
  `replay_segments` takes `(n_events, rate)` segments, not `(seconds, rate)` — fixed before finalizing.
  All 8 weeks of the plan are now complete.
