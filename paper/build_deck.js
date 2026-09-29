const pptxgen = require("pptxgenjs");

const FIGDIR = "/home/adu/Projects/SEM III-IV Research and Project/logsentinel";

// ---------- palette: "signal / anomaly" theme, built for a log-monitoring & alerting topic -------
const C = {
  bgDark: "0B1220",      // near-black navy: title / conclusion slides
  bgLight: "FFFFFF",
  panelDark: "141E33",   // slightly lighter navy, for cards on dark bg
  text: "0B1220",
  textLight: "EAF0FB",
  muted: "5B6B87",
  mutedLight: "9FB0CC",
  signal: "2E86AB",      // steel blue: normal / baseline / "this system"
  anomaly: "E4572E",     // burnt orange: anomaly / alert / contrast finding (Spark result, drift failure)
  good: "3DDC97",        // signal green: sustained / recovered / success
  line: "23324D",
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
const W = 13.33, H = 7.5;

function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: C.bgDark };
  return s;
}
function lightSlide() {
  const s = pres.addSlide();
  s.background = { color: C.bgLight };
  return s;
}

function kicker(s, text, opts = {}) {
  s.addText(text.toUpperCase(), {
    x: opts.x ?? 0.6, y: opts.y ?? 0.45, w: opts.w ?? 8, h: 0.4,
    fontFace: "Calibri", fontSize: 13, bold: true, color: opts.color ?? C.signal, charSpacing: 2, isTextBox: true, margin: 0,
  });
}
function title(s, text, opts = {}) {
  s.addText(text, {
    x: opts.x ?? 0.6, y: opts.y ?? 0.82, w: opts.w ?? 11.8, h: opts.h ?? 0.9,
    fontFace: "Cambria", fontSize: opts.size ?? 32, bold: true, color: opts.color ?? (opts.dark === false ? C.text : C.textLight),
    isTextBox: true, margin: 0,
  });
}
function notes(s, text) { s.addNotes(text); }

function statTile(s, x, y, w, h, value, label, opts = {}) {
  s.addShape("roundRect", { x, y, w, h, rectRadius: 0.08, fill: { color: opts.fill ?? C.panelDark } });
  s.addText(value, { x: x + 0.15, y: y + 0.12, w: w - 0.3, h: h * 0.6, fontFace: "Calibri", fontSize: opts.valSize ?? 30, bold: true, color: opts.valColor ?? C.textLight, align: "left", isTextBox: true, margin: 0 });
  s.addText(label, { x: x + 0.15, y: y + h * 0.62, w: w - 0.3, h: h * 0.36, fontFace: "Calibri", fontSize: 12, color: opts.labelColor ?? C.mutedLight, align: "left", isTextBox: true, margin: 0 });
}

function pageNum(s, n) {
  s.addText(String(n), { x: W - 0.7, y: H - 0.45, w: 0.5, h: 0.3, fontFace: "Calibri", fontSize: 10, color: C.muted, align: "right", isTextBox: true, margin: 0 });
}

