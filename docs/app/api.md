# LogSentinel API (Week 4)

`python -m logsentinel.api` serves on `127.0.0.1:8000` (localhost only, **no authentication**); interactive docs at
`/docs`, schema at `/openapi.json`. CORS allows `localhost`/`127.0.0.1` on ports 5173 and 3000 for a dev UI.
DB: SQLite (WAL) at `$LOGSENTINEL_DB` or `data/logsentinel.db`.

Data path: engine -> Kafka `alerts-critical` -> **sink** (`python -m logsentinel.alerts.sink`) -> SQLite <- API.
The sink commits offsets only after the DB commit; `UNIQUE (run, session_key)` makes replays harmless; malformed
messages are counted and skipped; a failed offset commit is logged, not fatal.

| Method & path | Purpose |
|---|---|
| `GET /health` | liveness + row counts |
| `GET /alerts?status=&kind=&run=&min_score=&after_id=&limit=` | inbox; keyset pagination (`next_after_id`) |
| `GET /alerts/stats?run=` | counts by status/kind/run, FP rate among triaged, median sink lag |
| `GET /alerts/{id}` | alert + audit trail |
| `PATCH /alerts/{id}` `{status, note?, actor?}` | lifecycle move; 409 with `allowed` on an illegal move |
| `GET /models?dataset=`, `GET /models/{id}`, `GET /models/active?dataset=` | registry |
| `POST /models/register` `{path, name?, metrics?}` | register a bundle dir (must be inside `models/`); versions per name |
| `POST /models/{id}/activate` | one active model per dataset; engines start with `--bundle active:<dataset>` |
| `PUT /models/{id}/metrics` | attach offline/online metrics for comparison |
| `POST /models/train` | async training job (subprocess); model auto-registered on success |
| `GET /runs?kind=`, `GET /runs/{id}`, `GET /runs/{id}/log` | jobs and imported experiment runs |
| `POST /runs/import` `{kind, path}` | import `results/<...>/summary.json` (path must be inside `results/`) |

Alert lifecycle (no self-transitions; closed alerts must be reopened):
`open -> acknowledged | resolved | false_positive`; `acknowledged -> open | resolved | false_positive`;
`resolved | false_positive -> open`. Every move is written to `alert_events` with actor and note.
`false_positive_rate_triaged` is the operator feedback signal intended for threshold tuning (used in Week 5+).

Notes: an engine does not hot-reload; promoting a model takes effect when the engine is (re)started. Training via the
API supports HDFS bundles only (same as the streaming path).

## Added in Week 5
| Method & path | Purpose |
|---|---|
| `GET /metrics?run=&since_ns=&limit=` | per-second series for a run (rate, lag, open sessions, latency percentiles, batch time); summed over workers, percentiles are the max over workers |
| `POST /sources/start` `{rate, sessions, workers, scenario, bundle}` | start a live pipeline session (Kafka topics, engine workers, replay). One at a time (409 otherwise); 503 if Kafka is down |
| `GET /sources/current` | latest source run plus `progress.json` (phase, sent, total) |
| `POST /sources/{id}/stop` | ask the supervisor to stop; engines still drain and flush |
| `POST /sources/{id}/inject` `{count}` | inject known-anomalous sessions stamped at the current stream time (needs `python -m logsentinel.stream.pools` once) |
| `GET /sources/{id}/injections` | per injection: sessions, how many were alerted on, median and slowest time to alert |
| `POST /experiments/run` `{preset, ...}` | presets: `stream_benchmark`, `offline_subset`, `offline_report`; artifacts listed by `GET /experiments/{id}/files` |
| `GET /files?path=results/...` | download a result file (png, md, csv, json, txt, log only; path must be inside `results/`) |
| `GET /runs/{id}/log` | tail of a job's log; empty (not 404) before the job has written anything |

`GET /alerts` also takes `order=desc` (newest first, used by the inbox). `GET /alerts/stats` includes `score_histogram`
of score divided by each alert's own threshold (the incremental and age-check detectors use different score scales).
Jobs (training, sources, experiments) run under `logsentinel.api.runner`, which forwards SIGTERM and always writes an
exit code, so their state survives an API restart. Finished sources and experiments have their `summary.json`
stored on the run record.
