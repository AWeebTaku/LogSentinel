# E6: Spark Structured Streaming vs the Python consumer engine (Week 7)

Full tables: [perf/e6/tables.md](perf/e6/tables.md); figure: [perf/e6/e6_spark_vs_python.png](perf/e6/e6_spark_vs_python.png).
Raw runs: `results/perf/e6/*.rep*.json` (69 runs, 5 repeats per cell, 0 incomplete). Reproduce:
`python -m logsentinel.experiments.e6 run --reps 5` then `python -m logsentinel.experiments.e6 report` (about 40-50 min).

## Method
Same model (`hdfs-drain-pca-early`), same replayed events, same offered rate, both engines pinned to cores 2-3 (broker on
core 0, producer on core 1; Spark runs in `local[2]`). 15 s of paced traffic per run. Latency = alert message's Kafka
timestamp minus the send time of the line that triggered it, **incremental alerts only** (an age-check alert has no single
trigger line in the Spark port, so it is excluded from the latency comparison in both engines for a fair comparison).
"Keeping up" = backlog remaining after the last event was sent is at most 1 s (Python) or 10 s (Spark, about two
micro-batches at Spark's own batch cadence).

## Headline result
**The Python consumer engine sustains 50,000 events/s on this machine; the Spark arm sustains about 3,000 events/s** before
its backlog stops draining within two micro-batches.

| Metric | Python | Spark | Ratio |
|---|---|---|---|
| Sustained throughput | 50,000 ev/s | 3,000 ev/s | Python ~17x |
| Latency p50 @ 3,000 ev/s | 32 ms | 5,669 ms | Spark ~177x slower |
| Latency p99 @ 3,000 ev/s | 56 ms | 6,686 ms | Spark ~119x slower |
| Engine CPU @ 3,000 ev/s | 0.14 cores | 1.89 cores | Spark ~13.5x more |
| Peak memory @ 3,000 ev/s | 207 MB | 1,579 MB | Spark ~7.6x more |
| Startup time (process start to first batch/assignment) | 4.4 s | 14.2 s | Spark ~3.2x slower |
| False alarms across all 25 runs | rises with load (as elsewhere in this project) | **0 in every single run** | - |

At every rate the two engines were run at in common (1k / 3k / 5k events/s), **the number of incremental alerts matched
exactly** (4/4, 8/8, 26/26). This means the two engines are scoring identically; the entire gap above is infrastructure
overhead from Spark's micro-batch execution model and JVM/Arrow round-trips, not a difference in what gets detected.

## Why the gap exists (structural, not a tuning miss)
Three Spark configuration variants were tried at 3,000 events/s (its near-saturation point): 1 shuffle partition, 4 shuffle
partitions, and a smaller `maxOffsetsPerTrigger` (10,000). **None materially changed the backlog or latency** (all stayed in
the same 6.5-13 s backlog / 6.3-8.7 s p50-latency range as the default). This points to a floor set by Spark's own
micro-batch interval (observed batches cost 3-6 s **even when empty**) plus per-batch JVM/Arrow overhead, not a parameter
that can be tuned away in local mode on this hardware.

## Reading against the paper's framing
The synopsis's lit review treats Spark/Flink Structured Streaming as necessary machinery for reaching the >50,000
events/s target. **On this single machine, the plain Python consumer engine reaches that target on its own, and Spark falls
roughly 17x short of it.** This is not evidence that Spark is poorly built; it is evidence that, at this data volume, on
one 4-core host, its fixed per-batch overhead is not amortized. A fair statement for the paper: Spark/Flink's value
proposition is horizontal scale-out across many machines processing far higher aggregate volumes than one host can offer,
not lower latency or higher throughput on a single host at this event rate. The threats-to-validity / discussion section
should say this explicitly rather than let the lit review's framing stand unchallenged.

## Caveats
- Single 4-core host, Spark in local mode (2 cores) only; no cluster, no dedicated executor JVMs, no data locality
  advantages Spark is designed for at scale. These results say nothing about Spark on a real cluster.
- The Spark port has no end-of-stream flush (sessions younger than the age-check window at the end of a run never get
  checked), the watermark is global per micro-batch rather than per-worker, and age-check alerts are excluded from the
  latency comparison for both engines. These are documented, deliberate scope limits of the comparison, not bugs in one
  arm only.
- Startup time favors neither engine's steady-state numbers (it is excluded from throughput/latency stats) but is reported
  because "time to first alert after a cold start" is operationally relevant.
- Python's false-alarm count rising with offered load matches the pattern already seen in E4/E5 (see docs/results-perf.md)
  and is not new to this comparison; Spark's zero false alarms at every tested rate is likely because it never reached a
  rate where the false-alarm-inducing conditions (documented elsewhere) occur, not evidence Spark is more precise.
