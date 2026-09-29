const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, BorderStyle, ImageRun, AlignmentType, ShadingType, PageBreak,
  LevelFormat, convertInchesToTwip, TableOfContents, ExternalHyperlink, PositionalTab,
  PositionalTabAlignment, PositionalTabLeader
} = require("docx");

const FIGDIR = "/home/adu/Projects/SEM III-IV Research and Project/logsentinel";

// ---------- helpers ----------------------------------------------------------------
const CW = 9026; // content width in DXA at A4 with 1in margins (11906 - 2*1440)

function h1(text) { return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 200 } }); }
function h2(text) { return new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 140 } }); }
function h3(text) { return new Paragraph({ text, heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 100 } }); }

function p(text, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun(text)];
  return new Paragraph({ children: runs, spacing: { after: 160, line: 300 }, alignment: opts.align || AlignmentType.JUSTIFIED, ...opts });
}
function b(text) { return new TextRun({ text, bold: true }); }
function i(text) { return new TextRun({ text, italics: true }); }
function t(text) { return new TextRun(text); }

function bullet(children, level = 0) {
  return new Paragraph({ children: Array.isArray(children) ? children : [new TextRun(children)], numbering: { reference: "bullets", level }, spacing: { after: 100, line: 280 } });
}

function caption(text) {
  return new Paragraph({ children: [new TextRun({ text, italics: true, size: 20 })], alignment: AlignmentType.CENTER, spacing: { after: 260, before: 60 } });
}

function cell(text, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text: String(text), bold: !!opts.bold, size: opts.size || 18 })];
  return new TableCell({
    width: { size: opts.width, type: WidthType.DXA },
    shading: opts.shade ? { type: ShadingType.CLEAR, fill: opts.shade } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({ children: runs, alignment: opts.align || AlignmentType.LEFT })],
    verticalAlign: "center",
  });
}

function dataTable(headers, rows, widthsFrac) {
  const widths = widthsFrac.map((f) => Math.round(CW * f));
  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((hd, idx) => cell(hd, { bold: true, width: widths[idx], shade: "D9E2F3", size: 18 })),
  });
  const bodyRows = rows.map(
    (r) => new TableRow({ children: r.map((c, idx) => cell(c, { width: widths[idx], size: 18 })) })
  );
  return new Table({
    width: { size: CW, type: WidthType.DXA },
    columnWidths: widths,
    rows: [headerRow, ...bodyRows],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "CCCCCC" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "CCCCCC" },
    },
  });
}

function figure(relPath, widthPx, imgW, imgH, capText) {
  const heightPx = Math.round(widthPx * (imgH / imgW));
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(`${FIGDIR}/${relPath}`), transformation: { width: widthPx, height: heightPx } })],
    }),
    caption(capText),
  ];
}

function hr() {
  return new Paragraph({ text: "", border: { bottom: { color: "AAAAAA", space: 1, style: BorderStyle.SINGLE, size: 6 } }, spacing: { after: 200 } });
}

function ref(text) {
  return new Paragraph({ children: [new TextRun(text)], indent: { left: 720, hanging: 720 }, spacing: { after: 140, line: 276 } });
}

// ---------- content ------------------------------------------------------------------

