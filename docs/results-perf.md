# Performance results (Week 6: E4, E5, E7)

Single 4-core host (Intel i5-7400, 15.5 GB), one Kafka 3.9.1 broker, Python engine workers, model `hdfs-drain-pca-early`.
215 runs (185 in the main set plus 30 instrumented E5 repeats) and 9 cold-start test runs; 5 repeats per cell in the main set (interleaved across cells), median with min-max. Full tables: [perf/tables.md](perf/tables.md),
raw statistics: [perf/tables.csv](perf/tables.csv), figures: `perf/*.png`. Reproduce: `make perf` then `make perf-report`
(about 2 hours; close other applications first). Diagnosis of the E5 excursions: `perf run --only e5d --reps 10` then
`python -m logsentinel.experiments.e5_diagnose`.

## Headline numbers
| Question | Answer | Where |
|---|---|---|
| How fast can one engine worker consume with a healthy backlog? | **50,000 events/s** sustained (49.5k consumed, 0.1 s backlog, p99 111 ms). 55,000 fails (p99 969 ms). | E4a |
| Two workers? | **70,000 events/s** sustained (p99 419 ms, close to the limit). 80,000 fails (p99 603 ms). | E4a |
| Burst capacity (backlog draining as fast as possible) | 1 worker 54.7k; 2 workers 88-96k; 4 workers 114k (unpinned, all cores shared) | E4b, E4c |
| Event-to-alert latency below saturation, warm broker | Typical run: p99 **about 85-120 ms** at 25 / 50 / 75% of one worker's saturation. Pooled over all alerts of 44 warm runs: p99 **102 / 116 / 612 ms**, with 0.4% / 0% / 2.5% of alerts over 500 ms; the 612 comes from one run with an unexplained 8 s slowdown. | E5 |
| First minute after a broker restart | Cold broker: p50 360-501 ms and p99 1.1-1.2 s for the first paced run (3 of 3 restarts), producer-to-broker stage; warm runs after it: p99 81-112 ms (0 of 6 affected) | E5 cold start |
| Where the time goes | engine micro-batch update 17-37 ms, consumer fetch path (p99 about 72 ms); scoring only about 1 ms; alert emit 0.1 ms | E5 |
| Effect of tuning | batch 500: -9% capacity; batch 8000, lz4 compression, linger 0 and 20 ms: no measurable effect (inside run-to-run noise) | E4b |
| 10x traffic spike (15k to 150k events/s for 8 s) | 1 worker: peak lag 764k messages, back to normal 20 s after the spike; 2 workers: 366k, 5.8 s; 1 worker with reactive scale-out to 2: 599k, 7.7 s | E7 |

## Reading against the paper's targets
- **More than 50,000 events/s with under 500 ms:** met, narrowly, by one worker (50k sustained, 55k not). Two workers give 70k.
  These are HDFS log lines with model scoring included, on one machine, so this supports the claim for this setup only.
- **Sub-second processing:** typical below saturation (p99 about 100 ms). Two runs of 44 warm-broker runs (4.5%) had unexplained
  stalls with p99 of 830 ms and 661 ms, and a freshly restarted broker adds about 0.5 s to the producer-to-broker hop for its first
  minute. The paper's "p99 under 500 ms" is therefore supported as a typical, warm-broker figure, not as a bound. Above capacity
  latency grows with the backlog (seconds), as E7 shows.
- **"Elastic":** scale-out reduced recovery after the spike from 20 s to 7.7 s and the peak lag by 22%, but it did not stop
  latency from exceeding 500 ms during the spike (p99 6.1 s). A pre-provisioned second worker did better (5.8 s, p99 4.6 s).
  Timeline (measured): the scale-out was requested 1.5 to 2.5 s into the spike (1 s lag hold plus polling) and the new worker's
  first metrics arrived 2.2 s later (range 2.1-2.6 s, 1 s resolution), so it added capacity for only the last ~4 s of the 8 s
  spike. A faster trigger or a pre-warmed spare worker would help; that was not tested. Nothing tested keeps latency under
  500 ms through a 10x spike; the choice is between over-provisioning and accepting a queueing period.