// ================= Slide 1: Title (dark) ======================================================
{
  const s = darkSlide();
  s.addText("LOGSENTINEL", { x: 0.8, y: 1.9, w: 8, h: 0.5, fontFace: "Calibri", fontSize: 15, bold: true, color: C.signal, charSpacing: 3, isTextBox: true, margin: 0 });
  s.addText("Architecting an Elastic, High-Throughput Pipeline for\nReal-Time Distributed Log Analytics and\nUnsupervised Anomaly Detection", {
    x: 0.8, y: 2.35, w: 11.5, h: 2.2, fontFace: "Cambria", fontSize: 34, bold: true, color: C.textLight, lineSpacing: 40, isTextBox: true, margin: 0,
  });
  s.addText("M.Sc. Computer Science — Thesis Defense", { x: 0.8, y: 4.75, w: 8, h: 0.4, fontFace: "Calibri", fontSize: 16, color: C.mutedLight, isTextBox: true, margin: 0 });
  s.addText("[Candidate Name]  ·  Advisor: [Advisor Name]  ·  [Defense Date]", { x: 0.8, y: 5.2, w: 10, h: 0.4, fontFace: "Calibri", fontSize: 14, color: C.mutedLight, isTextBox: true, margin: 0 });
  // three small stat teasers across the bottom
  const teaseY = 6.2, tw = 3.7, gap = 0.25;
  statTile(s, 0.8, teaseY, tw, 1.0, "50,000/s", "Sustained throughput, one worker", { valColor: C.good });
  statTile(s, 0.8 + tw + gap, teaseY, tw, 1.0, "17×", "Faster than Spark, same host", { valColor: C.anomaly });
  statTile(s, 0.8 + 2 * (tw + gap), teaseY, tw, 1.0, "0.923", "Live F1 after the early-detection fix", { valColor: C.signal });
  notes(s, "Welcome. This defense reports on LogSentinel, a real-time log anomaly detection system built specifically to TEST the claims of the original research synopsis, not just illustrate them. Every number you'll see today comes from an executed, repeated, logged experiment.");
}

// ================= Slide 2: Problem statement (light) ==========================================
{
  const s = lightSlide();
  kicker(s, "The Problem", { color: C.anomaly });
  title(s, "Batch log analysis is too slow for real-time incidents", { dark: false });
  const colW = 5.7, y0 = 2.0, colH = 4.6;
  s.addShape("roundRect", { x: 0.6, y: y0, w: colW, h: colH, rectRadius: 0.08, fill: { color: "FBEDE8" } });
  s.addText("Traditional log management", { x: 0.9, y: y0 + 0.25, w: colW - 0.6, h: 0.4, fontFace: "Calibri", fontSize: 17, bold: true, color: C.anomaly, isTextBox: true, margin: 0 });
  [
    "Periodic batch indexing (cron / ELK) with no streaming compute buffer",
    "High ingest latency and resource contention under traffic spikes",
    "Deterministic rules (string matches, static thresholds) miss novel failure modes",
    "Rules require constant manual maintenance as systems evolve",
  ].forEach((t, i) => s.addText(t, { x: 0.95, y: y0 + 0.85 + i * 0.85, w: colW - 0.7, h: 0.8, fontFace: "Calibri", fontSize: 14, color: C.text, bullet: { code: "2013" }, isTextBox: true, margin: 0 }));

  const x1 = 0.6 + colW + 0.35;
  s.addShape("roundRect", { x: x1, y: y0, w: colW, h: colH, rectRadius: 0.08, fill: { color: "E8F1F6" } });
  s.addText("LogSentinel's approach", { x: x1 + 0.3, y: y0 + 0.25, w: colW - 0.6, h: 0.4, fontFace: "Calibri", fontSize: 17, bold: true, color: C.signal, isTextBox: true, margin: 0 });
  [
    "In-flight vectorization + unsupervised scoring, not store-then-query",
    "Trained only on normal behavior — no attack signatures required",
    "Alert published within milliseconds of the underlying evidence arriving",
    "Every architectural claim tested as a hypothesis, not assumed",
  ].forEach((t, i) => s.addText(t, { x: x1 + 0.35, y: y0 + 0.85 + i * 0.85, w: colW - 0.7, h: 0.8, fontFace: "Calibri", fontSize: 14, color: C.text, bullet: { code: "2013" }, isTextBox: true, margin: 0 }));
  pageNum(s, 2);
  notes(s, "The core problem: as systems move to microservices, log volume explodes and static rules can't keep up. LogSentinel treats this as a streaming classification problem, trained unsupervised, and critically: we test the assumptions rather than assume them.");
}

