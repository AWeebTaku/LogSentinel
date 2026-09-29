# Performance results (LogSentinel, single 4-core host)


## Setup

| Item | Value |
|---|---|
| CPU | Intel(R) Core(TM) i5-7400 CPU @ 3.00GHz |
| Cores / RAM | 4 cores, 15.5 GB |
| OS | Linux-7.2.7-arch1-1-x86_64-with-glibc2.44 |
| Python | 3.12.14 |
| Kafka | 3.9.1 single broker (KRaft), 1 replica, LogAppendTime on logs-raw |
| Core layout (pinned) | broker core 0, producer core 1, engine workers cores 2-3 |
| Model | hdfs-drain-pca-early (Drain3 + PCA, age check autoencoder at 30 s) |
| 1-min load average when a run started | median 2.63, max 6.46 (includes the benchmark's own previous run, so it is not a measure of other applications) |
| Repeats | 5 per cell, interleaved across cells; median with min-max |

## E4a Offered-load sweep

Sustained = consumed >= 97% of offered, backlog gone within 1 s of the last send, p99 under 500 ms, scanning upward and stopping at the first failing rate.

**1 worker**: sustained up to **50,000 events/s**; the next tested rate, 55,000, fails. The true limit lies in between.

| Offered ev/s | Consumed ev/s | Backlog after last send (s) | Event-to-alert p99 (ms) | Engine CPU (cores) | Broker CPU (s) | Producer CPU (s) |
|---|---|---|---|---|---|---|
| 10,000 | 9,967 [9,956-10,019] n=5 | 0.1 [0.0-0.1] n=5 | 83 [72-141] n=5 | 0.45 [0.44-0.45] n=5 | 2.7 [2.5-2.8] n=5 | 1.1 [1.1-1.1] n=5 |
| 20,000 | 20,004 [19,877-20,031] n=5 | 0.0 [0.0-0.1] n=5 | 118 [100-129] n=5 | 0.63 [0.63-0.64] n=5 | 2.8 [2.6-2.8] n=5 | 1.3 [1.3-1.4] n=5 |
| 30,000 | 29,943 [29,933-29,953] n=5 | 0.1 [0.0-0.1] n=5 | 100 [97-109] n=5 | 0.83 [0.82-0.83] n=5 | 2.7 [2.6-2.8] n=5 | 1.5 [1.5-1.6] n=5 |
| 40,000 | 39,857 [39,782-39,869] n=5 | 0.1 [0.1-0.1] n=5 | 93 [86-146] n=5 | 1.02 [1.01-1.03] n=5 | 2.7 [2.5-2.7] n=5 | 1.7 [1.7-1.7] n=5 |
| 45,000 | 44,805 [44,752-44,816] n=5 | 0.1 [0.1-0.1] n=5 | 90 [82-117] n=5 | 1.11 [1.10-1.13] n=5 | 2.6 [2.6-2.7] n=5 | 1.8 [1.7-1.8] n=5 |
| 50,000 | 49,530 [48,986-49,764] n=5 | 0.1 [0.1-0.3] n=5 | 111 [86-204] n=5 | 1.20 [1.17-1.21] n=5 | 2.5 [2.5-2.7] n=5 | 1.9 [1.8-1.9] n=5 |
| 55,000 | 49,691 [49,486-51,562] n=5 | 1.1 [0.7-1.1] n=5 | 969 [586-989] n=5 | 1.20 [1.19-1.22] n=5 | 2.6 [2.4-2.7] n=5 | 2.0 [1.9-2.0] n=5 |
| 60,000 | 49,176 [40,113-50,030] n=5 | 2.1 [2.0-2.3] n=5 | 2,056 [1,970-2,349] n=5 | 1.17 [0.95-1.20] n=5 | 2.5 [2.3-2.6] n=5 | 2.0 [2.0-2.1] n=5 |
| 70,000 | 50,875 [49,556-52,209] n=5 | 3.8 [3.4-4.1] n=5 | 3,781 [3,472-4,191] n=5 | 1.19 [1.18-1.20] n=5 | 2.1 [2.0-2.1] n=5 | 2.2 [2.2-2.3] n=5 |

**2 workers**: sustained up to **70,000 events/s**; the next tested rate, 80,000, fails. The true limit lies in between.

| Offered ev/s | Consumed ev/s | Backlog after last send (s) | Event-to-alert p99 (ms) | Engine CPU (cores) | Broker CPU (s) | Producer CPU (s) |
|---|---|---|---|---|---|---|
| 60,000 | 59,604 [59,158-59,774] n=5 | 0.1 [0.1-0.2] n=5 | 228 [172-348] n=5 | 0.87 [0.85-0.89] n=5 | 2.7 [2.6-2.9] n=5 | 2.0 [2.0-2.1] n=5 |
| 70,000 | 69,662 [69,475-69,695] n=5 | 0.1 [0.1-0.1] n=5 | 419 [96-439] n=5 | 0.97 [0.86-0.98] n=5 | 2.6 [2.6-2.7] n=5 | 2.2 [2.1-2.2] n=5 |
| 80,000 | 79,621 [70,837-79,650] n=5 | 0.1 [0.1-1.3] n=5 | 603 [330-1,951] n=5 | 1.04 [0.98-1.08] n=5 | 2.8 [2.6-2.9] n=5 | 2.3 [2.3-2.5] n=5 |
| 100,000 | 85,029 [82,787-87,931] n=5 | 1.8 [1.4-2.1] n=5 | 1,777 [1,431-2,035] n=5 | 1.07 [1.05-1.11] n=5 | 2.9 [2.6-2.9] n=5 | 2.7 [2.7-2.7] n=5 |
| 110,000 | 82,092 [70,771-91,095] n=5 | 3.4 [2.1-5.6] n=5 | 3,189 [2,051-5,372] n=5 | 1.02 [0.88-1.11] n=5 | 2.2 [1.8-3.6] n=5 | 2.8 [2.8-2.9] n=5 |
| 120,000 | 81,666 [69,431-91,321] n=5 | 4.7 [3.2-7.2] n=5 | 4,487 [3,119-6,892] n=5 | 1.04 [0.87-1.12] n=5 | 2.2 [2.1-3.6] n=5 | 3.0 [3.0-3.1] n=5 |
| 140,000 | 85,657 [78,437-91,483] n=5 | 6.4 [5.3-7.9] n=5 | 6,033 [5,095-7,368] n=5 | 1.04 [0.97-1.05] n=5 | 2.1 [1.9-3.4] n=5 | 3.4 [3.3-3.5] n=5 |

## E4b Tuning at burst (capacity)

Producer sends 1M events as fast as it can; capacity = events consumed / time span of consumption. Baseline: 1 worker, batch 2000, no compression, linger 5 ms, 6 partitions.

| Cell | Configuration | Capacity (ev/s) | vs baseline | Engine CPU (cores) | Broker CPU (s) |
|---|---|---|---|---|---|
| base | 1w, batch 2000, none, linger 5 ms, 6 partitions | 54,686 [52,469-56,217] n=5 | baseline | 1.23 [1.21-1.25] n=5 | 0.7 [0.7-0.9] n=5 |
| batch500 | 1w, batch 500, none, linger 5 ms, 6 partitions | 49,756 [49,289-52,681] n=5 | -9.0% | 1.21 [1.19-1.24] n=5 | 0.8 [0.8-0.9] n=5 |
| batch8000 | 1w, batch 8000, none, linger 5 ms, 6 partitions | 55,856 [54,870-58,717] n=5 | +2.1% | 1.27 [1.23-1.29] n=5 | 0.7 [0.7-0.8] n=5 |
| lz4 | 1w, batch 2000, lz4, linger 5 ms, 6 partitions | 54,387 [53,407-56,460] n=5 | -0.5% | 1.17 [1.16-1.23] n=5 | 0.8 [0.8-1.8] n=5 |
| linger0 | 1w, batch 2000, none, linger 0 ms, 6 partitions | 54,080 [53,563-56,711] n=5 | -1.1% | 1.23 [1.20-1.25] n=5 | 2.6 [2.0-3.2] n=5 |
| linger20 | 1w, batch 2000, none, linger 20 ms, 6 partitions | 54,379 [52,254-57,263] n=5 | -0.6% | 1.25 [1.21-1.28] n=5 | 0.6 [0.5-0.7] n=5 |
| w2_part2 | 2w, batch 2000, none, linger 5 ms, 2 partitions | 95,961 [89,011-98,130] n=5 | +75.5% | 1.09 [1.08-1.15] n=5 | 0.8 [0.6-0.8] n=5 |
| w2_part6 | 2w, batch 2000, none, linger 5 ms, 6 partitions | 87,949 [87,279-92,127] n=5 | +60.8% | 1.10 [1.09-1.13] n=5 | 0.8 [0.7-1.9] n=5 |
| w2_part12 | 2w, batch 2000, none, linger 5 ms, 12 partitions | 87,043 [66,459-93,257] n=5 | +59.2% | 1.11 [0.79-1.14] n=5 | 0.9 [0.8-2.3] n=5 |

## E4c Worker scaling (burst capacity)

Pinned: broker on core 0, producer on core 1, workers share cores 2-3 (so 4 workers are oversubscribed). Unpinned: everything shares all four cores.

| Layout | Workers | Capacity (ev/s) | Speedup vs 1 worker | Efficiency |
|---|---|---|---|---|
| pinned | 1 | 54,717 [42,690-56,938] n=5 | 1.00x | 100% |
| pinned | 2 | 88,350 [83,665-91,213] n=5 | 1.61x | 81% |
| pinned | 4 | 78,521 [63,601-86,107] n=5 | 1.44x | 36% |
| unpinned | 1 | 54,998 [53,911-55,976] n=5 | 1.00x | 100% |
| unpinned | 2 | 96,308 [92,150-102,647] n=5 | 1.75x | 88% |
| unpinned | 4 | 114,430 [106,563-120,539] n=5 | 2.08x | 52% |

## E5 Latency breakdown by stage

Alerts triggered during paced runs at 25/50/75% of single-worker saturation. Stages: producer to broker (includes client linger, batching, network, append), broker to consumer, engine update (rest of the micro-batch before scoring), scoring, alert emit. Broker append time has 1 ms resolution. Each cell is the median over repeats of that run's percentile.

| Load | Stage | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|
| 25% (12,500 ev/s) | producer_to_broker | 0.7 [0.5-1.0] n=14 | 4.7 [4.2-322.1] n=14 | 5.4 [5.0-768.2] n=14 |
| 25% (12,500 ev/s) | broker_to_consumer | 7.8 [7.3-9.2] n=14 | 53.7 [47.7-61.7] n=14 | 68.4 [58.9-90.4] n=14 |
| 25% (12,500 ev/s) | engine_update | 17.4 [16.2-18.3] n=14 | 22.1 [20.2-36.0] n=14 | 29.7 [21.4-40.6] n=14 |
| 25% (12,500 ev/s) | scoring | 1.0 [1.0-1.0] n=14 | 1.5 [1.3-1.8] n=14 | 2.2 [1.8-3.9] n=14 |
| 25% (12,500 ev/s) | alert_emit | 0.1 [0.1-0.1] n=14 | 0.1 [0.1-0.2] n=14 | 0.2 [0.2-0.8] n=14 |
| 25% (12,500 ev/s) | total | 27.9 [26.8-29.4] n=14 | 73.9 [66.2-468.3] n=14 | 88.6 [79.8-830.3] n=14 |
| 50% (25,000 ev/s) | producer_to_broker | 0.9 [0.6-1.0] n=15 | 4.5 [4.1-4.7] n=15 | 5.5 [5.2-16.1] n=15 |
| 50% (25,000 ev/s) | broker_to_consumer | 5.2 [4.9-5.9] n=15 | 54.3 [47.7-59.8] n=15 | 72.7 [69.6-78.8] n=15 |
| 50% (25,000 ev/s) | engine_update | 38.0 [36.4-40.1] n=15 | 41.4 [39.1-48.7] n=15 | 47.0 [40.6-68.1] n=15 |
| 50% (25,000 ev/s) | scoring | 1.1 [1.1-1.2] n=15 | 1.6 [1.4-2.0] n=15 | 2.2 [1.6-3.8] n=15 |
| 50% (25,000 ev/s) | alert_emit | 0.1 [0.1-0.1] n=15 | 0.2 [0.2-0.2] n=15 | 0.3 [0.2-0.9] n=15 |
| 50% (25,000 ev/s) | total | 46.2 [44.6-48.7] n=15 | 96.4 [87.4-103.3] n=15 | 115.5 [109.4-124.4] n=15 |
| 75% (37,500 ev/s) | producer_to_broker | 1.4 [1.2-1.9] n=15 | 5.1 [4.9-7.6] n=15 | 6.0 [5.5-65.3] n=15 |
| 75% (37,500 ev/s) | broker_to_consumer | 6.5 [5.5-323.2] n=15 | 48.5 [44.1-562.1] n=15 | 72.7 [57.6-612.8] n=15 |
| 75% (37,500 ev/s) | engine_update | 37.7 [35.9-39.8] n=15 | 41.1 [39.3-62.8] n=15 | 44.8 [40.9-78.7] n=15 |
| 75% (37,500 ev/s) | scoring | 1.2 [1.1-1.3] n=15 | 1.6 [1.4-2.2] n=15 | 2.2 [1.8-4.0] n=15 |
| 75% (37,500 ev/s) | alert_emit | 0.1 [0.1-0.1] n=15 | 0.7 [0.4-2.3] n=15 | 1.0 [0.8-2.7] n=15 |
| 75% (37,500 ev/s) | total | 47.5 [44.4-393.1] n=15 | 90.9 [85.0-616.9] n=15 | 108.1 [94.6-660.6] n=15 |

**Pooled over every alert and repeat** (a median of per-run percentiles hides a bad run; pooling does not). One run at 25% load had a 0.7 s stall before the broker and one run at 75% load had an 8 s consumer-side slowdown; the cause of both is unknown (the broker log shows nothing that distinguishes them from a normal run). Runs on a cold broker are excluded here and reported in the next section.

| Load | Alerts | p50 (ms) | p95 (ms) | p99 (ms) | p99.9 (ms) | Share over 500 ms | Runs with p99 over 500 ms |
|---|---|---|---|---|---|---|---|
| 25% (12,500 ev/s) | 2,975 | 28 | 75 | 102 | 830 | 0.37% | 1 of 14 |
| 50% (25,000 ev/s) | 5,435 | 46 | 97 | 116 | 129 | 0.00% | 0 of 15 |
| 75% (37,500 ev/s) | 11,111 | 48 | 103 | 612 | 649 | 2.45% | 1 of 15 |

## E5 cold-start effect

The first paced run after a broker restart is much slower than the following ones; the slow part is the producer-to-broker stage (about 500-700 ms on the slow alerts). 3 of 3 restarts reproduced it, 0 of 6 later runs did. A burst warm-up does not remove it. Same load as E5 at 25% (12,500 events/s).

| Broker | Run | State | Alerts | p50 (ms) | p99 (ms) | Alerts over 300 ms |
|---|---|---|---|---|---|---|
| restart 1 | run 1 | cold broker | 215 | 501 | 1098 | 122 |
| restart 1 | run 2 | warm | 213 | 28 | 81 | 0 |
| restart 1 | run 3 | warm | 211 | 29 | 90 | 0 |
| restart 2 | run 1 | cold broker | 226 | 399 | 1225 | 123 |
| restart 2 | run 2 | warm | 216 | 29 | 87 | 0 |
| restart 2 | run 3 | warm | 210 | 27 | 101 | 0 |
| restart 3 | run 1 | cold broker | 217 | 360 | 1238 | 112 |
| restart 3 | run 2 | warm | 212 | 27 | 86 | 0 |
| restart 3 | run 3 | warm | 211 | 31 | 112 | 0 |

## E7 Elasticity under a 10x spike

Base 15,000 ev/s, then 10x for 8 s, then base again. `elastic_1to2` starts with one worker and adds a second when total lag stays above 20,000 messages for 1 s (worker start-up and the group rebalance are included). Recovery = seconds after the spike ends until lag stays under one second of base traffic.

| Config | Peak lag (messages) | Recovered | Recovery after spike (s) | p99 during spike (ms) | Scale-out |
|---|---|---|---|---|---|
| fixed_w1 | 764,076 [758,653-818,009] n=5 | 5/5 | 20.1 [18.7-24.5] n=5 | 14,081 [14,028-17,234] n=5 | none |
| fixed_w2 | 365,731 [313,123-520,623] n=5 | 5/5 | 5.8 [4.2-10.9] n=5 | 4,649 [3,645-8,752] n=5 | none |
| elastic_1to2 | 598,768 [516,549-658,735] n=5 | 5/5 | 7.7 [6.6-8.7] n=5 | 6,104 [5,492-7,208] n=5 | 11.5 s after start |

## Data quality

215 runs are included; 0 still-incomplete runs are excluded from all statistics (consumed count differs from sent count).

Set aside earlier:
- e4c/unpinned_w4 rep1: consumed 1,202,699 of 1,000,000 sent (a consumer-group rebalance during the run re-read messages; the harness's readiness check was racy). Fixed and rerun; the original is kept in excluded/.
- e5d/load25.rep0: first run after a broker restart (cold broker): p99 935 ms; reproduced in 3 of 3 restarts (see the E5 cold-start section)
