# Resume guide (historical — E6 is now complete)

**Superseded.** This guide was written for a deliberate mid-Week-7 pause. The session resumed on 2026-09-29, discarded the 6
partial rep0 runs (they predated a CPU-measurement fix and mixing them with the rest would have been methodologically
inconsistent), and reran E6 clean: 69/69 runs, 5 reps, 0 incomplete. Results are in `docs/results-e6.md`. This file is kept
for the record of what was in flight and the bugs already fixed at the time of the pause; the "preliminary" numbers below
are superseded by `docs/results-e6.md` and should not be cited.

## State
| Area | State |
|---|---|
| Weeks 1-6 | Done and committed (data, offline E1-E3, streaming, API, UI, performance E4/E5/E7). See `PLAN.md` |
| Early detection, E5 excursion diagnosis | Done and committed (`docs/results-stream.md`, `docs/results-perf.md`, `docs/perf/e5-diagnosis.md`) |
| Week 7: E8 concept drift | Done (`docs/results-drift.md`) |
| Week 7: ablations | Done (`docs/results-ablations.md`); recommendations NOT applied to the streaming bundle |
| Week 7: E6 Spark vs Python | **Code done and tested, measurement 6 of 69 runs.** Stopped on purpose |
| Weeks 8: paper, defense deck | Not started |

## Resume E6 (about 60 minutes; resumable, skips finished runs)
```bash
cd "/home/adu/Projects/SEM III-IV Research and Project/logsentinel"
scripts/kafka.sh start                                   # data folder survives; wait for "kafka up"
# close other applications first (browser, Discord, Steam): the machine is 4 cores and noisy
.venv/bin/python -m logsentinel.experiments.e6 run --reps 5 > /tmp/e6_run.log 2>&1
.venv/bin/python -m logsentinel.experiments.e6 report    # results/perf/e6/tables.md + figures/e6_spark_vs_python.png
```
Then: read the tables, write `docs/results-e6.md` (copy tables and the figure into `docs/perf/`), update `PLAN.md`, commit.
Note the resume mixes conditions: the first run after a Kafka restart is flagged cold and excluded automatically; the pause breaks the
interleaving of repeats, so mention it. Runs saved so far are in `results/perf/e6/` (python 1k and 3k, spark 1k to 4k, all rep 0).

## What is known about Spark so far (preliminary)
- The Spark arm (`stream/spark_engine.py`) reproduces the Python engine's incremental alerts on identical input (8 and 8 sessions, same ids;
  34 and 34 in another probe). NumPy per-session scoring equals the sklearn path to 1e-8 (unit test).
- Local mode on 2 pinned cores, defaults: micro-batches cost 3 to 6 s each (even empty ones 3 s). Rep-0 numbers: Spark p50 alert latency 3.5 s at 1k
  events/s rising to 9.7 s at 4k, backlog 4 to 9 s, about 1.7 GB memory, startup about 15 s. Python at 3k: p50 41 ms, 0.13 cores, 209 MB, startup 5 s.
  At 10k events/s Spark did not keep up (probe). Spark tuning variants (shuffle partitions 1/4, smaller batches) are part of the E6 run.
- Differences that must be stated with the results: Spark has no end-of-stream flush (young sessions never get their age check), age-check
  alerts have no trigger line so only incremental alerts are compared on latency, the watermark is global per micro-batch.
- Bugs already fixed in the Spark port: workers ran Python 3.14 (set `PYSPARK_PYTHON`), array-typed state fails in PySpark 4.2 (state is bytes),
  stale checkpoints (deleted at start), timeout earlier than watermark raises (clamped).

## Open items (not blocking)
- Two unexplained E5 latency stalls (2 of 44 warm runs); cold-broker effect is explained and handled.
- Ablations: PCA at 99% variance gives HDFS F1 0.994 vs 0.938 (validation-selected); binary features raise BGL PR-AUC from 0.17 to 0.76. Neither is applied.
- The engine is at-least-once with auto-commit; a consumer-group rebalance can double-count open sessions.
- UI drift scenario is disabled (engine cannot hot-swap a model). Drift results are simulated rewording only.
- Everything is single-machine. Week 8 (paper text, real tables/figures wiring, defense deck) is untouched; citations need manual checking (`docs/citations.md`).

## Environment gotchas
- The project path contains spaces. Kafka and the JDK live in `~/.local/share/logsentinel` (no spaces) via `scripts/kafka.sh setup`.
- `data/`, `results/`, `models/`, `ui/dist`, `.venv` are git-ignored: on this machine only. Rebuild with `make data`; models with
  `python -m logsentinel.models.train --dataset hdfs --parser drain --model pca --early-age 30 --early-model ae --out models/hdfs-drain-pca-early`;
  register and activate it in the UI (or API) before starting a source; UI: `make ui`.
- The venv is Python 3.12 (system Python is 3.14). `uv` is not in the venv; if you need it: `python3 -m venv /tmp/u && /tmp/u/bin/pip install uv`.
  PyPI is intermittently unreachable: retry.
- `pkill -f`/`pgrep -f` match the calling shell's own command line if the pattern text appears in it (this killed the shell several times):
  use bracketed patterns such as `pgrep -f "[e]xperiments.e6 run"` and keep them out of long compound commands.
- Do not run tests while a benchmark runs, and do not suspend or hibernate the machine mid-run.
- Tests: `pytest -q` (78), `pytest -q -m e2e` (needs Kafka; recreates topics), `make ui-test`, `node ui/e2e/smoke.mjs` (needs API, sink, Kafka, active model).