// ================= Slide 3: Architecture (dark) =================================================
{
  const s = darkSlide();
  kicker(s, "System Design");
  title(s, "Four-stage streaming pipeline");
  const stages = [
    { t: "Ingest", d: "Kafka logs-raw\n6 partitions" },
    { t: "Parse", d: "Drain template\nmining" },
    { t: "Score", d: "PCA / IForest /\nAutoencoder" },
    { t: "Alert", d: "alerts-critical\n→ SQLite → UI" },
  ];
  const boxW = 2.6, gap = 0.55, startX = (W - (4 * boxW + 3 * gap)) / 2, y = 2.6, boxH = 1.6;
  stages.forEach((st, i) => {
    const x = startX + i * (boxW + gap);
    s.addShape("roundRect", { x, y, w: boxW, h: boxH, rectRadius: 0.1, fill: { color: C.panelDark }, line: { color: C.signal, width: 1.5 } });
    s.addText(st.t, { x, y: y + 0.18, w: boxW, h: 0.4, align: "center", fontFace: "Calibri", fontSize: 18, bold: true, color: C.textLight, isTextBox: true, margin: 0 });
    s.addText(st.d, { x, y: y + 0.65, w: boxW, h: 0.8, align: "center", fontFace: "Calibri", fontSize: 12.5, color: C.mutedLight, isTextBox: true, margin: 0 });
    if (i < 3) s.addText("→", { x: x + boxW, y: y + 0.45, w: gap, h: 0.7, align: "center", fontFace: "Calibri", fontSize: 26, bold: true, color: C.good, isTextBox: true, margin: 0 });
  });
  s.addText("Two interchangeable engine implementations were built and benchmarked head-to-head for the Score/Alert stages: a native Python consumer-group engine, and an Apache Spark Structured Streaming port of the identical detection logic — same trained model, verified numerically identical to 8 decimal places.", {
    x: 1.2, y: 4.85, w: W - 2.4, h: 1.0, align: "center", fontFace: "Calibri", fontSize: 15, italic: true, color: C.mutedLight, isTextBox: true, margin: 0,
  });
  statTile(s, 1.5, 6.05, 3.3, 1.0, "8", "Research questions (E1–E8) tested against the synopsis's claims");
  statTile(s, 5.05, 6.05, 3.3, 1.0, "215+", "Benchmark runs, repeated & interleaved");
  statTile(s, 8.6, 6.05, 3.3, 1.0, "3", "Real LogHub datasets (HDFS, BGL, Thunderbird)");
  pageNum(s, 3);
  notes(s, "Four stages: ingest via Kafka, parse via Drain (a template-mining algorithm), score with an unsupervised model, alert through a sink into a database the UI reads. The key methodological point: everything downstream of parsing was implemented TWICE — once in Python, once in Spark — with numerically verified identical scoring, specifically so we could test whether Spark is actually necessary.");
}

// ================= Slide 4: E4 Throughput (light, native chart) =================================
{
  const s = lightSlide();
  kicker(s, "E4 — Throughput Ceiling", { color: C.signal });
  title(s, "One worker sustains 50,000 events/second", { dark: false });
  const chartData = [
    { name: "Consumed (1 worker)", labels: ["10k", "20k", "30k", "40k", "45k", "50k", "55k", "60k", "70k"], values: [9.97, 20.0, 29.9, 39.9, 44.8, 49.5, 49.7, 49.2, 50.9] },
  ];
  s.addChart(pres.ChartType.line, chartData, {
    x: 0.6, y: 1.95, w: 6.6, h: 4.6,
    showTitle: true, title: "Consumer throughput vs offered load (k events/s)", titleFontSize: 13,
    showLegend: false, chartColors: [C.signal], lineSize: 3, lineDataSymbol: "circle", lineDataSymbolSize: 6,
    catAxisLabelColor: C.muted, valAxisLabelColor: C.muted, valAxisTitle: "Consumed (k ev/s)", showValAxisTitle: true,
    catGridLine: { style: "none" }, valGridLine: { color: "E5E9F0", size: 1 },
    dataLabelColor: C.text, showDataLabels: false,
  });
  s.addShape("line", { x: 5.85, y: 2.35, w: 0, h: 3.9, line: { color: C.anomaly, width: 1.5, dashType: "dash" } });
  s.addText("55k: backlog\nforms (fails)", { x: 5.55, y: 2.0, w: 1.6, h: 0.5, fontFace: "Calibri", fontSize: 10, color: C.anomaly, align: "center", isTextBox: true, margin: 0 });

  const rx = 7.55, rw = 5.2;
  statTile(s, rx, 1.95, rw, 1.1, "50,000 ev/s", "sustained, 1 worker — p99 latency 111 ms, zero backlog growth", { fill: "E8F1F6", valColor: C.signal, labelColor: C.muted });
  statTile(s, rx, 3.2, rw, 1.1, "70,000 ev/s", "sustained, 2 workers — the throughput target this project set out to test, met", { fill: "E8F1F6", valColor: C.signal, labelColor: C.muted });
  statTile(s, rx, 4.45, rw, 1.35, "≈ 1.2 cores", "per 50,000 ev/s — the engine's own CPU is the ceiling, not Kafka (broker CPU < 3 s per 10 s run)", { fill: "FBEDE8", valColor: C.anomaly, labelColor: C.muted });
  pageNum(s, 4);
  notes(s, "A single Python worker sustains 50,000 events per second with p99 latency of just 111 milliseconds. At 55,000 it fails — a backlog starts forming and latency explodes to nearly a second. Two workers push this to 70,000. Profiling shows the bottleneck is the engine's own CPU cost, not Kafka — the broker barely breaks a sweat.");
}