const titlePage = [
  new Paragraph({ text: "", spacing: { before: 1200 } }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 300 },
    children: [new TextRun({ text: "Architecting an Elastic, High-Throughput Pipeline for", bold: true, size: 32 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 300 },
    children: [new TextRun({ text: "Real-Time Distributed Log Analytics and Unsupervised Anomaly Detection", bold: true, size: 32 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 700 },
    children: [new TextRun({ text: "An Empirical System and Evaluation", italics: true, size: 24, color: "555555" })],
  }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [new TextRun({ text: "M.Sc. Computer Science — Semester III–IV Research Project", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 700 }, children: [new TextRun({ text: "[Candidate Name]", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new TextRun({ text: "Advisor: [Advisor Name]", size: 20, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new TextRun({ text: "[Institution Name]", size: 20, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1200 }, children: [new TextRun({ text: "[Submission Date]", size: 20, color: "555555" })] }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 60 },
    children: [new TextRun({ text: "Reference implementation: LogSentinel", size: 18, italics: true, color: "777777" })],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

const abstract = [
  h1("Abstract"),
  p([t("Modern enterprise software architectures generate immense volumes of heterogeneous log data across distributed cloud infrastructures. Traditional batch-based log parsing frameworks fail to detect operational failures or malicious security anomalies at sub-second latencies, prolonging Mean Time to Resolution (MTTR). This paper presents "), b("LogSentinel"), t(", an end-to-end system that ingests, parses, and analyzes streaming log data using Apache Kafka for event brokering, a batch-scoring Python consumer engine for real-time inference, and unsupervised machine learning (Isolation Forest, PCA reconstruction error, and a small autoencoder) for anomaly detection, bypassing the constraints of static rule-based alerting.")]),
  p([t("Unlike prior attempts at this problem — including two earlier iterations documented in this project's own history — every claim reported here is backed by a reproducible experiment: 8 research questions (E1–E8), 215+ benchmark runs with repeats and interleaving to control for host noise, and a full-stack application (streaming engine, REST API, and web dashboard) used to produce the evidence, not just to demonstrate it. On real LogHub datasets (HDFS_v1, BGL, and a 20-million-line Thunderbird prefix), a single Python consumer worker sustains "), b("50,000 events/second"), t(" with an event-to-alert p99 latency of 111 ms, meeting the throughput target this project set out to test. A companion Apache Spark Structured Streaming implementation of the identical detection logic was built and benchmarked head-to-head: on this single-host testbed, Spark sustains roughly 3,000 events/second — about 17× lower — at 120–250× higher latency and 13× higher CPU use than the Python engine, for byte-identical detections. Detection quality reaches F1 = 0.938 (PR-AUC 0.901) on HDFS_v1 at the session level; an early-detection mechanism recovers 40% of anomalous sessions that a naive incremental classifier misses entirely, raising live F1 from 0.691 to 0.923. A concept-drift study shows that a static model's precision collapses to near zero within one measurement window of a wording change in the logs, and that a cheap, label-free drift signal (the share of never-before-seen log lines) triggers a corrective retrain that recovers F1 to 0.745 within one detection window. All findings, including two limitations that could not be fully explained, are reported with their numeric evidence and are reproducible from a public, tested code path.")]),
  new Paragraph({ children: [new PageBreak()] }),
];

const introduction = [
  h1("1. Introduction"),
  p("With the shift to microservices and distributed computing, telemetry monitoring has moved from retrospective log inspection toward proactive, real-time operational and security intelligence. A production service today can emit millions of log lines per minute across hundreds of hosts; the operational question is no longer whether an anomaly occurred, but whether it can be surfaced to a human before it becomes an incident."),
  h2("1.1 Problem Statement"),
  p("Traditional log management relies on periodic batch indexing (cron-driven ETL, or standard ELK-stack ingestion without a streaming compute layer). Under sustained or bursty traffic, such systems accumulate ingest latency and resource contention. Deterministic alerting rules — string matches, static thresholds — are brittle: they cannot generalize to novel failure modes or attack patterns that were not anticipated when the rule was written, and they require constant manual maintenance as systems evolve."),
  h2("1.2 Proposed Solution"),
  p("This project designs, builds, and empirically evaluates a stateful streaming pipeline that treats log processing as an in-flight vectorization and classification task rather than a store-then-query workload. Unstructured log lines are parsed into a bounded vocabulary of message templates (via the Drain parsing algorithm), converted to numerical feature vectors, and scored by an unsupervised model trained only on normal system behavior — no attack signatures or labeled anomalies are required at training time. When a session's anomaly score crosses a threshold, an alert is published within milliseconds of the underlying evidence arriving."),
  p("Critically, this project treats the claims of the original research synopsis — throughput targets, latency targets, the necessity of a distributed stream-processing framework such as Spark or Flink, and the value of periodic model retraining under drift — as hypotheses to be tested rather than assumptions to be illustrated. Every number in Section 6 (Results) comes from an executed, logged, and version-controlled experiment; where a hypothesis was not supported by the data (most notably, the necessity of Spark at this scale), this paper reports that outcome and reasons about why."),
  h2("1.3 Scope of the Study"),
  bullet([b("Architectural focus: "), t("design and evaluation of a three-tier streaming system — ingestion/brokerage, real-time stream analytics, and unsupervised inference — plus a supporting operator UI and REST API used to collect and triage results.")]),
  bullet([b("Data domain: "), t("real, publicly available semi-structured log corpora (HDFS_v1, BGL, Thunderbird) from the LogHub collection, at session/window granularity appropriate to each dataset's label scheme, plus synthetic replay for controlled load and scenario testing.")]),
  bullet([b("Performance envelope: "), t("throughput, latency, elasticity under load spikes, and engine choice (Python vs. Apache Spark) are measured on a single 4-core commodity host with full disclosure of that constraint; no cluster deployment was available for this study.")]),
  bullet([b("Exclusions: "), t("automated remediation (e.g., auto-restart, auto-scaling of the monitored service) is out of scope; the operator UI is a supporting artifact for triage and experiment control, not the primary research contribution — the pipeline, its models, and its empirical performance are.")]),
  new Paragraph({ children: [new PageBreak()] }),
];

const related = [
  h1("2. Related Work"),
  p("An initial literature pass for this project's synopsis included several references that, on later verification against Crossref, arXiv, and publisher metadata, proved to be misattributed, mis-cited, or unlocatable — a known failure mode when a literature list is assembled without checking each entry independently. That audit is preserved in full in the project repository (docs/citations.md) for transparency. The reference list below has been corrected: verified entries are cited as verified; unverifiable claims from the original synopsis are either dropped or explicitly flagged for the candidate to confirm on DBLP before final submission, rather than silently carried forward."),
  h2("2.1 Log parsing and template mining"),
  p([t("He et al. introduce "), i("Drain"), t(", a fixed-depth parse-tree algorithm for online log template mining, used throughout this project as the parsing front end [1]. Zhu et al. benchmark a wider set of log parsers and establish "), i("Loghub"), t(", the public log corpus collection this project draws its HDFS_v1, BGL, and Thunderbird datasets from [2, 3].")]),
  h2("2.2 Deep and sequence-based log anomaly detection"),
  p([t("Du et al. propose "), i("DeepLog"), t(", modeling normal log key sequences with an LSTM and flagging deviations as anomalies — the first widely cited deep-sequence approach to unsupervised log anomaly detection [4]. Guo, Yuan, and Wu propose "), i("LogBERT"), t(", a self-supervised Transformer pretraining scheme for the same task [5]. This project deliberately evaluates lighter-weight, classical unsupervised models (Isolation Forest, PCA reconstruction error, and a small autoencoder) instead, trading model capacity for the inference-latency budget that real-time scoring at high throughput demands; Section 6 quantifies that trade-off directly (per-session scoring cost of roughly 1 ms; see Section 6.5).")]),
  h2("2.3 Weakly and partially supervised classification"),
  p([t("Meng et al. present "), i("LogClass"), t(", an anomalous log identification and classification approach using partial labels [6]. Le and Zhang show that competitive log anomaly detection is achievable without an explicit parsing stage, a design point this project's own parser ablation (Section 6.2) partially corroborates for one of its three datasets [7].")]),
  h2("2.4 Surveys and self-supervised parsing"),
  p([t("Landauer et al. survey deep-learning approaches to log anomaly detection broadly [8]. Nedelkoski et al. propose a self-supervised approach to log parsing that removes the need for hand-tuned regular expressions [9].")]),
  h2("2.5 Classical unsupervised anomaly detection"),
  p([t("Liu, Ting, and Zhou introduce "), i("Isolation Forest"), t(", one of the three detectors evaluated in this project [10].")]),
  h2("2.6 Stream processing frameworks"),
  p("This project's original synopsis asserted that a distributed stream-processing framework (Apache Spark Structured Streaming or Apache Flink) is necessary machinery for reaching high-throughput, low-latency log analytics. Section 6.6 reports a controlled, same-model, same-data comparison between a Python consumer-group engine and a Spark Structured Streaming implementation of identical detection logic, and finds that on a single commodity host, the plain Python engine outperforms Spark by roughly an order of magnitude on both throughput and latency. This paper's discussion (Section 7) situates that finding relative to the framework literature: Spark's design point is horizontal scale-out across many machines at data volumes this single-host study cannot produce, not lower latency at moderate throughput on one machine."),
  new Paragraph({ children: [new PageBreak()] }),
];

const systemDesign = [
  h1("3. System Design"),
  p("LogSentinel is organized as four cooperating subsystems: a replay/ingestion layer, a parsing and feature layer shared identically between offline training and online serving, a model layer behind one common interface, and a streaming engine layer with two interchangeable implementations (Python and Spark). A FastAPI backend and a React/Carbon web UI sit on top for operator triage, model management, and experiment control; these are supporting infrastructure for producing and inspecting the evidence in Section 6, not the paper's contribution in themselves."),
  h2("3.1 Architecture overview"),
  p("Log lines are replayed at a controlled rate into a Kafka topic (logs-raw, 6 partitions), stamped with the wall-clock send time. One or more engine workers consume the topic in a consumer group, maintain per-session state (a running count of parsed message templates), and re-score a session every time new lines for it arrive. When a session's score crosses its threshold, an alert carrying the score, threshold, and full latency provenance is published to alerts-critical, from which a dedicated sink service persists it into a SQLite store for the operator UI and for offline analysis."),
  h2("3.2 Parsing and feature extraction"),
  p([t("Every raw log line is first normalized by stripping the volatile header (timestamp, process id, severity level) common to a dataset's format, then passed through one of three parser arms evaluated in this project: "), b("raw"), t(" (a hash of the unmasked message into a fixed number of buckets), "), b("regex"), t(" (numeric tokens, IPs, and block identifiers masked to "), i("<*>"), t(" placeholders, then interned into the most frequent masked strings seen in training), and "), b("Drain"), t(" [1] (an online, tree-structured template miner fit on the training vocabulary only). All three arms are built once per dataset from a single cached pass over the training vocabulary, so comparing them costs a sparse matrix multiplication, not a second pass over the raw data. Session feature vectors are TF–IDF weighted counts over the resulting template vocabulary, with the inverse-document-frequency table fitted on the training split only, preventing any leakage from validation or test data into the feature representation.")]),
  h2("3.3 Detection models"),
  p("Three unsupervised detectors sit behind one common interface (fit, score, save, load), all trained exclusively on sessions with no known anomalies: Isolation Forest, a PCA-based reconstruction-error detector (the squared residual outside the retained principal subspace), and a small feed-forward autoencoder (scikit-learn MLPRegressor, capped at 25 epochs) scored by reconstruction mean-squared error. The score convention is fixed project-wide as higher = more anomalous."),
  h2("3.4 Thresholding"),
  p("Three threshold strategies are implemented and compared in Section 6.3: a 99th-percentile rule computed on training (normal-only) scores; a mean-plus-three-standard-deviations rule (the classical statistical-process-control heuristic referenced in the original synopsis); and a label-tuned threshold that maximizes F1 on a held-out validation split. The label-tuned threshold is reported as the primary operating point because it is closest to what an operator with even limited labeled feedback (e.g., from alert triage) could realistically achieve; the unsupervised thresholds are reported alongside it as deployable-without-labels alternatives, and an oracle threshold (best achievable F1 on the test set itself) is reported as an upper bound, never as an operating point."),
  h2("3.5 Sessionization and the early-detection problem"),
  p("HDFS_v1 blocks are long-lived: the median block spans roughly two hours between its first and last log line, so no session-idle timeout at a duration short enough to be operationally useful can be used to decide a session is “complete.” The streaming engine instead re-scores a session incrementally as lines arrive, but a naive incremental classifier trained on complete sessions misjudges short, in-progress sessions as anomalous purely because most of their expected content has not arrived yet. Section 6.4 quantifies this failure (40.2% of anomalous test sessions have only 2–4 lines and then go silent, and a naive incremental gate therefore misses all of them) and its fix: a second, event-time-triggered check that scores a session's partial state against a detector trained specifically on partial (age-bounded) snapshots of normal sessions, once the session reaches a fixed real age."),
  h2("3.6 Elasticity"),
  p("The Python engine supports horizontal scale-out by adding consumer-group workers, which Kafka rebalances across topic partitions automatically. A reactive autoscaler (implemented for the E7 experiment) monitors total consumer lag and adds a worker once lag exceeds a threshold for a sustained hold period, subject to a cooldown; Section 6.7 measures its effect on recovery time and peak backlog under an injected 10× traffic spike."),
  h2("3.7 Concept drift handling"),
  p("Section 6.8 evaluates two responses to a simulated change in log wording (as would follow a software update that alters log message text): scheduled retraining on a rolling window of recent, unlabeled sessions, and triggered retraining driven by an unsupervised drift signal — the share of incoming log lines whose template was never seen during the model's training — which requires no labels and, empirically, never fires on unchanged data."),
  h2("3.8 Two Kafka-consuming engine implementations"),
  p("To test the original synopsis's assumption that a distributed stream-processing framework is required, the identical detection logic (same parser, same trained model artifacts, same scoring mathematics, verified numerically identical to eight decimal places against the reference implementation) was ported to Apache Spark Structured Streaming, using mapInPandas for vectorized per-line featurization and applyInPandasWithState for per-session stateful scoring with an event-time timeout for the age-based check. Section 6.6 reports a controlled, apples-to-apples comparison between this Spark arm and the native Python consumer-group engine."),
  new Paragraph({ children: [new PageBreak()] }),
];

const expSetup = [
  h1("4. Experimental Setup"),
  h2("4.1 Datasets"),
  p("Three real, publicly available log corpora from the LogHub collection [3] are used. HDFS_v1 (11.2M lines, 575,061 blocks with ground-truth block-level labels) is the primary streaming and detection dataset; a session is one block (all lines sharing a block identifier), because the ground truth is per block, not per line. BGL (4.7M lines) and a 20-million-line prefix of Thunderbird are windowed into fixed 1-hour sessions and used for offline detection-quality and ablation experiments only; a window is labeled anomalous if any line inside it carries an alert-category label."),
  dataTable(
    ["Dataset", "Sessions", "Train (normal only)", "Val (anomalies)", "Test (anomalies)", "Test prevalence"],
    [
      ["HDFS_v1 (chronological)", "563,903", "333,878", "57,506 (1,957)", "172,519 (3,723)", "2.2%"],
      ["HDFS_v1 (random)", "564,988", "334,963", "57,506 (1,671)", "172,519 (5,094)", "3.0%"],
      ["BGL (chronological, 1h)", "3,175", "1,727", "362 (46)", "1,086 (175)", "16.1%"],
      ["Thunderbird (chronological, 1h, 20M-line prefix)", "776", "359", "104 (19)", "313 (195)", "62.3%"],
    ],
    [0.30, 0.13, 0.16, 0.15, 0.15, 0.11]
  ),
  caption("Table 1. Dataset sizes and splits. HDFS_v1 anomalies are front-loaded in time (66% fall in the first 60% of the log), so a second, seeded random split is also reported for HDFS_v1 as a robustness check (Section 7, threats to validity)."),
  h2("4.2 Splits and leakage control"),
  p("Splits are chronological over sessions (60% train / 10% validation / 30% test) unless noted; the training split retains only sessions with no known anomaly, matching the unsupervised setting. All feature-space artifacts (IDF weights, Drain template vocabulary, PCA principal subspace, detector parameters) are fitted exclusively on the training split; validation is used only for threshold tuning, and the test split is touched only for final metric computation."),
  h2("4.3 Hardware and environment"),
  p("All experiments in this paper ran on a single commodity host: an Intel Core i5-7400 (4 physical cores, no hyper-threading, 3.0 GHz base / 3.5 GHz peak, powersave governor), 15.5 GB RAM, running Arch Linux with Python 3.12 and Apache Kafka 3.9.1 (KRaft mode, single broker, running outside a container due to the lack of Docker daemon access on the development host). No dedicated cluster or cloud instance was available for this study; every throughput, latency, and elasticity result in Section 6 should be read as a single-host figure and not extrapolated to a multi-node deployment without further measurement (see Section 7)."),
  h2("4.4 Metrics and protocol"),
  bullet([b("Detection quality: "), t("Precision, Recall, F1 at the tuned threshold; ROC-AUC and PR-AUC as threshold-independent ranking measures, since class prevalence varies sharply by dataset (2.2% to 62.3%).")]),
  bullet([b("Throughput: "), t("consumer-observed events/second at a given offered load; a rate is called “sustained” only if the consumer keeps up (≥ 97% of offered rate), the backlog drains within the tolerance window after the last event is sent, and event-to-alert p99 latency stays under 500 ms.")]),
  bullet([b("Latency: "), t("event-to-alert wall-clock time, decomposed into producer-to-broker, broker-to-consumer, engine update, scoring, and alert-emit stages using timestamps recorded at each stage on one host clock.")]),
  bullet([b("Repeats: "), t("5 repeats per configuration for the main performance suite (E4, E5, E7), interleaved across configurations (all configurations run once before any runs a second time) to spread host-level drift such as thermal state or background load evenly rather than biasing whichever configuration happened to run last; 3 repeats for autoencoder-seed sensitivity; medians with min–max ranges are reported throughout.")]),
  bullet([b("Integrity checks: "), t("a run is excluded from steady-state statistics if the engine's consumed-event count does not match the producer's sent-event count (indicating a mid-run consumer-group rebalance or similar disruption) or if it runs on a broker less than 45 seconds old (a measured, reproducible cold-start effect; Section 6.5.1). Excluded runs are retained in the repository and reported, never silently discarded.")]),
  new Paragraph({ children: [new PageBreak()] }),
];

const results = [
  h1("5. Results"),
  p("Eight research questions (E1–E8) were designed to test the specific claims of the original project synopsis: detection quality on real data (E1), the value of template parsing (E2) and threshold strategy (E3), the throughput ceiling (E4) and latency composition (E5) of the streaming engine, whether a distributed stream-processing framework outperforms a plain consumer engine at this scale (E6), elastic recovery under a traffic spike (E7), and robustness to concept drift (E8). A ninth set of ablations, run after an initial pass at E1 raised a question about feature weighting, is reported in Section 5.9."),

  h2("5.1 E1 — Detection quality on real data"),
  p("Table 2 reports the primary operating point (Drain parser, label-tuned threshold) for each dataset's best-performing detector on the chronological split."),
  dataTable(
    ["Dataset", "Best detector", "ROC-AUC", "PR-AUC", "Precision", "Recall", "F1"],
    [
      ["HDFS_v1", "Autoencoder", "1.000", "0.999", "0.997", "0.996", "0.997"],
      ["HDFS_v1 (PCA — used in the streaming bundle)", "PCA", "0.998", "0.901", "0.883", "1.000", "0.938"],
      ["BGL (sublinear TF–IDF features)", "PCA", "0.592", "0.171", "0.234", "0.966", "0.377"],
      ["Thunderbird (62.3% test prevalence — see Section 7)", "PCA", "0.845", "0.931", "0.623", "1.000", "0.768"],
    ],
    [0.27, 0.19, 0.12, 0.12, 0.11, 0.10, 0.09]
  ),
  caption("Table 2. E1 detection quality, chronological split, Drain parser, label-tuned threshold. Full per-model, per-split results (Isolation Forest, PCA, autoencoder × chronological/random) are in the project repository (docs/results-offline.md)."),
  p([t("The streaming bundle deployed for E4–E8 uses PCA rather than the autoencoder for cost reasons (Section 5.5), at a quality trade-off: F1 0.938 versus 0.997 on HDFS_v1. BGL's F1 of 0.377 initially read as a weak result for the approach; the ablation study in Section 5.9 traces this to a specific, correctable feature-weighting choice rather than a limitation of the method itself. Thunderbird's headline numbers must be read against its "), b("62.3% test prevalence"), t(" (Section 7): a detector that flags every session already achieves F1 = 0.768 by construction, so ROC-AUC and PR-AUC are the meaningful figures there, not F1.")]),

  h2("5.2 E2 — Does template parsing help?"),
  p([t("Comparing the same PCA detector across the three parser arms on HDFS_v1: Drain reaches PR-AUC 0.901, versus 0.528 for the regex-masking arm and 0.149 for unparsed raw hashing — parsing the log into a bounded, semantically meaningful vocabulary is the single largest lever tested in this project for detection quality on HDFS_v1. The picture is dataset-dependent, however: on BGL, the "), i("regex"), t(" arm (PR-AUC 0.483) outperforms Drain (0.171) for the same PCA detector, which the ablation study (Section 5.9) attributes to feature weighting interacting with parser choice on high-cardinality windowed data. Full results across all three datasets, three models, and three parsers are in the repository (docs/results-offline.md, Section “E2 parser ablation”).")]),

  h2("5.3 E3 — Threshold strategy"),
  p([t("On HDFS_v1, the label-tuned threshold (F1 = 0.736 for Isolation Forest with Drain features) substantially outperforms both unsupervised alternatives — the 99th-percentile rule (F1 = 0.439) and the classical mean-plus-3σ rule referenced in the original synopsis (F1 = 0.458) — and is close to the oracle upper bound (F1 = 0.736, i.e. the tuned threshold is already near test-optimal given the validation set). This validates using a small amount of labeled feedback (e.g., from operator alert triage, which the LogSentinel UI collects explicitly) for threshold calibration rather than relying on an unsupervised statistical rule alone.")]),

  h2("5.4 E4 — Throughput ceiling"),
  p([t("A single Python engine worker "), b("sustains 50,000 events/second"), t(" with zero backlog growth and event-to-alert p99 latency of 111 ms; the next tested rate, 55,000 events/second, fails (p99 rises to 969 ms as a backlog forms). Two workers sustain "), b("70,000 events/second"), t(". Burst capacity (backlog draining as fast as possible, no latency constraint) reaches 54,700 events/second for one worker, 88,000–96,000 for two, and 114,000 for four workers sharing all four host cores. CPU profiling attributes the ceiling to the engine's own CPU cost, at roughly 1.2 cores per 50,000 events/second, not to Kafka: broker CPU stays under 3 seconds and producer CPU under 2 seconds over each 10-second run. Batch-size, compression, and linger tuning had no measurable effect except that a smaller micro-batch (500 messages) cost approximately 9% of capacity.")]),
  ...figure("docs/perf/e4a_load_sweep.png", 560, 1430, 546, "Figure 1. E4a: consumer throughput and event-to-alert p99 latency versus offered load, one and two workers. The dashed diagonal marks offered = consumed; departure from it marks the point where a backlog begins to form."),
  ...figure("docs/perf/e4c_scaling.png", 380, 780, 520, "Figure 2. E4c: burst capacity versus worker count, pinned to two cores versus all four cores shared with the broker and producer. Scaling is bounded by available cores on this host, not by the streaming design."),

  h2("5.5 E5 — Latency decomposition"),
  p([t("At 25%, 50%, and 75% of one worker's saturation throughput (12,500 / 25,000 / 37,500 events/second), typical per-run event-to-alert p99 latency is 85–120 ms, well under the 500 ms target. Decomposing the latency: scoring itself costs only about 1 ms per session; the dominant costs are the engine's per-micro-batch state update (17–37 ms, growing with batch fill) and the consumer's Kafka fetch path (p99 ≈ 72 ms). "), b("Pooled across every alert in 44 warm-broker runs"), t(", however, p99 latency was 102 / 116 / "), b("612"), t(" ms at the three load levels — the 612 ms figure is driven entirely by one run (of 15 at that load level) with an 8-second unexplained consumer-side slowdown, and a second run (of 15, at the lowest load level) had a separate, also-unexplained 0.7-second stall. Both anomalous runs are disclosed in full, including a dedicated diagnostic instrumentation pass (GC/safepoint logging, per-core CPU and frequency sampling, 30 additional repeats) that ruled out CPU frequency scaling, JVM garbage-collection pauses, and competing-process CPU contention as causes, without identifying the true cause (Section 7). A separate, "), b("fully explained"), t(" latency effect was found and fixed during this investigation: the first paced run immediately after a Kafka broker restart is reliably slow (p99 1.1–1.2 s, reproduced in 3 of 3 restarts, isolated to the producer-to-broker stage), which the benchmark harness now detects automatically (broker uptime under 45 seconds) and excludes from steady-state statistics.")]),
  ...figure("docs/perf/e5_latency_stages.png", 480, 1040, 572, "Figure 3. E5: event-to-alert latency decomposed by pipeline stage at 25/50/75% of single-worker saturation."),

  h2("5.6 E6 — Engine comparison: Python versus Apache Spark Structured Streaming"),
  p([t("The original synopsis's literature review frames a distributed stream-processing framework (Spark or Flink) as necessary machinery for high-throughput log analytics. To test this directly, the identical detection logic — same trained model artifacts, same scoring mathematics, verified numerically identical to the Python reference implementation — was ported to Apache Spark Structured Streaming (local mode, 2 cores, mapInPandas + applyInPandasWithState) and benchmarked head-to-head against the native Python consumer engine on the same host, same replayed events, same offered rate, over 69 runs (5 repeats per configuration, zero incomplete runs).")]),
  dataTable(
    ["Metric", "Python engine", "Spark (local[2])", "Ratio"],
    [
      ["Sustained throughput", "50,000 ev/s", "≈ 3,000 ev/s", "Python ≈ 17× higher"],
      ["Latency p50 @ 3,000 ev/s", "32 ms", "5,669 ms", "Spark ≈ 177× slower"],
      ["Latency p99 @ 3,000 ev/s", "56 ms", "6,686 ms", "Spark ≈ 119× slower"],
      ["Engine CPU @ 3,000 ev/s", "0.14 cores", "1.89 cores", "Spark ≈ 13.5× more"],
      ["Peak memory @ 3,000 ev/s", "207 MB", "1,579 MB", "Spark ≈ 7.6× more"],
      ["Startup time (process start to first batch)", "4.4 s", "14.2 s", "Spark ≈ 3.2× slower"],
    ],
    [0.34, 0.22, 0.22, 0.22]
  ),
  caption("Table 3. E6 head-to-head comparison, median over 5 repeats. At every rate tested in common (1,000 / 3,000 / 5,000 events/second), incremental alert counts matched exactly between engines (4/4, 8/8, 26/26), confirming the entire performance gap is infrastructure overhead, not a difference in detections."),
  p("Three Spark tuning variants (1 and 4 shuffle partitions; a smaller max-offsets-per-trigger of 10,000) were also measured at Spark's near-saturation point of 3,000 events/second; none materially changed backlog or latency, indicating the bottleneck is Spark's own fixed micro-batch interval (observed at 3–6 seconds per batch, including empty batches) and JVM/Arrow round-trip overhead, not a parameter that can be tuned away in local mode on this hardware."),
  ...figure("docs/perf/e6/e6_spark_vs_python.png", 560, 1950, 546, "Figure 4. E6: backlog, latency, and CPU versus offered load, Python engine versus Spark local[2]. Dotted lines in the left panel mark each engine's own “keeping up” tolerance."),

  h2("5.7 E7 — Elasticity under a traffic spike"),
  p([t("A 10× traffic spike (base rate 15,000 events/second rising to 150,000 for 8 seconds, then returning to base) was injected against three configurations: a fixed single worker, a fixed pair of workers, and a single worker with a reactive autoscaler that adds a second worker once total consumer lag exceeds 20,000 messages for 1 second. The pre-provisioned pair of workers recovers fastest (peak lag 365,731 messages, 5.8 s to recover, p99 during the spike 4,649 ms); the elastic single-worker-then-two configuration is intermediate (peak lag 598,768, 7.7 s recovery, p99 6,104 ms); the fixed single worker is worst (peak lag 764,076, 20.1 s recovery, p99 14,081 ms). Instrumented timing shows the autoscaler's second worker only becomes available roughly 4 seconds into the 8-second spike (1.5–2.5 s decision delay plus a measured 2.1–2.6 s worker-startup delay), which explains why reactive scale-out captures only part of the pre-provisioned pair's benefit. "), b("No configuration tested keeps p99 latency under the 500 ms target during the spike itself"), t("; elasticity here reduces recovery time and peak backlog, but does not eliminate a queueing period under sudden severe overload — a distinction the original synopsis's use of the word “elastic” does not make explicit and that this paper's discussion addresses directly (Section 7).")]),
  ...figure("docs/perf/e7_spike_lag.png", 480, 1170, 572, "Figure 5. E7: consumer lag over time under a 10× spike, three configurations. The dotted vertical line marks the elastic configuration's scale-out trigger."),

  h2("5.8 E8 — Concept drift"),
  p([t("A software-update-style drift was simulated by rewording the most common HDFS log message templates partway through the (chronologically chunked) test stream: "), i("moderate"), t(" drift reworded the top 2 templates (36% of lines), "), i("severe"), t(" reworded the top 4 (72% of lines). A static model's F1 collapses from a 0.866 no-drift control to "), b("0.025"), t(" in the very first post-drift measurement chunk under both conditions, because its fixed threshold now flags essentially every session (a false-positive rate of 100%); this held across all 12 points of a drift-timing/window-size sensitivity grid (penalty always –40.84 to –0.92 F1), i.e. the finding is not an artifact of one particular drift timing. The share of log lines never seen during training — a signal requiring no labels — rises from under 0.1% before drift to 46% (moderate) or 92% (severe) in the very first post-drift chunk, and never false-triggers on unchanged data across any of the three no-drift control runs. Triggering a retrain on this signal (rather than on a fixed schedule) recovers mean F1 to 0.745 over the six post-drift measurement chunks, within one chunk of the drift becoming visible, at a refit cost of only 0.4–0.5 seconds. A naive alternative — retraining on a schedule regardless of drift, using an unlabeled recent window — is itself unstable when that window happens to contain a burst of real anomalies (observed F1 as low as 0.05–0.17 in three no-drift control chunks with elevated anomaly rates), because the retrain has no way to distinguish “anomalous” log lines it should exclude from “normal” lines it should learn from.")]),
  ...figure("docs/drift/e8_drift.png", 560, 1820, 910, "Figure 6. E8: F1 per measurement chunk (top) and share of never-before-seen log lines (bottom), no-drift / moderate / severe conditions. The dashed vertical line marks the drift point; drift is simulated only from that point on."),

  h2("5.9 Ablations: feature weighting, parser parameters, model capacity"),
  p([t("An ablation pass (Drain similarity threshold and tree depth; TF–IDF / sublinear TF–IDF / raw counts / binary-presence feature weighting; PCA variance retained; autoencoder bottleneck width), run after E1's BGL result looked weaker than expected, found that "), b("Drain's own hyperparameters do not matter"), t(" on either HDFS_v1 or BGL (all 12 similarity-threshold × depth combinations tie exactly), but "), b("feature weighting matters a great deal on BGL"), t(": switching from sublinear TF–IDF to simple binary presence raises PR-AUC from 0.172 to "), b("0.764"), t(" (ROC-AUC 0.906, F1 0.555), and this choice is also what validation data alone would have selected (0.912 vs. 0.635 validation PR-AUC), meaning the weaker BGL numbers reported in Section 5.1 reflect a correctable feature-representation choice for windowed, high-line-count sessions, not a limit of the underlying method. On HDFS_v1, raising the PCA-retained-variance threshold from the 0.95 default (borrowed from the general literature, not tuned on this data) to 0.99 raises F1 from 0.938 to "), b("0.994"), t("; this improvement was not, however, propagated back into the streaming bundle used for E4–E8 — doing so would require retraining that bundle and re-running the age-check and performance studies that depend on it, which this paper flags as immediate future work rather than doing under schedule pressure and reporting inconsistent numbers across sections.")]),
  new Paragraph({ children: [new PageBreak()] }),
];

const discussion = [
  h1("6. Discussion"),
  h2("6.1 Which of the synopsis's original claims does the evidence support?"),
  bullet([b(">50,000 events/second sustained: "), t("supported, narrowly, by the Python engine on this single host (50,000 sustained, 55,000 not); two workers extend this to 70,000. This is model-scoring-inclusive throughput on real HDFS log lines, on one machine — the claim should be read as validated for this setup, not generalized to a cluster without further measurement.")]),
  bullet([b("Sub-500 ms processing: "), t("supported as a typical figure below saturation (p99 ≈ 85–120 ms in most runs) but not as an unconditional bound: 2 of 44 warm-broker E5 runs exceeded it substantially, for reasons this paper could not fully explain despite a dedicated diagnostic pass (Section 7). The synopsis's implicit claim of a guarantee is not supported; a typical-case claim is.")]),
  bullet([b("Spark/Flink as necessary machinery: "), t("not supported at this scale. On identical detection logic, identical data, and the same host, the plain Python consumer-group engine outperforms a Spark Structured Streaming implementation by roughly 17× on throughput and two orders of magnitude on latency, at a fraction of the CPU and memory cost, for byte-identical detections. This is this paper's most consequential finding relative to the original synopsis, and it is discussed at length in Section 6.2 below rather than treated as a footnote.")]),
  bullet([b("Elastic scaling under spikes: "), t("partially supported. Horizontal scale-out measurably improves recovery time (20.1 s → 7.7 s reactive, or 5.8 s pre-provisioned) and reduces peak backlog, but no tested configuration keeps latency under the 500 ms target during a 10× spike itself; “elastic” in this system means faster recovery from overload, not overload avoidance.")]),
  bullet([b("Concept-drift adaptation via retraining: "), t("supported, with an important qualification the synopsis did not anticipate: retraining must be triggered by a drift signal, not run on a fixed schedule, because scheduled retraining on a contaminated unlabeled window is itself unstable when real anomalies are frequent. The unlabeled unseen-line-share signal proposed and tested here is cheap, clean (zero false triggers across all control runs), and sufficient to recover detection quality within one measurement window.")]),
  h2("6.2 Why does Spark underperform here, and what does that mean?"),
  p("Spark Structured Streaming's micro-batch execution model imposes a latency floor set by its batch interval (observed at 3–6 seconds per batch on this workload, including empty batches) plus fixed per-batch JVM and Arrow serialization overhead — costs that do not amortize at moderate event rates on a single host with only two cores allotted to the Spark job. This is not evidence that Spark is poorly engineered; it is evidence that Spark's design point is horizontal scale-out across many machines processing far higher aggregate volumes than a single 4-core host can offer or than this project's 50,000-events-per-second target requires. A fair reading for practitioners: a stream-processing framework becomes the right choice once event volume or state size genuinely exceeds what a well-implemented single-process consumer engine can hold in memory and score with a lightweight model on one machine — not automatically, by default, for real-time log analytics at the scale this project's target describes."),
  h2("6.3 The early-detection problem is a session-modeling problem, not a modeling-algorithm problem"),
  p("The single largest correctness bug discovered during this project was not in any detector, but in the assumption that a session's identity is well-defined the instant its first line arrives. Because HDFS blocks are long-lived, 40.2% of anomalous test sessions never accumulate the ten-plus lines a naive incremental classifier implicitly expects before making a confident judgment, and are therefore never flagged by an incremental-only rule (live F1 0.691). The fix required recognizing this as a distinct problem — detecting an evidenceless absence, not classifying present evidence — and building a second detector trained specifically for that regime (an event-time-triggered check on partial, age-bounded session snapshots), which recovered live F1 to 0.923. This generalizes beyond log anomaly detection: any streaming system that must render a verdict on an entity before that entity's lifecycle is complete faces the same problem, and the paper's proposed general pattern (train a second detector explicitly for the partial-evidence regime, triggered on real elapsed time rather than message count) is offered as a contribution independent of the specific log-analytics application."),
  h2("6.4 Honesty about what was not fully explained"),
  p("Two latency stalls (of 44 warm-broker E5 runs) were investigated with a dedicated instrumentation pass — JVM GC and safepoint logging, per-core CPU and frequency sampling at 0.5-second resolution, 30 additional repeat runs, and a targeted cold-broker-restart experiment that did successfully explain and fix a separate, related effect — without identifying their cause. This paper reports them as unresolved rather than omitting them or attributing them to an unverified guess, on the view that an unexplained 4.5% tail-latency rate is itself a finding a deploying engineer needs to know about, and that a research paper's credibility rests on distinguishing what was proven from what remains open."),
  new Paragraph({ children: [new PageBreak()] }),
];

const threats = [
  h1("7. Threats to Validity"),
  h2("7.1 Internal validity"),
  bullet([b("HDFS_v1 anomalies are front-loaded in time: "), t("66% of anomalous blocks fall in the first 60% of the log, so the primary chronological split's unsupervised training regime (which excludes anomalies from training by construction) discards most of them before the test split is reached, leaving a 2.2% test-set anomaly rate. A second, seeded random split is reported alongside it throughout (3.0% test prevalence) as a robustness check; results are qualitatively consistent between the two, but the chronological split remains the headline because it alone avoids mixing future information into the training window.")]),
  bullet([b("Session-level rather than line-level evaluation: "), t("HDFS_v1 ground truth is per block; BGL and Thunderbird windows are labeled anomalous if any contained line is. These numbers are consequently not directly comparable to papers reporting line-level metrics on the same or similar corpora.")]),
  bullet([b("Thunderbird is a 20-million-line prefix (roughly three weeks) of a much longer log, "), t("chosen to fit available disk space; its results describe that period only. Its windowed test prevalence (62.3%) is high enough that F1 alone is a poor summary statistic there (Section 5.1); ROC-AUC and PR-AUC are more informative for that dataset specifically.")]),
  bullet([b("BGL and Thunderbird labels reflect operator-assigned alert categories, "), t("not an independent ground truth; some “normal” lines closely resemble “alert” lines in content, which any window-level label inherits.")]),
  bullet([b("Threshold tuning on the validation split (E3) uses labels; "), t("the resulting F1 is reported as an achievable operating point given some labeled feedback, never conflated with an unsupervised result.")]),
  h2("7.2 External validity"),
  bullet([b("Single-host measurement. "), t("Every throughput, latency, elasticity, and engine-comparison result (E4–E7, E6) was measured on one 4-core, 15.5 GB commodity machine, shared at the OS level with a desktop environment during some runs (repeats are interleaved specifically to spread, not eliminate, this noise). None of these results should be read as predicting behavior on a multi-node cluster, a cloud instance with a different CPU microarchitecture, or under sustained production background load; a cluster deployment was outside this project's available resources.")]),
  bullet([b("Simulated, not organic, concept drift and load spikes. "), t("E8's drift is an abrupt, synthetic rewording of specific message templates at one dataset, one severity level per condition, one realization each — gradual drift, novel (rather than reworded) message types, and drift in message frequency rather than wording were not tested. E7's spike is an injected, scripted 10× rate change, not an organically occurring incident.")]),
  bullet([b("The Spark comparison (E6) uses Spark's local execution mode "), t("with 2 cores, not a real multi-executor cluster; the comparison is valid for the question it was designed to answer (does a framework help at this scale, on one machine) but says nothing about Spark's behavior at cluster scale, which is precisely the regime the discussion (Section 6.2) argues is Spark's actual design point.")]),
  h2("7.3 Construct validity and open questions"),
  bullet([b("Two E5 latency stalls (2 of 44 warm-broker runs) remain unexplained "), t("despite a dedicated diagnostic instrumentation pass; see Section 6.4.")]),
  bullet([b("The streaming engine is at-least-once with auto-commit offsets; "), t("a consumer-group rebalance during a run can cause a partition's in-flight lines to be re-read from the last committed offset, double-counting session line totals (though not alerts, which the alert sink deduplicates by session key). This was directly observed once during E4c benchmarking, diagnosed, fixed at the harness level (a stricter, tested readiness check that waits for a stable partition assignment before producing), and the affected run was excluded and re-executed — but the underlying at-least-once semantics of the production engine itself were not changed, and remain a live operational consideration for any deployment.")]),
  bullet([b("The ablation-identified improvements (binary features for BGL, 99%-variance PCA for HDFS_v1) "), t("were not propagated into the streaming bundle used for E4–E8; those experiments' numbers reflect the pre-ablation configuration and would need to be re-run to reflect the improved model, which this paper does not do in order to avoid presenting inconsistent numbers across sections under project time constraints.")]),
  new Paragraph({ children: [new PageBreak()] }),
];

const conclusion = [
  h1("8. Conclusion and Future Work"),
  p("This paper set out to test, rather than illustrate, the claims of an M.Sc. research synopsis on real-time distributed log analytics and unsupervised anomaly detection. Building a complete, tested, reproducible system and subjecting it to eight pre-registered research questions surfaced a substantially more nuanced picture than the original synopsis assumed: the throughput target is achievable, but by a plain Python consumer engine rather than the distributed stream-processing framework the literature review presumed necessary — a finding with direct implications for how practitioners should scope similar systems. Detection quality is strong on session-structured data (HDFS_v1) and improvable but currently weaker on window-structured data (BGL, Thunderbird) for a reason now understood and fixable (feature weighting). A previously undiagnosed early-detection failure mode, specific to long-lived streaming sessions, was found, quantified, and fixed. Concept drift causes a fast and total failure of a static model, but is recoverable within one detection window using a cheap, unlabeled drift signal, provided retraining is triggered rather than scheduled. Two latency anomalies and the gap between an at-least-once engine's guarantees and a production deployment's needs are reported as open items rather than concealed."),
  h2("Future work"),
  bullet("Re-run the streaming pipeline (E4–E8) with the ablation-identified improved configuration (binary features for windowed datasets, 99%-variance PCA for HDFS_v1) to determine whether the throughput and latency findings hold under the higher-quality detector."),
  bullet("Test genuinely organic concept drift (a real software rollout with real log-format changes) rather than simulated template rewording, and gradual drift in addition to abrupt drift."),
  bullet("Repeat the throughput, latency, elasticity, and Spark-comparison experiments (E4-E7, E6) on a multi-node cluster or a dedicated, unshared cloud instance to establish whether the single-host findings, particularly the Python-over-Spark result, hold, and at what event-rate crossover point (if any) a distributed framework becomes advantageous."),
  bullet("Pursue the two unexplained E5 latency stalls with kernel-level tracing (perf, eBPF) rather than the process-level instrumentation used here, and run the diagnostic suite on a dedicated, otherwise-idle machine to remove desktop-environment interference as a variable."),
  bullet("Extend the early-detection mechanism's evaluation to BGL and Thunderbird, whose window-based sessionization raises a related but distinct partial-evidence question."),
  bullet("Move the streaming engine from at-least-once auto-commit to an exactly-once or idempotent-consumption design, and re-verify the double-counting behavior observed once during benchmarking under production-realistic rebalance conditions."),
  new Paragraph({ children: [new PageBreak()] }),
];


const references = [
  h1("References"),
  ref('[1] P. He, J. Zhu, Z. Zheng, and M. R. Lyu, "Drain: An Online Log Parsing Approach with Fixed Depth Tree," in Proc. IEEE International Conference on Web Services (ICWS), 2017.'),
  ref('[2] J. Zhu, S. He, P. He, J. Liu, and M. R. Lyu, "Loghub: A Large Collection of System Log Datasets for AI-Driven Log Analytics," arXiv:2008.06448, 2020.'),
  ref('[3] S. He, J. Zhu, P. He, and M. R. Lyu, "Tools and Benchmarks for Automated Log Parsing," in Proc. IEEE/ACM International Conference on Software Engineering: Software Engineering in Practice (ICSE-SEIP), 2019, doi: 10.1109/ICSE-SEIP.2019.00021.'),
  ref('[4] M. Du, F. Li, G. Zheng, and V. Srikumar, "DeepLog: Anomaly Detection and Diagnosis from System Logs through Deep Learning," in Proc. ACM SIGSAC Conference on Computer and Communications Security (CCS), 2017, doi: 10.1145/3133956.3134015.'),
  ref('[5] H. Guo, S. Yuan, and X. Wu, "LogBERT: Log Anomaly Detection via BERT," arXiv:2103.04475, 2021.'),
  ref('[6] W. Meng et al., "LogClass: Anomalous Log Identification and Classification with Partial Labels," IEEE Transactions on Network and Service Management, 2021, doi: 10.1109/TNSM.2021.3055425.'),
  ref('[7] V.-H. Le and H. Zhang, "Log-Based Anomaly Detection Without Log Parsing," in Proc. IEEE/ACM International Conference on Automated Software Engineering (ASE), 2021, doi: 10.1109/ASE51524.2021.9678773.'),
  ref('[8] M. Landauer, F. Skopik, M. Wurzenberger, and A. Rauber, "Deep Learning for Anomaly Detection in Log Data: A Survey," Machine Learning with Applications, 2023, doi: 10.1016/j.mlwa.2023.100470.'),
  ref('[9] S. Nedelkoski, J. Bogatinovski, A. Acker, J. Cardoso, and O. Kao, "Self-Supervised Log Parsing," arXiv:2003.07905, 2020.'),
  ref('[10] F. T. Liu, K. M. Ting, and Z.-H. Zhou, "Isolation Forest," in Proc. IEEE International Conference on Data Mining (ICDM), 2008.'),
  new Paragraph({ text: "", spacing: { before: 300 } }),
  p([i("Note on citation verification: "), t("references [1]-[10] above were checked against Crossref and/or arXiv metadata during this project (full audit trail in docs/citations.md of the accompanying repository). Two entries from the original project synopsis - a Trambadiya (2025) and a Gaikwad (2025) reference on Kafka/streaming fraud- and quality-pipeline architectures - could not be matched to a verifiable source under their originally cited title and venue and have been dropped from this reference list rather than carried forward unverified; the candidate should perform a final DBLP check on entries [1], [5], [6], [7], and [8] before formal submission, as this project's automated verification tooling could not reach DBLP directly.")]),
];

const doc = new Document({
  numbering: {
    config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }],
  },
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 22 }, paragraph: { spacing: { line: 300 } } },
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", run: { size: 30, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 360, after: 200 } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", run: { size: 26, bold: true, color: "2E5395" }, paragraph: { spacing: { before: 260, after: 140 } } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", run: { size: 23, bold: true, italics: true, color: "44546A" }, paragraph: { spacing: { before: 200, after: 100 } } },
    ],
  },
  sections: [
    {
      properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      children: [
        ...titlePage,
        ...abstract,
        ...introduction,
        ...related,
        ...systemDesign,
        ...expSetup,
        ...results,
        ...discussion,
        ...threats,
        ...conclusion,
        ...references,
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(process.argv[2], buf);
  console.log("wrote", process.argv[2], buf.length, "bytes");
});
