# Streaming results (Week 3, preliminary; single 4-core / 15 GB host shared by broker, producer and workers)

Setup: HDFS_v1 test split (chronological), bundle `hdfs-drain-pca` (Drain3 + PCA-SPE, val-tuned threshold),
Kafka 3.9.1 single broker, `logs-raw` 6 partitions. Raw summaries in `docs/stream-runs/`.

## Sustained load: whole test split, 10,000 events/s for 286 s (1 worker)
| metric | value |
|---|---|
| events / sessions | 2,859,006 / 172,519 (all scored) |
| producer / consumer rate | 10,000 / 10,002 ev/s, backlog after last send: 0.0 s |
| event -> alert latency p50 / p95 / p99 | 41.6 / 72.2 / 77.9 ms (transport 30/60/67, compute 11/13/16, emit 0.2/1.0/1.2) |
| **final full-session** P / R / F1 | 0.883 / 1.000 / 0.938 (PR-AUC 0.904) = offline reference; scores 100% identical, max abs diff 0 |
| streaming alert-any-time (gate >= 10 lines) P / R / F1 | 0.819 / 0.598 / 0.691 (2,718 alerts) |

Reading: the serving path reproduces the offline detector exactly. Online alerts lose recall (0.60 vs 1.00) because
short anomalous sessions cannot be told from partial normal ones until the stream ends (see README, known limitation).

## Burst (producer as fast as possible, 40,000 sessions = 759k lines): consumer capacity
| workers | consumer rate | note |
|---|---|---|
| 1 | 60,359 ev/s | backlog drained 11.1 s after last send; latency is queueing delay (p50 10.5 s) |
| 2 | 104,113 ev/s (1.7x) | drained in 5.9 s |

Caveats: each burst run lasts ~12 s, producer and broker compete with workers for 4 cores, JSON on the wire.
The 50k ev/s target is met for consumer *capacity* here, but only the 10k ev/s run is a steady-state latency
measurement. Proper sweeps (offered load, batch size, 1..N workers, repeats >= 5) are Week 6 (E4/E5).


## Early-detection fix (bundle `hdfs-drain-pca-early`: incremental rule OR age-30s check, autoencoder)
Diagnosis: normal HDFS sessions always have >= 13 lines, but 40.2% of anomalous test sessions (1,497 / 3,723) have only
2-4 lines and then stay silent, so the `--min-lines` gate never lets them alert (live recall 0.598 = 1 - 0.402).
Fix: when a session is 30 LOG-seconds old, score its snapshot with an autoencoder trained on age-30s snapshots of
normal sessions (event-time timer driven by a per-worker watermark). (age, model) chosen by a validation-only rule;
simulation over ages/models: `docs/stream-runs/early-simulation.json`. Plain deadline rule ("< 13 lines at age T")
needs T >= 420 s for F1 0.93; the learned check needs 30 s. Isolation Forest fails as the age check (recall stays 0.60).

Same full-test run, 10,000 events/s, 1 worker (before -> after):
| metric | incremental only | + age check |
|---|---|---|
| live P / R / F1 | 0.819 / 0.598 / 0.691 | **0.868 / 0.986 / 0.923** |
| alerts (incremental / deadline) | 2,718 / - | 2,717 / 1,514 |
| event -> alert latency p50 / p95 / p99 | 41.6 / 72.2 / 77.9 ms | 31.8 / 75.3 / 97.8 ms |
| consumer rate, backlog | 10,002 ev/s, 0 s | 9,998 ev/s, 0.1 s |
| final full-session F1 (needs whole lifetime) | 0.938 | 0.938 (scores still 100% identical to offline) |

Two different delays must not be confused: **system latency** (ms above) is what the pipeline adds; **evidence delay** is
how much log time passes before the data itself contains the evidence (deadline alerts: 30 log-s; alerts from
later-appearing evidence: p95 7,122 log-s, i.e. ~2 h, because those blocks only look abnormal late in their life).

Unexplained gap: the offline simulation predicted recall 0.999 / F1 0.930, live gave 0.986 / 0.923. Not yet investigated;
candidates: per-worker watermark across 6 partitions, multi-block lines routed by first block, due-queue ordering.