// ================= Slide 5: E6 Spark finding (dark, dramatic) ===================================
{
  const s = darkSlide();
  kicker(s, "E6 — Engine Comparison", { color: C.anomaly });
  title(s, "The synopsis assumed Spark was necessary. It wasn't.", { size: 28 });
  s.addText("Identical detection logic. Identical data. Same host. Head-to-head, 69 runs, 0 incomplete.", {
    x: 0.6, y: 1.75, w: 11.8, h: 0.5, fontFace: "Calibri", fontSize: 15, italic: true, color: C.mutedLight, isTextBox: true, margin: 0,
  });
  const barData = [{ name: "Sustained throughput (k ev/s)", labels: ["Python engine", "Spark (local[2])"], values: [50, 3] }];
  s.addChart(pres.ChartType.bar, barData, {
    x: 0.6, y: 2.5, w: 6.0, h: 4.3,
    showTitle: true, title: "Sustained throughput", titleColor: C.textLight, titleFontSize: 14,
    showLegend: false, chartColors: [C.good], barDir: "col",
    catAxisLabelColor: C.mutedLight, valAxisLabelColor: C.mutedLight, valAxisTitle: "k events/s", showValAxisTitle: true, valAxisTitleColor: C.mutedLight,
    catGridLine: { style: "none" }, valGridLine: { color: C.line, size: 1 },
    showDataLabels: true, dataLabelPosition: "outEnd", dataLabelColor: C.textLight, dataLabelFontSize: 13, dataLabelFormatCode: '0"k"',
    dataLabelColorOverrides: undefined,
    chartColorsOpacity: 100,
  });
  const rx = 7.1, rw = 5.6;
  statTile(s, rx, 2.5, rw, 1.0, "≈ 17×", "higher sustained throughput, Python vs Spark", { valColor: C.good });
  statTile(s, rx, 3.65, rw, 1.0, "120–250×", "lower latency, Python vs Spark, at every shared rate", { valColor: C.good });
  statTile(s, rx, 4.8, rw, 1.0, "13.5× / 7.6×", "less CPU / memory, for byte-identical detections", { valColor: C.good });
  s.addText("Reading: not “Spark is bad” — Spark's micro-batch model has a fixed cost floor (3–6 s per batch) that doesn't amortize on one host at this event rate. Its design point is horizontal scale-out across many machines at far higher volumes than this study could produce.", {
    x: rx, y: 6.0, w: rw, h: 1.2, fontFace: "Calibri", fontSize: 11.5, italic: true, color: C.mutedLight, isTextBox: true, margin: 0,
  });
  pageNum(s, 5);
  notes(s, "This is the single most consequential finding relative to the original synopsis. The synopsis's literature review treated Spark or Flink as necessary machinery. We built both engines, verified they score identically, and benchmarked head to head. Python wins by an order of magnitude on every metric, at this scale, on this hardware. We are careful in the paper to frame this correctly: it's not that Spark is poorly built, it's that its overhead doesn't amortize below a certain scale, which this project's target never actually reached.");
}

