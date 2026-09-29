# Live demo script (defense)

Two variants: the **UI demo** (recommended — this exact flow was scripted and passed end-to-end with a real
Chrome browser in Week 5, see `ui/e2e/smoke.mjs`) and the **4-pane terminal demo** from the original project
notebook, using the actual commands this repo runs (every command below has been executed successfully at
least once during development; this is not aspirational). Budget 5 minutes either way. **Do one full dry run
within 24 hours of the defense** — this script assembles proven commands, it is not itself a substitute for
rehearsing on the day's machine.

## Before the jury arrives

```bash
cd "logsentinel"
scripts/kafka.sh status                 # start if not "running": scripts/kafka.sh start ; wait for "kafka up"
ls models/                              # confirm a bundle exists, e.g. hdfs-drain-pca-early
```

If no model is registered/active yet:
```bash
.venv/bin/python -m logsentinel.models.train --dataset hdfs --parser drain --model pca \
  --early-age 30 --early-model ae --out models/hdfs-drain-pca-early    # ~30 s
.venv/bin/python -m logsentinel.stream.pools                            # anomaly pool for injection, ~10 s
```

---

## Variant A: UI demo (recommended)

```bash
make ui                                 # once per checkout: npm install + build ui/dist
.venv/bin/python -m logsentinel.alerts.sink &
.venv/bin/python -m logsentinel.api &
```
Open `http://127.0.0.1:8000` in a browser.

1. **Models page** — register the bundle (`models/hdfs-drain-pca-early`) and click Activate. *Say: "one active
   model per dataset; the engine loads whichever is promoted."*
2. **Source page** — set rate 2,000 ev/s, sessions 10,000, scenario Normal, click **Start source**. Watch the
   progress bar move.
3. **Dashboard** — switch tabs. Live throughput and lag charts fill in within ~2 seconds. *Say: "every number
   here comes off Kafka in real time, not a mock."*
4. **Back to Source, mid-run** — set count 100, click **Inject anomaly burst**. *Say: "this injects real
   labeled-anomalous HDFS sessions, held out from training, stamped at the current stream time."*
5. **Alerts page** — within a second or two, the injected sessions appear as alerts. Open one, show the score/
   threshold/evidence-delay fields, click **Acknowledge** then **Resolve**. *Say: "triage feeds back into
   threshold tuning — every action is audit-logged."*
6. **Source page, injection table** — point at the detection-rate and time-to-alert columns for the burst just
   injected (typically ~95–100% detected, well under a second median).
7. **Experiments page** — click **Rebuild report** under "Rebuild report", show the regenerated E1–E3 figures
   appearing live. *Say: "every figure in the paper is produced by this exact button, not copied by hand."*

Stop cleanly: Ctrl+C both background processes, or `pkill -f "logsentinel.api"` / `pkill -f "logsentinel.alerts.sink"`.

---

## Variant B: 4-pane terminal demo (from the original project notebook)

Four terminals, tiled. This is the more "systems" visual: raw throughput and alert JSON scrolling live.

**Pane 1 — the attacker / producer:**
```bash
.venv/bin/python -m logsentinel.experiments.stream_e2e --bundle active:hdfs --rate 5000 --sessions 20000 --run-id demo
```
This single command drives panes 2–4 by itself (it starts the engine and replays traffic); for a *manual*
4-pane split instead, run the pieces separately:

**Pane 2 — the stream engine** (throughput/lag ticking once a second):
```bash
.venv/bin/python -m logsentinel.stream.engine --bundle active:hdfs --group demo --run-dir /tmp/demo
```

**Pane 3 — the alert sink** (persists alerts as they're detected):
```bash
.venv/bin/python -m logsentinel.alerts.sink --group demo-sink
```

**Pane 4 — the producer/attacker**, started last, once panes 2–3 show "ready":
```bash
.venv/bin/python -c "
from logsentinel.experiments.harness import Ctx
from logsentinel.stream.producer import replay_segments
from logsentinel.experiments.stream_e2e import replay_events
from logsentinel.features.counts import load_or_build
cf = load_or_build('hdfs', 'chronological')
ids, events = replay_events(cf, 20000)
replay_segments(events, '127.0.0.1:9092', [[len(events), 5000.0]], 6)   # segments are (n_events, rate), not (seconds, rate)
"
```
*Say, while pane 2 shows throughput and pane 3 prints alert JSON scrolling by: "sub-100-millisecond alerts,
sustained multi-thousand events per second, on one laptop-class machine — no cluster."*

For the injection moment, in a fifth ad-hoc terminal:
```bash
.venv/bin/python -c "
from logsentinel.stream import inject, pools
from logsentinel.store.db import connect, latest_watermark
with connect() as con:
    wm = latest_watermark(con, 'demo') or 300000.0
events, keys = inject.build_burst(pools.load(), 50, wm, tag=1)
inject.send(events, '127.0.0.1:9092')
print('injected', len(keys), 'anomalous sessions')
"
```
Watch pane 3 print the corresponding alerts within roughly the median time-to-alert reported in `docs/results-e6.md`.

---

## If something goes wrong live

- **Kafka not up**: `scripts/kafka.sh start`, wait ~10 s for "kafka up" before anything else.
- **No active model**: fall back to Variant B's `--bundle active:hdfs` → replace with the literal path
  `models/hdfs-drain-pca-early` if the registry is empty.
- **Port 8000 already in use**: `pkill -f "logsentinel.api"` first.
- **Whole demo unrecoverable**: fall back to walking through the pre-generated figures in `docs/perf/`,
  `docs/drift/`, and `docs/perf/e6/` — every one of them is a real result, not a mockup, and the paper/deck
  already reference them by name.
