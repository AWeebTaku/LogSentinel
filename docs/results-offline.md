> **Correction added in Week 7.** The BGL results below use sublinear tf-idf features. An ablation (docs/results-ablations.md) shows binary presence features raise BGL PR-AUC from 0.17 to 0.76 (chosen on validation), so the weak BGL numbers here reflect that feature choice, not the limit of the approach. Thunderbird was not re-run.

# Offline results (test split, mean ± std over seeds)

> **Read F1 next to `prevalence`.** A detector that flags everything gets recall 1.0, precision = prevalence and
> F1 = 2p/(1+p) (e.g. 0.768 at 0.623). Rows at that level (Thunderbird chronological, BGL random tuned_val) are
> degenerate; judge them by ROC-AUC / PR-AUC vs prevalence instead.

## E1 detection quality (parser=drain, val-tuned threshold)

| dataset | mode | prevalence | model | roc_auc | pr_auc | precision | recall | f1 |
|---|---|---|---|---|---|---|---|---|
| bgl | chronological | 0.161 | ae | 0.584 ± 0.034 | 0.223 ± 0.066 | 0.216 ± 0.004 | 0.962 ± 0.018 | 0.353 ± 0.006 |
| bgl | chronological | 0.161 | iforest | 0.687 ± 0.008 | 0.296 ± 0.020 | 0.418 ± 0.070 | 0.183 ± 0.043 | 0.254 ± 0.054 |
| bgl | chronological | 0.161 | pca | 0.592 ± 0.000 | 0.171 ± 0.000 | 0.234 ± 0.000 | 0.966 ± 0.000 | 0.377 ± 0.000 |
| bgl | random | 0.171 | ae | 0.940 ± 0.004 | 0.765 ± 0.006 | 0.616 ± 0.041 | 0.769 ± 0.023 | 0.682 ± 0.019 |
| bgl | random | 0.171 | iforest | 0.374 ± 0.016 | 0.155 ± 0.006 | 0.171 ± 0.000 | 1.000 ± 0.000 | 0.292 ± 0.000 |
| bgl | random | 0.171 | pca | 0.985 ± 0.000 | 0.901 ± 0.001 | 0.813 ± 0.000 | 0.914 ± 0.000 | 0.861 ± 0.000 |
| hdfs | chronological | 0.022 | ae | 1.000 ± 0.000 | 0.999 ± 0.000 | 0.997 ± 0.000 | 0.996 ± 0.003 | 0.997 ± 0.002 |
| hdfs | chronological | 0.022 | iforest | 0.990 ± 0.000 | 0.588 ± 0.004 | 0.582 ± 0.001 | 1.000 ± 0.000 | 0.736 ± 0.001 |
| hdfs | chronological | 0.022 | pca | 0.998 ± 0.000 | 0.901 ± 0.002 | 0.883 ± 0.000 | 1.000 ± 0.000 | 0.938 ± 0.000 |
| hdfs | random | 0.030 | ae | 1.000 ± 0.000 | 0.993 ± 0.002 | 0.961 ± 0.011 | 0.996 ± 0.005 | 0.978 ± 0.008 |
| hdfs | random | 0.030 | iforest | 0.984 ± 0.000 | 0.524 ± 0.018 | 0.534 ± 0.032 | 0.934 ± 0.093 | 0.675 ± 0.009 |
| hdfs | random | 0.030 | pca | 0.998 ± 0.000 | 0.894 ± 0.000 | 0.908 ± 0.000 | 0.999 ± 0.000 | 0.951 ± 0.000 |
| thunderbird | chronological | 0.623 | ae | 0.836 ± 0.009 | 0.910 ± 0.005 | 0.623 ± 0.000 | 1.000 ± 0.000 | 0.768 ± 0.000 |
| thunderbird | chronological | 0.623 | iforest | 0.562 ± 0.122 | 0.713 ± 0.047 | 0.623 ± 0.000 | 1.000 ± 0.000 | 0.768 ± 0.000 |
| thunderbird | chronological | 0.623 | pca | 0.845 ± 0.000 | 0.931 ± 0.000 | 0.623 ± 0.000 | 1.000 ± 0.000 | 0.768 ± 0.000 |
| thunderbird | random | 0.476 | ae | 0.796 ± 0.005 | 0.669 ± 0.005 | 0.729 ± 0.012 | 0.915 ± 0.006 | 0.812 ± 0.006 |
| thunderbird | random | 0.476 | iforest | 0.546 ± 0.006 | 0.510 ± 0.002 | 0.499 ± 0.032 | 0.926 ± 0.104 | 0.644 ± 0.002 |
| thunderbird | random | 0.476 | pca | 0.952 ± 0.000 | 0.942 ± 0.000 | 0.885 ± 0.004 | 0.875 ± 0.006 | 0.880 ± 0.002 |

## E2 parser ablation (val-tuned threshold; PR-AUC and F1 per parser)