// ================= Slide 6: Early detection (light) ==============================================
{
  const s = lightSlide();
  kicker(s, "Streaming Correctness", { color: C.signal });
  title(s, "The hardest bug: sessions have no natural end", { dark: false });
  s.addText("HDFS blocks live ~2 hours. A naive incremental classifier judges short, in-progress sessions as anomalous — because most of their expected content hasn't arrived yet.", {
    x: 0.6, y: 1.7, w: 11.8, h: 0.7, fontFace: "Calibri", fontSize: 15, color: C.muted, isTextBox: true, margin: 0,
  });
  const colW = 5.7, y0 = 2.6, colH = 3.8;
  s.addShape("roundRect", { x: 0.6, y: y0, w: colW, h: colH, rectRadius: 0.08, fill: { color: "FBEDE8" } });
  s.addText("Before: incremental-only", { x: 0.9, y: y0 + 0.25, w: colW - 0.6, h: 0.4, fontFace: "Calibri", fontSize: 16, bold: true, color: C.anomaly, isTextBox: true, margin: 0 });
  s.addText("40.2%", { x: 0.9, y: y0 + 0.8, w: 2.5, h: 1.0, fontFace: "Calibri", fontSize: 44, bold: true, color: C.anomaly, isTextBox: true, margin: 0 });
  s.addText("of anomalous test sessions have only 2–4 lines, then go silent — missed entirely", { x: 3.3, y: y0 + 0.95, w: colW - 2.8, h: 0.8, fontFace: "Calibri", fontSize: 13, color: C.text, isTextBox: true, margin: 0 });
  s.addText("Live F1 = 0.691", { x: 0.9, y: y0 + 2.1, w: colW - 0.6, h: 0.5, fontFace: "Calibri", fontSize: 20, bold: true, color: C.anomaly, isTextBox: true, margin: 0 });
  s.addText("(recall 0.598, precision 0.819)", { x: 0.9, y: y0 + 2.65, w: colW - 0.6, h: 0.4, fontFace: "Calibri", fontSize: 13, color: C.muted, isTextBox: true, margin: 0 });

  const x1 = 0.6 + colW + 0.35;
  s.addShape("roundRect", { x: x1, y: y0, w: colW, h: colH, rectRadius: 0.08, fill: { color: "E8F1F6" } });
  s.addText("After: + event-time age check", { x: x1 + 0.3, y: y0 + 0.25, w: colW - 0.6, h: 0.4, fontFace: "Calibri", fontSize: 16, bold: true, color: C.signal, isTextBox: true, margin: 0 });
  s.addText("A second detector, trained specifically on partial (age-bounded) snapshots of normal sessions, checks every session once it reaches 30 log-seconds old.", { x: x1 + 0.35, y: y0 + 0.8, w: colW - 0.7, h: 1.1, fontFace: "Calibri", fontSize: 13, color: C.text, isTextBox: true, margin: 0 });
  s.addText("Live F1 = 0.923", { x: x1 + 0.35, y: y0 + 2.1, w: colW - 0.6, h: 0.5, fontFace: "Calibri", fontSize: 20, bold: true, color: C.signal, isTextBox: true, margin: 0 });
  s.addText("(recall 0.986, precision 0.868) — latency p99 unchanged at ~98 ms", { x: x1 + 0.35, y: y0 + 2.65, w: colW - 0.6, h: 0.5, fontFace: "Calibri", fontSize: 13, color: C.muted, isTextBox: true, margin: 0 });
  pageNum(s, 6);
  notes(s, "This generalizes beyond log analytics: any streaming system that must render a verdict before an entity's lifecycle is complete faces this exact problem. Our fix recovered recall from 60% to 99%, at no latency cost.");
}

