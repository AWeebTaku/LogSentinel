# Ablations (Week 7)

Which design choices matter. HDFS and BGL, chronological split, threshold tuned on validation, metrics on test. Full tables:
[ablations/tables.md](ablations/tables.md). Reproduce: `python -m logsentinel.experiments.ablations` (under a minute).

**How to read the selection lines.** I first looked at the test tables, which is the wrong order, so each table now also shows validation
PR-AUC and a "selected on validation" line: the setting a practitioner would have picked without seeing test. Both large effects below
were also the validation choice.

| Question | HDFS | BGL |
|---|---|---|
| Does Drain's similarity threshold (0.3-0.6) or depth (3-5) matter? | **No.** All 12 combinations give identical results (20 templates, PR-AUC 0.904, F1 0.938) | Essentially flat (PR-AUC 0.171-0.172, 138 to 199 templates) |
| Does feature weighting matter? | Little on F1. tf-idf 0.942 PR-AUC vs sublinear tf-idf 0.904, counts 0.930, binary 0.828 | **Yes, a lot.** Binary presence: PR-AUC **0.764**, ROC-AUC 0.906, F1 0.555. Sublinear tf-idf (used so far): PR-AUC 0.172, ROC-AUC 0.592, F1 0.377. Validation picks binary too (0.912 vs 0.635) |
| PCA variance kept (0.90-0.999) | **0.99 is much better than the 0.95 default**: PR-AUC 0.999 vs 0.904, F1 0.994 vs 0.938 (validation: 0.999 vs 0.826). 0.999 is worse again (0.956 / 0.934) | No effect (0.157-0.172) |
| Autoencoder bottleneck (4, 8, 16, 32) | 16 is the validation choice: F1 0.998; 4 gives 0.938 | No useful setting: PR-AUC 0.16-0.18 |

## What this means
- **The BGL result in E1 was pessimistic because of the feature weighting I chose.** With tf-idf weighting on 1-hour windows (about 1,500 lines
  each) the frequent messages dominate; the presence of a message type is the signal. E1's BGL numbers should be read as "tf-idf features",
  not as the limit of the approach. Thunderbird (also windows) was not re-run and probably has the same issue.
- **HDFS with PCA at 99% variance reaches F1 0.994.** The 95% default came from the literature, not from tuning here. This is a
  validation-selected improvement for the streaming model, but it is NOT applied: the streaming bundle, the age-check study (E-early) and the
  Week 3 to 6 numbers all use 0.95. Adopting it means retraining the bundle and re-running those checks.
- **Drain parameters are not worth tuning on these datasets.** The parser choice (E2) matters; its settings do not.

## Caveats
- Single split per dataset; BGL validation has only 46 anomalies, and validation and test PR-AUC differ a lot for some BGL settings
  (for example sublinear tf-idf 0.635 validation versus 0.172 test), so treat BGL differences below about 0.1 PR-AUC as noise.
- PCA 0.99 vs 0.999 on HDFS is non-monotonic (0.999 is worse): the variance setting is sensitive, so re-validate it if the data change.
- Only one axis is varied at a time; interactions (for example binary features with Drain settings) were not explored.
- Autoencoder is the small sklearn MLP capped at 25 epochs (convergence warnings appear), so its bottleneck comparison is limited by training length.
