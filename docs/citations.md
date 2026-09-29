# Citation audit (started Week 1)

Method: each reference from the synopsis was looked up on Crossref, then arXiv (script kept out of the repo).
DBLP and OpenAlex were unreachable when I tried (no response / rate-limited), so items marked *confirm* still need a manual DBLP check.
Caveat: Crossref does not index IJCAI, arXiv or ECML, so "not found" means *unconfirmed*, not *fake*.
Every row still needs a manual check on DBLP / Google Scholar before it enters the paper.

| # | Synopsis reference | Finding | Action |
|---|---|---|---|
| 1 | Databricks (2025) blog, Spark Real-Time Mode | Not checked (blog) | Open the URL, record title/date/access date |
| 2 | Bhimanapati & Chandu (2025), IJCESEN 11(4) | **Found**, title/venue match (DOI 10.22399/ijcesen.4367) | Confirm author list; low-tier venue, cite sparingly |
| 3 | Trambadiya (2025), IJERT 15(3) | A similar paper exists but with a **different title and venue** (Int. J. Computer Applications, DOI 10.5120/ijca2025925872) | Fix title/venue; verify the "94.2% sensitivity" claim in the text itself |
| 4 | Zhang et al. (2020), LogAnomaly, ICDM | **Likely misattributed.** LogAnomaly is Meng et al., IJCAI 2019 | Confirm on DBLP, correct authors/venue/year |
| 5 | Du et al. (2017), DeepLog, ACM CCS | **Verified** (DOI 10.1145/3133956.3134015) | Keep |
| 6 | Nedelkoski et al. (2020), Self-Supervised Log Parsing, IEEE ICWS | **Paper verified on arXiv** (2003.07905, Nedelkoski, Bogatinovski, Acker et al., 2020). The arXiv record has no venue; I believe ECML-PKDD 2020, not ICWS (*confirm*) | Cite as arXiv 2003.07905 until the venue is confirmed |
| 7 | Gaikwad (2025), Towards Data Engineering | A same-topic 2025 paper exists with a different title/venue; no author returned | Treat as **unverified**; likely replace |
| 8 | Meng et al. (2019), LogClass, IEEE InfoCom | **Wrong details.** Real: Meng et al., "LogClass: Anomalous Log Identification and Classification With Partial Labels", IEEE TNSM 2021 (DOI 10.1109/tnsm.2021.3055425) | Correct; also fix the description (partial labels, not "weakly supervised XGBoost") |
| 9 | He et al. (2020), "An Evaluation of Log Parsing Tools...", IEEE TDSC | **Not found.** The "13 parsers, Drain best" finding matches Zhu et al., "Tools and Benchmarks for Automated Log Parsing", ICSE-SEIP 2019 (DOI 10.1109/icse-seip.2019.00021) | Replace with the real paper |
| 10 | Landauer et al. (2022), "Deep Clustering for Log Data Analysis", Computers & Security 115 | **Not found.** Real, related: Landauer et al., "Deep learning for anomaly detection in log data: a survey", Machine Learning with Applications 2023 (DOI 10.1016/j.mlwa.2023.100470) | Replace/verify |
| - | Lit-review item "Le & Ivanov (2021), multi-head self-attention" | **Not found**; closest real: Le & Zhang, "Log-based Anomaly Detection Without Log Parsing", ASE 2021 (DOI 10.1109/ase51524.2021.9678773) | Likely conflated; replace |

## Standard references to add (from memory, confirm each before citing)
- Drain: He et al., ICWS 2017 (the parser used in the pipeline).
- Isolation Forest: Liu, Ting, Zhou, ICDM 2008.
- LogBERT: Guo, Yuan, Wu — **verified on arXiv** (2103.04475, 2021); venue IJCNN 2021 (*confirm*).
- LogRobust: Zhang et al., ESEC/FSE 2019.
- Loghub: Zhu et al., arXiv 2008.06448 (2020) — **verified on arXiv** — covers the datasets used here (HDFS_v1, BGL, Thunderbird).

## Corrected reference list (proposed, for the paper's References section)
Use this in place of the synopsis list once each *confirm* item is checked:
- Du, Li, Zheng, Srikumar. DeepLog. ACM CCS 2017. DOI 10.1145/3133956.3134015.
- Meng et al. LogClass: Anomalous Log Identification and Classification With Partial Labels. IEEE TNSM 2021. DOI 10.1109/tnsm.2021.3055425.
- Zhu, He et al. Tools and Benchmarks for Automated Log Parsing. ICSE-SEIP 2019. DOI 10.1109/icse-seip.2019.00021.
- Landauer, Skopik, Wurzenberger, Rauber. Deep learning for anomaly detection in log data: a survey. Machine Learning with Applications 2023. DOI 10.1016/j.mlwa.2023.100470.
- Le, Zhang. Log-based Anomaly Detection Without Log Parsing. ASE 2021. DOI 10.1109/ase51524.2021.9678773.
- Nedelkoski et al. Self-Supervised Log Parsing. arXiv 2003.07905 (2020).
- Guo, Yuan, Wu. LogBERT. arXiv 2103.04475 (2021).
- Zhu et al. Loghub. arXiv 2008.06448 (2020).
- Bhimanapati, Chandu. IJCESEN 2025. DOI 10.22399/ijcesen.4367 (optional, low-tier venue).
- LogAnomaly (Meng et al., IJCAI 2019), Drain (He et al., ICWS 2017), Isolation Forest (Liu, Ting, Zhou, ICDM 2008), LogRobust (Zhang et al., ESEC/FSE 2019): *confirm* on DBLP.
- Drop: Trambadiya and Gaikwad entries unless the exact papers are located; Databricks blog only with a recorded access date.

Net: of 10 reference-list entries, 1 is verified as written (DeepLog), 1 more exists as written (Bhimanapati), and the rest have wrong or unconfirmed details.