// ================= Slide 7: E5 Latency (dark, embedded figure) ===================================
{
  const s = darkSlide();
  kicker(s, "E5 — Latency Decomposition");
  title(s, "Where does the time go? Not the model.");
  s.addImage({ path: `${FIGDIR}/docs/perf/e5_latency_stages.png`, x: 0.7, y: 1.75, w: 7.4, h: 4.06 });
  const rx = 8.4, rw = 4.3;
  statTile(s, rx, 1.85, rw, 1.0, "~1 ms", "to SCORE a session — the model is never the bottleneck", { valColor: C.good });
  statTile(s, rx, 3.0, rw, 1.0, "17–37 ms", "engine micro-batch state update — the real cost", { valColor: C.signal });
  statTile(s, rx, 4.15, rw, 1.0, "~72 ms", "consumer Kafka fetch path (p99)", { valColor: C.signal });
  statTile(s, rx, 5.3, rw, 1.15, "2 of 44", "warm-broker runs had an unexplained stall (612 ms pooled p99) — disclosed, not hidden", { fill: "3A2A22", valColor: C.anomaly });
  pageNum(s, 7);
  notes(s, "Below saturation, typical p99 latency is 85 to 120 milliseconds — well under our 500ms target. We decomposed exactly where that time goes: scoring itself is about a millisecond. The real costs are the engine's own batch bookkeeping and the network fetch path. We also ran a full diagnostic investigation — GC logs, per-core CPU sampling — into two anomalous slow runs, and we report honestly that we could not fully explain them.");
}

// ================= Slide 8: E7 Elasticity (light, embedded figure) ================================
{
  const s = lightSlide();
  kicker(s, "E7 — Elasticity Under a Spike", { color: C.signal });
  title(s, "“Elastic” means faster recovery, not overload avoidance", { dark: false, size: 27 });
  s.addImage({ path: `${FIGDIR}/docs/perf/e7_spike_lag.png`, x: 0.6, y: 1.8, w: 7.2, h: 3.52 });
  const rows = [
    [{ text: "Configuration", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }, { text: "Peak lag", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }, { text: "Recovery", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }],
    ["Fixed, 1 worker", "764,076 msgs", "20.1 s"],
    ["Elastic, 1→2 workers", "598,768 msgs", "7.7 s"],
    ["Fixed, 2 workers", "365,731 msgs", "5.8 s"],
  ];
  s.addTable(rows, { x: 8.05, y: 1.85, w: 4.7, colW: [2.2, 1.3, 1.2], fontFace: "Calibri", fontSize: 12, border: { type: "solid", color: "E5E9F0", pt: 1 }, autoPage: false });
  s.addText("A 10× spike (15k→150k ev/s, 8 s). The autoscaler's new worker takes ~4 s to become useful (decision delay + startup) — it only helps for the second half of the spike.", {
    x: 8.05, y: 3.5, w: 4.7, h: 1.3, fontFace: "Calibri", fontSize: 12.5, color: C.muted, isTextBox: true, margin: 0,
  });
  s.addShape("roundRect", { x: 8.05, y: 5.0, w: 4.7, h: 1.6, rectRadius: 0.08, fill: { color: "FBEDE8" } });
  s.addText("No configuration tested keeps p99 latency under 500 ms during the spike itself.", { x: 8.3, y: 5.2, w: 4.2, h: 1.2, fontFace: "Calibri", fontSize: 13.5, bold: true, color: C.anomaly, isTextBox: true, margin: 0 });
  pageNum(s, 8);
  notes(s, "We tested three configurations under an injected 10x spike. Pre-provisioned capacity wins outright. Reactive autoscaling helps a lot versus doing nothing, but the physical reality of worker startup time means it only captures part of the benefit. And critically: nothing we tested prevents a queueing period during a severe spike. Elastic means recovers faster, not immune.");
}