| dataset | mode | model | pr_auc:drain | pr_auc:raw | pr_auc:regex | f1:drain | f1:raw | f1:regex |
|---|---|---|---|---|---|---|---|---|
| bgl | chronological | ae | 0.223 ± 0.066 | 0.123 ± 0.002 | 0.186 ± 0.019 | 0.353 ± 0.006 | 0.284 ± 0.001 | 0.297 ± 0.014 |
| bgl | chronological | iforest | 0.296 ± 0.020 | 0.530 ± 0.002 | 0.315 ± 0.009 | 0.254 ± 0.054 | 0.478 ± 0.021 | 0.395 ± 0.043 |
| bgl | chronological | pca | 0.171 ± 0.000 | 0.130 ± 0.000 | 0.483 ± 0.002 | 0.377 ± 0.000 | 0.323 ± 0.001 | 0.555 ± 0.023 |
| bgl | random | ae | 0.765 ± 0.006 | 0.169 ± 0.003 | 0.238 ± 0.002 | 0.682 ± 0.019 | 0.300 ± 0.018 | 0.394 ± 0.011 |
| bgl | random | iforest | 0.155 ± 0.006 | 0.350 ± 0.004 | 0.201 ± 0.018 | 0.292 ± 0.000 | 0.450 ± 0.001 | 0.338 ± 0.025 |
| bgl | random | pca | 0.901 ± 0.001 | 0.234 ± 0.000 | 0.381 ± 0.001 | 0.861 ± 0.000 | 0.408 ± 0.001 | 0.477 ± 0.005 |
| hdfs | chronological | ae | 0.999 ± 0.000 | 0.328 ± 0.033 | 0.501 ± 0.004 | 0.997 ± 0.002 | 0.389 ± 0.051 | 0.076 ± 0.015 |
| hdfs | chronological | iforest | 0.588 ± 0.004 | 0.022 ± 0.000 | 0.138 ± 0.024 | 0.736 ± 0.001 | 0.046 ± 0.000 | 0.227 ± 0.036 |
| hdfs | chronological | pca | 0.901 ± 0.002 | 0.149 ± 0.001 | 0.528 ± 0.000 | 0.938 ± 0.000 | 0.187 ± 0.008 | 0.093 ± 0.001 |
| hdfs | random | ae | 0.993 ± 0.002 | 0.293 ± 0.030 | 0.841 ± 0.042 | 0.978 ± 0.008 | 0.369 ± 0.042 | 0.828 ± 0.027 |
| hdfs | random | iforest | 0.524 ± 0.018 | 0.027 ± 0.001 | 0.217 ± 0.016 | 0.675 ± 0.009 | 0.055 ± 0.003 | 0.271 ± 0.020 |
| hdfs | random | pca | 0.894 ± 0.000 | 0.167 ± 0.005 | 0.853 ± 0.001 | 0.951 ± 0.000 | 0.210 ± 0.006 | 0.906 ± 0.003 |
| thunderbird | chronological | ae | 0.910 ± 0.005 | 0.479 ± 0.001 | 0.802 ± 0.004 | 0.768 ± 0.000 | 0.756 ± 0.001 | 0.748 ± 0.016 |
| thunderbird | chronological | iforest | 0.713 ± 0.047 | 0.568 ± 0.018 | 0.790 ± 0.016 | 0.768 ± 0.000 | 0.758 ± 0.002 | 0.572 ± 0.172 |
| thunderbird | chronological | pca | 0.931 ± 0.000 | 0.523 ± 0.000 | 0.898 ± 0.001 | 0.768 ± 0.000 | 0.760 ± 0.000 | 0.717 ± 0.002 |
| thunderbird | random | ae | 0.669 ± 0.005 | 0.459 ± 0.001 | 0.474 ± 0.002 | 0.812 ± 0.006 | 0.644 ± 0.001 | 0.714 ± 0.002 |
| thunderbird | random | iforest | 0.510 ± 0.002 | 0.447 ± 0.013 | 0.549 ± 0.010 | 0.644 ± 0.002 | 0.642 ± 0.009 | 0.676 ± 0.022 |
| thunderbird | random | pca | 0.942 ± 0.000 | 0.518 ± 0.000 | 0.638 ± 0.001 | 0.880 ± 0.002 | 0.645 ± 0.000 | 0.705 ± 0.002 |

## E3 threshold strategies (iforest + drain; oracle_test = best F1 on test, upper bound)

