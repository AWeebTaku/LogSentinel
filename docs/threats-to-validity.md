# Threats to validity (draft, feeds the paper's Discussion section)

1. **HDFS_v1 anomalies are front-loaded in time.** 11,158 of 16,838 anomalous blocks (66%) fall in the first 60% of the log.
   The chronological split drops them from train (unsupervised setting), leaving 2.2% anomalies in test (val 3.4%).
   Mitigation: E1 also reports the seeded `random` split (test anomaly rate 2.95%, natural). Report both; the
   chronological split is the headline because it does not mix past and future.
2. **Session-level, not line-level, evaluation.** HDFS labels are per block; BGL/Thunderbird windows are anomalous if any
   line is. Numbers are not comparable to per-line papers.
3. **Thunderbird windows are mostly anomalous.** Only 776 hourly windows exist in the 20M-line prefix, and 62% of the
   chronological test windows (195/313) contain at least one alert line, so precision/F1 are inflated relative to a
   real deployment and AUC/PR-AUC are the more meaningful numbers there. Only 359 normal windows are available for training.
   **Thunderbird is also a prefix.** Only the first 20M of ~211M lines (about three weeks) are used, to fit disk. Results describe that
   period, not the whole dataset.
4. **BGL/Thunderbird label noise.** Labels are alert categories assigned by the operators' tooling; some "normal" lines are
   near-duplicates of "alert" lines. Window labels inherit this.
5. **Threshold tuning on validation** (E3) uses labels; the label-tuned result is an upper bound, not a deployable number.
6. **Single machine.** Throughput/latency results (E4-E7) hold for one 4-core, 15 GB host and do not extrapolate to a cluster.
7. **Synthetic load tests** exercise the pipeline, not detection quality.
