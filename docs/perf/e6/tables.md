# E6: Spark Structured Streaming vs the Python consumer engine

Same model (`hdfs-drain-pca-early`), same events, same rate, both on cores 2-3 (broker core 0, producer core 1); Spark = local mode with 2 cores. 15 s of paced traffic per run, median with min-max over repeats. Latency = alert message timestamp minus the send time of the line that triggered it, incremental alerts only. "Keeping up" = backlog left after the last send is at most 1 s (Python) or 10 s (Spark, about two micro-batches).

## python

Keeps up through **50,000 events/s**
 (keeping up at [1000, 3000, 5000, 10000, 20000, 40000, 50000]).

| Offered ev/s | Runs | Events/s over the consumption window (includes the tail) | Processing capacity (Spark: events per second of batch time) | Backlog after last send (s) | Incremental latency p50 (ms) | p99 (ms) | Engine CPU (cores) | Peak memory (MB) | Alerts (incremental) | False alarms (all runs) | Keeping up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 5 | 1,002 [1,000-1,003] | n/a | 0.0 [0.0-0.0] | 28 [15-49] | 49 [45-58] | 0.07 [0.07-0.08] | 204 [204-204] | 10 [10-10] (4) | 0 | yes |
| 3,000 | 5 | 3,004 [3,000-3,005] | n/a | 0.0 [0.0-0.0] | 32 [24-44] | 56 [50-60] | 0.14 [0.13-0.14] | 207 [207-207] | 21 [20-22] (8) | 0 | yes |
| 5,000 | 5 | 5,003 [4,989-5,004] | n/a | 0.0 [0.0-0.0] | 34 [25-39] | 57 [54-63] | 0.17 [0.17-0.18] | 209 [209-209] | 56 [55-57] (26) | 0 | yes |
| 10,000 | 5 | 10,005 [9,994-10,025] | n/a | 0.0 [0.0-0.1] | 38 [27-44] | 74 [66-90] | 0.26 [0.26-0.27] | 215 [215-215] | 107 [105-108] (40) | 10 | yes |
| 20,000 | 5 | 20,032 [19,928-20,053] | n/a | 0.0 [0.0-0.1] | 56 [51-59] | 104 [99-109] | 0.42 [0.42-0.43] | 226 [226-227] | 222 [220-224] (64) | 15 | yes |
| 40,000 | 5 | 39,908 [39,905-39,916] | n/a | 0.1 [0.1-0.1] | 49 [48-56] | 89 [86-90] | 0.81 [0.80-0.82] | 250 [243-252] | 410 [403-413] (109) | 74 | yes |
| 50,000 | 5 | 49,856 [49,831-49,867] | n/a | 0.1 [0.1-0.1] | 57 [51-62] | 117 [111-139] | 0.99 [0.98-1.00] | 253 [252-253] | 741 [739-743] (360) | 113 | yes |
## spark

Keeps up through **3,000 events/s**
 (keeping up at [1000, 2000, 3000, 5000]).

| Offered ev/s | Runs | Events/s over the consumption window (includes the tail) | Processing capacity (Spark: events per second of batch time) | Backlog after last send (s) | Incremental latency p50 (ms) | p99 (ms) | Engine CPU (cores) | Peak memory (MB) | Alerts (incremental) | False alarms (all runs) | Keeping up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 5 | 792 [759-812] | 793 [759-812] | 4.0 [3.5-4.8] | 2,663 [2,230-2,906] | 4,105 [2,262-4,293] | 1.73 [1.64-1.83] | 1,535 [1,514-1,719] | 8 [8-8] (4) | 0 | yes |
| 2,000 | 5 | 1,426 [1,368-1,505] | 1,427 [1,369-1,506] | 6.1 [4.9-6.9] | 3,774 [3,523-4,839] | 4,712 [3,936-5,254] | 1.87 [1.85-1.89] | 1,684 [1,583-1,789] | 9 [9-9] (4) | 0 | yes |
| 3,000 | 5 | 1,983 [1,822-2,135] | 1,984 [1,823-2,136] | 7.7 [6.1-9.7] | 5,669 [4,785-7,431] | 6,686 [5,513-8,894] | 1.89 [1.77-1.97] | 1,579 [1,542-1,770] | 16 [16-16] (8) | 0 | yes |
| 4,000 | 5 | 2,336 [2,217-2,612] | 2,337 [2,218-2,613] | 10.7 [8.0-12.1] | 8,395 [6,254-8,768] | 9,337 [6,783-11,087] | 1.87 [1.82-1.97] | 1,657 [1,597-1,748] | 26 [26-26] (11) | 0 | no |
| 5,000 | 5 | 3,040 [3,010-3,095] | 3,040 [3,011-3,096] | 9.7 [9.2-9.9] | 8,526 [8,119-8,587] | 12,994 [12,669-13,423] | 2.13 [2.11-2.17] | 1,627 [1,562-1,862] | 47 [47-47] (26) | 0 | yes |
## Side by side at the shared rates

| Offered ev/s | Latency p50: Python / Spark (ms) | p99: Python / Spark (ms) | CPU cores: Python / Spark | Peak memory MB: Python / Spark | Incremental alerts: Python / Spark |
|---|---|---|---|---|---|
| 1,000 | 28 / 2,663 | 49 / 4,105 | 0.07 / 1.73 | 204 / 1,535 | 4 / 4 |
| 3,000 | 32 / 5,669 | 56 / 6,686 | 0.14 / 1.89 | 207 / 1,579 | 8 / 8 |
| 5,000 | 34 / 8,526 | 57 / 12,994 | 0.17 / 2.13 | 209 / 1,627 | 26 / 26 |

Startup (python): median 4.4 s [4.4-4.4], n=35 (process start to first partition assignment / first micro-batch).

Startup (spark): median 14.2 s [13.6-16.9], n=25 (process start to first partition assignment / first micro-batch).

## Spark tuning check at 3,000 events/s

Default = 2 shuffle partitions, at most 50,000 offsets per micro-batch. p1 / p4 = 1 or 4 shuffle partitions; mo10k = at most 10,000 offsets per batch.

| Variant | Runs | Backlog after last send (s) | Incremental latency p50 (ms) | p99 (ms) | Engine CPU (cores) |
|---|---|---|---|---|---|
| spark | 5 | 7.7 [6.1-9.7] | 5,669 [4,785-7,431] | 6,686 [5,513-8,894] | 1.89 [1.77-1.97] |
| spark-p1 | 3 | 12.9 [9.1-13.1] | 6,565 [6,499-6,680] | 6,890 [6,819-7,024] | 1.51 [1.48-1.58] |
| spark-p4 | 3 | 9.5 [6.9-10.7] | 6,565 [6,305-6,931] | 8,693 [7,011-9,825] | 1.89 [1.79-2.04] |
| spark-mo10k | 3 | 9.1 [8.9-9.6] | 6,534 [6,478-6,913] | 8,395 [8,024-8,578] | 1.88 [1.84-1.92] |
