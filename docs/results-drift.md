# E8: concept drift (Week 7)

Static model versus retraining when the log wording changes mid-stream. Full tables, per-chunk F1 and the sensitivity grid:
[drift/tables.md](drift/tables.md); figure: `drift/e8_drift.png`. Reproduce: `python -m logsentinel.experiments.drift` (about 2 minutes).

## What was simulated
HDFS test split cut into 10 chronological chunks. From chunk 4 on, the most common message types are reworded (a new suffix, as after a
software update): **moderate** = top 2 types (36% of lines), **severe** = top 4 (72%). Detector: Drain + PCA, as in the streaming path.
This is simulated drift on one dataset, abrupt, one realization per setting. Anomaly rates differ by chunk (0.9% to 5.3%), so every
result is read against the same arm's **no-drift control**.

## Results
| Finding | Evidence |
|---|---|
| A static model fails completely when a third or more of the lines are reworded | Its fixed threshold flags **100% of sessions**; F1 0.87 (control) falls to 0.03. F1 penalty -0.84 to -0.92 in all 12 sensitivity settings |
| Ranking survives moderate drift but not severe drift | PR-AUC 0.93 (moderate) versus 0.45 (severe): with moderate drift only the threshold is broken, with severe drift the scores are |
| An unlabeled drift signal exists and is clean | Share of lines the model has never seen: 0.05-0.1% before the drift, **46% (moderate) / 92% (severe)** in the first drifted chunk; 0 false triggers in the control |
| Retraining recovers within one chunk of the drift being visible | Triggered retraining fires at chunk 5 (drift at chunk 4); F1 0.86 to 0.94 afterwards, mean 0.745 over chunks 4-9 (the lost chunk 4 is included) |
| Refit is cheap | 0.4-0.5 s per fit on about 34,000 sessions (Drain + tf-idf + PCA); the delay is detection granularity, not compute |
| **Periodic retraining on raw windows is unstable** | In chunks 1-3 (anomaly rate 3.5-5.3%) its F1 is **0.17 / 0.57 / 0.05** even with no drift, versus 1.0 for the static model: anomalies in the window teach the model that they are normal. Triggered retraining does not have this problem because it does not retrain when nothing changed |
| Removing anomalies from the window helps, but is not the whole story | Oracle (labels used to clean the window): post-drift F1 0.80 (severe) vs 0.75 for periodic; still penalty -0.05 to -0.26 across the sensitivity grid |

## Sensitivity
Severe drift, drift point chunk 3-6, window 1-3 chunks: static always -0.84 to -0.92. The retraining arms range from +0.07 to -0.66;
window 2-3 gives -0.05 to -0.31 for most settings. With a one-chunk window the triggered arm sometimes re-triggers (chunk 9) on a
model fitted to a single window and does worse (-0.49, -0.66), so the window should span at least two chunks.

## Reading
- If the wording of logs can change, a fixed model plus a fixed threshold is not safe; the failure is silent unless you watch the share of
  unseen lines.
- The cheap, label-free trigger (unseen-line share above 5%) detected all simulated drift and never fired without it. Retraining on a
  contaminated recent window is fragile when anomalies are frequent, so retrain on trigger rather than on a schedule, and prefer a
  window of two or more chunks. Trimming the highest-scoring sessions from the window before refitting is an obvious next step; it was
  not tested.

## Caveats and what is not done
- Simulated rewording of the most common messages, not real drift; gradual drift, new message types and changes in message frequency
  were not tested. One dataset (HDFS), one realization per setting (no confidence intervals).
- The static arm's tuned threshold uses labels (an optimistic baseline); the retraining arms use an unsupervised percentile threshold.
- Chunks are about 17,000 sessions, so "one chunk of delay" is coarse. This is an offline simulation over scored sessions. The engine
  cannot hot-swap a model yet, so the UI's drift scenario stays disabled.
