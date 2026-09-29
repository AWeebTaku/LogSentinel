# E5 latency excursions: diagnosis

30 instrumented runs, 13,158 alerts; excursion = alerts over 300 ms clustered within 1 s. Pauses considered: broker JVM GC and safepoint pauses of at least 20 ms (62 in the logs).

**3 excursion window(s) in 1 run(s).**

| Run | Start (s into run) | Duration (s) | Slow alerts | Max (ms) | Stage that grew (mean ms) | Other-process CPU on engine cores (% max) | Engine core busy (max) | Min freq (MHz) | JVM pause (ms) |
|---|---|---|---|---|---|---|---|---|---|
| load25-r0 | 0.3 | 2.2 | 10 | 1015 | producer_to_broker (598) | 83 | 0.58 | 3300 | 0  |
| load25-r0 | 2.5 | 1.8 | 13 | 1359 | producer_to_broker (482) | 67 | 0.81 | 3298 | 0  |
| load25-r0 | 5.0 | 7.1 | 73 | 708 | producer_to_broker (494) | 77 | 0.57 | 3300 | 28 (gc:Young, safepoint:G1CollectForAllocation) |

Baseline (556 normal 1 s windows) versus the excursion windows:

| Feature | Normal p50 | Normal p95 | Normal p99 | Excursion median | Excursion max |
|---|---|---|---|---|---|
| Other-process CPU on engine cores (%) | 50.40 | 86.90 | 162.97 | 77.10 | 83.30 |
| Engine core busy | 0.61 | 0.83 | 0.89 | 0.58 | 0.81 |
| Min frequency on engine cores (MHz) | 3300.01 | 3309.81 | 3323.33 | 3299.95 | 3299.97 |
| JVM pause (ms) | 0.00 | 5.04 | 25.30 | 0.00 | 28.07 |

Excursions overlapping a JVM pause of at least 20 ms: 1 of 3; normal windows overlapping one: 5.0%.