// ================= Slide 9: E8 Concept Drift (dark, embedded figure) ==============================
{
  const s = darkSlide();
  kicker(s, "E8 — Concept Drift");
  title(s, "A static model fails silently. A cheap signal fixes it.");
  s.addImage({ path: `${FIGDIR}/docs/drift/e8_drift.png`, x: 0.55, y: 1.75, w: 8.3, h: 4.15 });
  const rx = 9.15, rw = 3.6;
  statTile(s, rx, 1.85, rw, 1.15, "0.866 → 0.025", "F1 collapse, one measurement window after log wording changes", { valColor: C.anomaly });
  statTile(s, rx, 3.15, rw, 1.15, "0.1% → 92%", "share of never-before-seen lines — the free, label-less drift signal", { valColor: C.signal });
  statTile(s, rx, 4.45, rw, 1.15, "0.745", "F1 recovered within one window of triggered retraining (0.4–0.5 s refit)", { valColor: C.good });
  s.addText("Scheduled (not triggered) retraining is itself unsafe: an unlabeled window containing real anomalies teaches the model they're normal (F1 as low as 0.05 with zero drift).", {
    x: rx, y: 5.75, w: rw, h: 1.4, fontFace: "Calibri", fontSize: 11.5, italic: true, color: C.mutedLight, isTextBox: true, margin: 0,
  });
  pageNum(s, 9);
  notes(s, "We simulated a software-update-style drift: the wording of common log messages changes. A static model's precision doesn't just degrade, it collapses to flagging everything. But there's a completely free, label-free signal for this: the share of log lines the model has never seen. It jumps from noise to over 90 percent immediately, and triggering a retrain on that signal recovers detection quality within one window. Important nuance: naive scheduled retraining is actually dangerous when real anomalies are common in the window.");
}

// ================= Slide 10: Detection quality + ablation honesty (light) ==========================
{
  const s = lightSlide();
  kicker(s, "E1 & Ablations — Detection Quality", { color: C.signal });
  title(s, "Strong on sessions (HDFS); a fixable gap on windows (BGL)", { dark: false, size: 27 });
  const rows = [
    [{ text: "Dataset", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }, { text: "PR-AUC", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }, { text: "F1", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }, { text: "Note", options: { bold: true, color: "FFFFFF", fill: { color: C.signal } } }],
    ["HDFS_v1 (PCA, streaming bundle)", "0.901", "0.938", "primary operating point"],
    ["HDFS_v1 (autoencoder)", "0.999", "0.997", "best quality, higher inference cost"],
    ["BGL, sublinear TF–IDF (as shipped)", "0.171", "0.377", "weak — see fix →"],
    ["BGL, binary features (ablation)", { text: "0.764", options: { bold: true, color: C.good } }, "0.555", "validation-selected fix, not yet shipped"],
  ];
  s.addTable(rows, { x: 0.6, y: 1.95, w: 12.1, colW: [4.6, 2.2, 1.8, 3.5], fontFace: "Calibri", fontSize: 13.5, border: { type: "solid", color: "E5E9F0", pt: 1 }, autoPage: false, rowH: 0.55 });
  s.addShape("roundRect", { x: 0.6, y: 4.55, w: 12.1, h: 1.9, rectRadius: 0.08, fill: { color: "E8F1F6" } });
  s.addText("We initially reported BGL's weak result at face value. An ablation pass traced it to one specific, correctable choice: TF–IDF over-weights the few frequent messages in a 1-hour window; simple binary presence lifts PR-AUC 4.4×, and validation data alone would have picked it. This was not silently fixed after the fact — the original numbers, the diagnosis, and the fix are all reported.", {
    x: 0.9, y: 4.75, w: 11.5, h: 1.55, fontFace: "Calibri", fontSize: 14, color: C.text, isTextBox: true, margin: 0,
  });
  s.addText("Drain's own hyperparameters (similarity threshold, tree depth) did not matter on either dataset — 12/12 combinations tied exactly.", {
    x: 0.6, y: 6.6, w: 12.1, h: 0.5, fontFace: "Calibri", fontSize: 12.5, italic: true, color: C.muted, isTextBox: true, margin: 0,
  });
  pageNum(s, 10);
  notes(s, "Detection quality on HDFS is excellent. BGL initially looked weak. Rather than leave that as a limitation of the method, we ran an ablation study and found it was a specific, fixable feature-representation choice. We report this exactly as it happened — including that the fix was NOT retroactively applied to the streaming numbers you saw earlier, to avoid presenting inconsistent figures across the study.");
}

