# UI (Week 5)

React + TypeScript + Vite in `ui/`, built with **IBM Carbon** (`@carbon/react`, Carbon Charts, Carbon icons, IBM Plex
self-hosted through `@fontsource`). Carbon because this is dense operations UI: the design guidance in use says
dashboards are out of scope for its marketing-page rules and points to an official system, and Carbon is the one
named for analytics. Dark by default (follows the system preference), light toggle in the header. Hash routing, since
the API serves the bundle from `/` and paths such as `/alerts` are API endpoints.

```bash
cd ui && npm install && npm run build      # produces ui/dist, served by: python -m logsentinel.api  ->  http://127.0.0.1:8000
cd ui && npm run dev                       # dev server on :5173, talks to the API on :8000 (CORS allowed)
cd ui && npm test                          # vitest: formatting + the alert lifecycle mirror
cd ui && node e2e/smoke.mjs                # real-Chrome demo flow (needs API, Kafka, sink, an active model)
```

Pages: **Dashboard** (live rate, lag, open sessions, latency percentiles, alert score distribution, latest alerts),
**Alerts** (filters, batch triage, detail with audit trail), **Source** (start/stop, scenarios normal and spike,
anomaly burst injection with detection results), **Models** (registry, activate, compare, register, train jobs with
logs), **Experiments** (stream benchmark, offline subset, report rebuild; figures and file previews).

Live data flow: engine -> Kafka `logsentinel-metrics` (1 message per second per worker) and `alerts-critical` ->
sink -> SQLite -> API -> UI polling (1.5 to 4 s). Polling pauses while the tab is hidden.

Not done: push updates (polling only), authentication, the concept-drift scenario (shown but disabled), mobile layout
(the grid collapses under 1056 px but was not tested on a phone), an accessibility audit beyond Carbon's defaults.
