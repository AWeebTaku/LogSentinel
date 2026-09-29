# Ablations

    python -m logsentinel.experiments.ablations         # results/ablations/{results.json,tables.md}

A1 Drain similarity threshold x tree depth (PCA detector)     A2 feature weighting (Drain + PCA)
A3 PCA variance kept (Drain, tf-idf)                           A4 autoencoder bottleneck size (Drain, tf-idf, 3 seeds)


## HDFS (test prevalence 2.2%; a detector that flags everything gets F1 0.042)

### A1 Drain similarity threshold x depth

| sim_th | depth | templates | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|---|---|
| 0.3 | 3 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.3 | 4 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.3 | 5 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.4 | 3 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.4 | 4 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.4 | 5 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.5 | 3 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.5 | 4 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.5 | 5 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.6 | 3 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.6 | 4 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.6 | 5 | 20 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |

### A2 Feature weighting

| weighting | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|
| tfidf_sublinear | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| tfidf | 0.851 | 0.942 | 0.999 | 0.938 | 0.884 | 1.000 |
| counts | 0.823 | 0.930 | 0.998 | 0.924 | 0.875 | 0.979 |
| binary | 0.793 | 0.828 | 0.997 | 0.938 | 0.883 | 1.000 |

Selected on validation PR-AUC: **weighting = tfidf** (test PR-AUC 0.942, F1 0.938); the current default tfidf_sublinear gives test PR-AUC 0.904, F1 0.938.


### A3 PCA variance kept

| variance | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|
| 0.9 | 0.824 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.95 | 0.826 | 0.904 | 0.998 | 0.938 | 0.883 | 1.000 |
| 0.99 | 0.999 | 0.999 | 1.000 | 0.994 | 0.997 | 0.991 |
| 0.999 | 0.956 | 0.956 | 0.999 | 0.934 | 0.877 | 1.000 |

Selected on validation PR-AUC: **variance = 0.99** (test PR-AUC 0.999, F1 0.994); the current default 0.95 gives test PR-AUC 0.904, F1 0.938.


### A4 Autoencoder bottleneck (median of 3 seeds)

| bottleneck | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|
| 4 | 0.826 | 0.930 | 0.999 | 0.938 | 0.883 | 1.000 |
| 8 | 0.959 | 0.992 | 1.000 | 0.938 | 0.884 | 0.999 |
| 16 | 0.999 | 0.999 | 1.000 | 0.998 | 0.997 | 0.999 |
| 32 | 0.999 | 0.999 | 1.000 | 0.994 | 0.997 | 0.992 |

Selected on validation PR-AUC: **bottleneck = 16** (test PR-AUC 0.999, F1 0.998).


## BGL (test prevalence 16.1%; a detector that flags everything gets F1 0.278)

### A1 Drain similarity threshold x depth

| sim_th | depth | templates | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|---|---|
| 0.3 | 3 | 138 | 0.637 | 0.171 | 0.591 | 0.355 | 0.216 | 1.000 |
| 0.3 | 4 | 147 | 0.635 | 0.171 | 0.591 | 0.377 | 0.234 | 0.966 |
| 0.3 | 5 | 156 | 0.634 | 0.171 | 0.591 | 0.376 | 0.234 | 0.966 |
| 0.4 | 3 | 146 | 0.639 | 0.172 | 0.592 | 0.377 | 0.234 | 0.966 |
| 0.4 | 4 | 153 | 0.635 | 0.172 | 0.592 | 0.377 | 0.234 | 0.966 |
| 0.4 | 5 | 156 | 0.634 | 0.171 | 0.591 | 0.376 | 0.234 | 0.966 |
| 0.5 | 3 | 148 | 0.636 | 0.171 | 0.592 | 0.377 | 0.234 | 0.966 |
| 0.5 | 4 | 155 | 0.635 | 0.171 | 0.592 | 0.377 | 0.234 | 0.966 |
| 0.5 | 5 | 158 | 0.634 | 0.171 | 0.591 | 0.376 | 0.234 | 0.966 |
| 0.6 | 3 | 189 | 0.636 | 0.171 | 0.592 | 0.372 | 0.230 | 0.971 |
| 0.6 | 4 | 196 | 0.636 | 0.171 | 0.591 | 0.358 | 0.218 | 1.000 |
| 0.6 | 5 | 199 | 0.636 | 0.171 | 0.591 | 0.372 | 0.230 | 0.971 |

### A2 Feature weighting

| weighting | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|
| tfidf_sublinear | 0.635 | 0.172 | 0.592 | 0.377 | 0.234 | 0.966 |
| tfidf | 0.567 | 0.176 | 0.601 | 0.363 | 0.223 | 0.971 |
| counts | 0.153 | 0.356 | 0.724 | 0.361 | 0.236 | 0.766 |
| binary | 0.912 | 0.764 | 0.906 | 0.555 | 0.429 | 0.789 |

Selected on validation PR-AUC: **weighting = binary** (test PR-AUC 0.764, F1 0.555); the current default tfidf_sublinear gives test PR-AUC 0.172, F1 0.377.


### A3 PCA variance kept

| variance | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|
| 0.9 | 0.565 | 0.170 | 0.586 | 0.372 | 0.229 | 0.989 |
| 0.95 | 0.635 | 0.172 | 0.592 | 0.377 | 0.234 | 0.966 |
| 0.99 | 0.639 | 0.167 | 0.580 | 0.369 | 0.226 | 1.000 |
| 0.999 | 0.588 | 0.157 | 0.545 | 0.364 | 0.224 | 0.977 |

Selected on validation PR-AUC: **variance = 0.99** (test PR-AUC 0.167, F1 0.369); the current default 0.95 gives test PR-AUC 0.172, F1 0.377.


### A4 Autoencoder bottleneck (median of 3 seeds)

| bottleneck | Validation PR-AUC | Test PR-AUC | Test ROC-AUC | Test F1 | Test precision | Test recall |
|---|---|---|---|---|---|---|
| 4 | 0.345 | 0.171 | 0.559 | 0.342 | 0.208 | 0.989 |
| 8 | 0.392 | 0.160 | 0.554 | 0.337 | 0.205 | 0.977 |
| 16 | 0.455 | 0.177 | 0.561 | 0.351 | 0.214 | 0.971 |
| 32 | 0.482 | 0.158 | 0.548 | 0.353 | 0.218 | 0.977 |

Selected on validation PR-AUC: **bottleneck = 32** (test PR-AUC 0.158, F1 0.353); the current default 16 gives test PR-AUC 0.177, F1 0.351.