| dataset | mode | prevalence | threshold_rule | threshold | precision | recall | f1 |
|---|---|---|---|---|---|---|---|
| bgl | chronological | 0.161 | percentile99 | 0.467 ± 0.005 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| bgl | chronological | 0.161 | three_sigma | 0.422 ± 0.004 | 0.500 ± 0.000 | 0.011 ± 0.000 | 0.022 ± 0.000 |
| bgl | chronological | 0.161 | tuned_val | 0.349 ± 0.003 | 0.418 ± 0.070 | 0.183 ± 0.043 | 0.254 ± 0.054 |
| bgl | chronological | 0.161 | oracle_test | 0.321 ± 0.001 | - | - | 0.393 ± 0.004 |
| bgl | random | 0.171 | percentile99 | 0.440 ± 0.007 | 0.101 ± 0.025 | 0.007 ± 0.003 | 0.013 ± 0.005 |
| bgl | random | 0.171 | three_sigma | 0.405 ± 0.003 | 0.201 ± 0.023 | 0.045 ± 0.007 | 0.073 ± 0.010 |
| bgl | random | 0.171 | tuned_val | 0.302 ± 0.000 | 0.171 ± 0.000 | 1.000 ± 0.000 | 0.292 ± 0.000 |
| bgl | random | 0.171 | oracle_test | 0.302 ± 0.000 | - | - | 0.292 ± 0.000 |
| hdfs | chronological | 0.022 | percentile99 | 0.692 ± 0.002 | 0.403 ± 0.000 | 0.482 ± 0.000 | 0.439 ± 0.000 |
| hdfs | chronological | 0.022 | three_sigma | 0.685 ± 0.002 | 0.416 ± 0.009 | 0.509 ± 0.019 | 0.458 ± 0.014 |
| hdfs | chronological | 0.022 | tuned_val | 0.656 ± 0.002 | 0.582 ± 0.001 | 1.000 ± 0.000 | 0.736 ± 0.001 |
| hdfs | chronological | 0.022 | oracle_test | 0.656 ± 0.002 | - | - | 0.736 ± 0.001 |
| hdfs | random | 0.030 | percentile99 | 0.698 ± 0.003 | 0.389 ± 0.075 | 0.276 ± 0.089 | 0.322 ± 0.087 |
| hdfs | random | 0.030 | three_sigma | 0.694 ± 0.002 | 0.484 ± 0.133 | 0.282 ± 0.100 | 0.344 ± 0.086 |
| hdfs | random | 0.030 | tuned_val | 0.633 ± 0.005 | 0.534 ± 0.032 | 0.934 ± 0.093 | 0.675 ± 0.009 |
| hdfs | random | 0.030 | oracle_test | 0.628 ± 0.002 | - | - | 0.677 ± 0.009 |
| thunderbird | chronological | 0.623 | percentile99 | 0.559 ± 0.013 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| thunderbird | chronological | 0.623 | three_sigma | 0.515 ± 0.005 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| thunderbird | chronological | 0.623 | tuned_val | 0.332 ± 0.002 | 0.623 ± 0.000 | 1.000 ± 0.000 | 0.768 ± 0.000 |
| thunderbird | chronological | 0.623 | oracle_test | 0.342 ± 0.002 | - | - | 0.786 ± 0.025 |
| thunderbird | random | 0.476 | percentile99 | 0.548 ± 0.010 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| thunderbird | random | 0.476 | three_sigma | 0.514 ± 0.004 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| thunderbird | random | 0.476 | tuned_val | 0.319 ± 0.006 | 0.499 ± 0.032 | 0.926 ± 0.104 | 0.644 ± 0.002 |
| thunderbird | random | 0.476 | oracle_test | 0.316 ± 0.001 | - | - | 0.646 ± 0.002 |

## Model cost (parser=drain): fit seconds, scoring ms per session

| dataset | mode | model | fit_s | score_ms_per_session |
|---|---|---|---|---|
| bgl | chronological | ae | 0.584 ± 0.127 | 0.002 ± 0.001 |
| bgl | chronological | iforest | 0.298 ± 0.008 | 0.021 ± 0.000 |
| bgl | chronological | pca | 0.192 ± 0.035 | 0.005 ± 0.002 |
| bgl | random | ae | 0.502 ± 0.076 | 0.003 ± 0.002 |
| bgl | random | iforest | 0.338 ± 0.023 | 0.028 ± 0.003 |
| bgl | random | pca | 0.121 ± 0.076 | 0.003 ± 0.002 |
| hdfs | chronological | ae | 1.013 ± 0.115 | 0.001 ± 0.001 |
| hdfs | chronological | iforest | 1.505 ± 0.188 | 0.004 ± 0.000 |
| hdfs | chronological | pca | 0.277 ± 0.035 | 0.000 ± 0.000 |
| hdfs | random | ae | 1.046 ± 0.115 | 0.000 ± 0.000 |
| hdfs | random | iforest | 1.376 ± 0.104 | 0.005 ± 0.000 |
| hdfs | random | pca | 0.329 ± 0.081 | 0.000 ± 0.000 |
| thunderbird | chronological | ae | 0.294 ± 0.036 | 0.009 ± 0.002 |
| thunderbird | chronological | iforest | 0.252 ± 0.002 | 0.068 ± 0.002 |
| thunderbird | chronological | pca | 0.176 ± 0.035 | 0.015 ± 0.006 |
| thunderbird | random | ae | 0.316 ± 0.049 | 0.015 ± 0.001 |
| thunderbird | random | iforest | 0.270 ± 0.009 | 0.080 ± 0.001 |
| thunderbird | random | pca | 0.170 ± 0.009 | 0.011 ± 0.007 |