## What limits throughput
- **The engine's CPU**, not Kafka: at 50k events/s one worker uses about 1.2 cores while broker CPU is about 2.6 s and
  producer CPU about 1.9 s over a 10 s run. Producer compression and linger changed nothing.
- **Cores available:** roughly 1.2 cores per 50k events/s. Two workers pinned to two cores reach 1.61x (81% efficient);
  four workers squeezed onto those two cores are slower than two (1.44x). With all four cores shared, 4 workers reach 2.08x.
  So scaling here is bounded by the machine, not by the design; a real cluster needs its own measurement.
- **Micro-batch size trades latency for throughput:** engine update time sits near 37 ms once a full 2,000-message batch
  forms; batch 500 lowers that but costs about 9% capacity.

## Caveats
- **Latency excursions: what is explained and what is not.** *Explained:* a cold broker. The first paced run after any broker
  restart has p99 of 1.1-1.2 s (3 of 3 restarts, 4 cold runs in total including one in the instrumented set), all of it in the
  producer-to-broker stage; runs 2 and 3 after each restart are normal, and a burst warm-up does not prevent it. Not caused by CPU
  frequency (stable at 3.3 GHz), JVM pauses (at most 28 ms) or competing processes (the same as in normal windows). Cold runs are
  now flagged automatically (broker uptime under 45 s), excluded from steady-state statistics and reported separately, and the
  runner does a paced warm-up first. My best guess at the mechanism (JIT compilation on the broker's single pinned core) is a
  hypothesis: it was not tested. *Not explained:* two stalls in the original, uninstrumented E5 runs on a broker that had been up
  for hours (`load25-r4`: 0.7 s in producer-to-broker; `load75-r0`: 8 s of consumer-side delay). None of the 29 instrumented warm runs
  had one, so no sampler or GC data exists for them; they stay in the statistics. Rate: 2 of 44 warm runs. Diagnosis details:
  [perf/e5-diagnosis.md](perf/e5-diagnosis.md). Operational note: warm a restarted broker with synthetic traffic before cutting over.
- One machine shared with the desktop and a `powersave` CPU governor. Repeats are interleaved to spread this noise, not remove it.
  The recorded load average includes the benchmark's own previous run, so it says nothing about other applications.
- Per-run p99 comes from roughly 100 to 700 alerts, so it is noisy at the top (86-204 ms at 50k events/s). Medians of five runs are
  reported with the ranges.
- Latency is measured for the lines that triggered an alert (about 1.5% of sessions), not for every event. Broker append time has
  1 ms resolution; stage values are clamped at 0 when rounding makes them negative.
- Fewer partitions helped two workers (2 partitions 96k vs 6 partitions 88k, 12 partitions 87k) but the ranges overlap; treat it as
  a hint.
- The 2-worker sweep brackets the limit between 70k and 80k; it was not refined further. Rates between tested points were not run.
- Replays use test sessions but performance runs slice the replay list, so sessions can be partial: accuracy is not measured here
  (see the Week 3 results for detection quality).

## Data quality
One of the first 180 runs (E4c, 4 workers, unpinned) consumed 1,202,699 events although 1,000,000 were sent. Cause: the harness's
worker-readiness check trusted stale files, so the producer started while the consumer group was still rebalancing; a partition
moved mid-run and about 200k messages were re-read from the last committed offset (Kafka at-least-once behavior). It was excluded
by the integrity check, a stricter check (stable assignment for 3 s) now guards the harness, the source supervisor and the
benchmark script (with a regression test), and the cell was rerun. The original run is kept in `results/perf/e4c/excluded/`.
Consequence to keep in mind: the engine is at-least-once with auto-commit, so a rebalance in production can double-count the
lines of open sessions; alerts are deduplicated by the sink, but session counts are not.