// ================= Slide 11: What we found vs what the synopsis claimed (dark) ======================
{
  const s = darkSlide();
  kicker(s, "Synthesis");
  title(s, "Claim vs. evidence");
  const rows = [
    [{ text: "Synopsis claim", options: { bold: true, color: "FFFFFF", fill: { color: C.panelDark } } }, { text: "What the evidence shows", options: { bold: true, color: "FFFFFF", fill: { color: C.panelDark } } }],
    [">50,000 events/sec", "Met — by the plain Python engine (50k–70k), on one host"],
    ["Sub-500 ms processing", "Typical, not guaranteed — p99 ~100 ms below saturation, 2 unexplained stalls"],
    ["Spark/Flink necessary", { text: "Not supported — Python is 17× faster at this scale", options: { color: C.anomaly, bold: true } }],
    ["Elastic scaling", "Faster recovery (20.1s→7.7s), not overload immunity"],
    ["Drift-adaptive retraining", "Supported — but must be triggered, not scheduled"],
  ];
  s.addTable(rows, {
    x: 0.6, y: 1.85, w: 12.1, colW: [4.3, 7.8], fontFace: "Calibri", fontSize: 14,
    color: C.textLight, fill: { color: C.bgDark },
    border: { type: "solid", color: C.line, pt: 1 }, autoPage: false, rowH: 0.85,
  });
  pageNum(s, 11);
  notes(s, "To summarize against the original synopsis directly: the throughput target is met, but by the component the synopsis said was insufficient alone. The latency target is typically true, not universally true. The framework claim is the one place the evidence actively disagrees with the synopsis. Elasticity and drift-adaptation both hold, each with an important qualification we discovered empirically.");
}

// ================= Slide 12: Conclusion & Q&A (dark) ================================================
{
  const s = darkSlide();
  s.addText("Conclusion", { x: 0.8, y: 1.5, w: 8, h: 0.6, fontFace: "Calibri", fontSize: 15, bold: true, color: C.signal, charSpacing: 2, isTextBox: true, margin: 0 });
  s.addText("A system built to test its own thesis —\nand honest about where the thesis was wrong.", {
    x: 0.8, y: 2.0, w: 11.5, h: 1.6, fontFace: "Cambria", fontSize: 30, bold: true, color: C.textLight, lineSpacing: 38, isTextBox: true, margin: 0,
  });
  const items = [
    "8 research questions, 215+ repeated benchmark runs, 3 real LogHub datasets",
    "Throughput target met by the simpler component the literature said couldn't do it alone",
    "A novel early-detection mechanism for long-lived streaming sessions, generalizable beyond logs",
    "Concept drift is survivable with a free, label-free trigger signal",
    "Two findings reported as open and unresolved, not concealed",
  ];
  items.forEach((t, i) => s.addText(t, { x: 1.0, y: 3.75 + i * 0.5, w: 11, h: 0.48, fontFace: "Calibri", fontSize: 15, color: C.mutedLight, bullet: { code: "2013" }, isTextBox: true, margin: 0 }));
  s.addText("Thank you — Questions?", { x: 0.8, y: 6.55, w: 8, h: 0.6, fontFace: "Cambria", fontSize: 22, bold: true, color: C.good, isTextBox: true, margin: 0 });
  notes(s, "Thank you. Happy to take questions — including on the two things we could not fully explain, which I'd rather discuss openly than pretend didn't happen.");
}

pres.writeFile({ fileName: process.argv[2] }).then(() => console.log("wrote", process.argv[2]));
