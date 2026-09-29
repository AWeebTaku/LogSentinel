# E8 Concept drift

    python -m logsentinel.experiments.drift            # results/drift/{results.json,tables.md,figures}

Drift is simulated as a software change that REWORDS the most common log messages from chunk DRIFT_AT onward (the message
text gets a new suffix, so a static model sees message types it never trained on). Because sessions are represented by
counts over a small vocabulary of masked messages, the rewording is applied to that vocabulary: cheap and exactly
reproducible. Conditions: none (control), moderate (top 2 message types, 36% of lines), severe (top 4, 72% of lines).


## Post-drift chunks (4 to 9), mean over chunks

| Drift | Arm | Mean F1 (post-drift chunks) | F1 penalty vs no-drift control | Penalty in the first drifted chunk | Recall penalty | False-positive rate | Mean PR-AUC |
|---|---|---|---|---|---|---|---|
| moderate | static_tuned | 0.025 | -0.841 | -0.683 | +0.000 | 100.00% | 0.934 |
| moderate | static_p99 | 0.025 | -0.840 | -0.683 | +0.000 | 100.00% | 0.934 |
| moderate | retrain_periodic | 0.746 | -0.072 | -0.520 | +0.072 | 16.73% | 0.836 |
| moderate | retrain_triggered | 0.745 | -0.120 | -0.683 | -0.162 | 16.67% | 0.990 |
| moderate | retrain_oracle | 0.760 | -0.088 | -0.690 | +0.078 | 16.72% | 0.961 |
| severe | static_tuned | 0.025 | -0.841 | -0.683 | +0.000 | 100.00% | 0.454 |
| severe | static_p99 | 0.025 | -0.840 | -0.683 | +0.000 | 100.00% | 0.454 |
| severe | retrain_periodic | 0.747 | -0.071 | -0.520 | +0.073 | 16.73% | 0.775 |
| severe | retrain_triggered | 0.745 | -0.120 | -0.683 | -0.162 | 16.67% | 0.859 |
| severe | retrain_oracle | 0.801 | -0.046 | -0.690 | +0.112 | 16.67% | 0.867 |

## No-drift control (same chunks)

| Arm | Mean F1 | False-positive rate |
|---|---|---|
| static_tuned | 0.866 | 0.42% |
| static_p99 | 0.865 | 0.43% |
| retrain_periodic | 0.818 | 0.24% |
| retrain_triggered | 0.865 | 0.43% |
| retrain_oracle | 0.848 | 0.18% |

## F1 per chunk, severe drift (drift starts at chunk 4)

| Arm | c0 | c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 |
|---|---|---|---|---|---|---|---|---|---|---|
| static_tuned | 1.00 | 1.00 | 1.00 | 0.96 | 0.02 | 0.02 | 0.02 | 0.02 | 0.03 | 0.03 |
| static_p99 | 1.00 | 1.00 | 1.00 | 0.96 | 0.02 | 0.02 | 0.02 | 0.02 | 0.03 | 0.03 |
| retrain_periodic | 1.00 | 0.17 | 0.57 | 0.05 | 0.02 | 0.86 | 0.86 | 0.73 | 1.00 | 1.00 |
| retrain_triggered | 1.00 | 1.00 | 1.00 | 0.96 | 0.02 | 0.86 | 0.94 | 0.85 | 0.93 | 0.87 |
| retrain_oracle | 1.00 | 0.17 | 0.52 | 0.40 | 0.02 | 0.87 | 0.99 | 0.98 | 0.94 | 1.00 |
| (anomaly rate) | 1.3% | 3.5% | 5.3% | 3.9% | 1.2% | 1.2% | 0.9% | 1.1% | 1.6% | 1.7% |

## Triggered retraining (unseen-line share above 5%)

- none: retrained at chunks never
- moderate: retrained at chunks [5]
- severe: retrained at chunks [5]

Retrain cost (fit on about 34k sessions): periodic 0.4 s per fit, triggered 0.5 s.

## Sensitivity (severe drift): mean F1 penalty over post-drift chunks

Each row is a separate run; the penalty is against a no-drift control with the same window. Closer to zero is better.

| Window (chunks) | Drift starts at chunk | static_tuned penalty | static_p99 penalty | retrain_periodic penalty | retrain_triggered penalty | retrain_oracle penalty | Triggered at chunks |
|---|---|---|---|---|---|---|---|
| 1 | 3 | -0.847 | -0.847 | -0.002 | -0.043 | -0.049 | [4] |
| 1 | 4 | -0.841 | -0.840 | -0.163 | -0.486 | -0.110 | [5, 9] |
| 1 | 5 | -0.872 | -0.872 | -0.044 | -0.100 | -0.044 | [6] |
| 1 | 6 | -0.924 | -0.923 | -0.246 | -0.658 | -0.244 | [7, 9] |
| 2 | 3 | -0.847 | -0.847 | +0.066 | -0.052 | -0.048 | [4] |
| 2 | 4 | -0.841 | -0.840 | -0.071 | -0.120 | -0.046 | [5] |
| 2 | 5 | -0.872 | -0.872 | -0.158 | -0.222 | -0.087 | [6] |
| 2 | 6 | -0.924 | -0.923 | -0.184 | -0.311 | -0.261 | [7] |
| 3 | 3 | -0.847 | -0.847 | +0.051 | -0.100 | -0.080 | [4] |
| 3 | 4 | -0.841 | -0.840 | -0.063 | -0.119 | -0.114 | [5] |
| 3 | 5 | -0.872 | -0.872 | -0.171 | -0.198 | -0.109 | [6] |
| 3 | 6 | -0.924 | -0.923 | -0.230 | -0.311 | -0.105 | [7] |
