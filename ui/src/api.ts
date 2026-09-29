// Typed client for the LogSentinel REST API (see docs/api.md).
export const BASE: string =
  (import.meta.env.VITE_API as string | undefined) ?? (location.port === "8000" ? "" : "http://127.0.0.1:8000");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(BASE + path, { ...init, headers: { "content-type": "application/json", ...init?.headers } });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is `python -m logsentinel.api` running?");
  }
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const d = (await r.json()).detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : (d?.message ?? msg);
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

const q = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};
const post = <T,>(path: string, body?: unknown) =>
  req<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export type Status = "open" | "acknowledged" | "resolved" | "false_positive";

export interface Alert {
  id: number; run: string; session_key: string; model: string | null; kind: string; score: number;
  threshold: number | null; n_lines: number | null; evidence_log_s: number | null; ingest_lag_ms: number | null;
  status: Status; note: string; created_ns: number; updated_ns: number;
}
export interface AlertEvent { ts_ns: number; from_status: string | null; to_status: string; actor: string; note: string }
export interface AlertDetail extends Alert { events: AlertEvent[] }
export interface Stats {
  total: number; by_status: Partial<Record<Status, number>>; by_kind: Record<string, number>;
  false_positive_rate_triaged: number | null; median_ingest_lag_ms: number | null;
  score_histogram: { edges: number[]; counts: number[] };
}
export interface MetricPoint {
  t: number; rate_eps: number; lag: number; open_sessions: number; alerts: number; alerts_interval: number;
  batch_ms_p95: number | null; alert_lat_p50: number | null; alert_lat_p95: number | null;
  alert_lat_p99: number | null; watermark: number | null;
}
export interface Run {
  id: string; kind: string; status: string; params: Record<string, unknown>; summary: Record<string, unknown> | null;
  pid: number | null; model_id: number | null; created_ns: number; updated_ns: number;
}
export interface Progress {
  phase?: string; sent?: number; total?: number; scenario?: string; rate?: number; workers?: number;
}
export interface Model {
  id: number; name: string; version: number; path: string; dataset: string; status: string;
  meta: Record<string, unknown> & { early?: { age_s: number; model: string } };
  metrics: Record<string, unknown> | null; created_ns: number;
}
export interface Injection {
  id: number; scenario: string; count: number; detected: number;
  time_to_alert_ms_p50: number | null; time_to_alert_ms_max: number | null;
}
export interface Artifact { path: string; size: number }

export const api = {
  health: () => req<{ status: string; alerts: number; models: number }>("/health"),
  alerts: (f: { status?: string; kind?: string; run?: string; min_score?: number; limit?: number }) =>
    req<{ items: Alert[] }>(`/alerts${q({ ...f, order: "desc" })}`),
  alert: (id: number) => req<AlertDetail>(`/alerts/${id}`),
  setStatus: (id: number, status: Status, note = "", actor = "analyst") =>
    req<AlertDetail>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify({ status, note, actor }) }),
  stats: (run?: string) => req<Stats>(`/alerts/stats${q({ run })}`),
  metrics: (run: string, limit = 180) => req<{ items: MetricPoint[] }>(`/metrics${q({ run, limit })}`),
  currentSource: () => req<{ run: Run | null; progress: Progress }>("/sources/current"),
  startSource: (b: { rate: number; sessions: number; workers: number; scenario: string; bundle?: string }) =>
    post<Run>("/sources/start", b),
  stopSource: (id: string) => post<Run>(`/sources/${id}/stop`),
  inject: (id: string, count: number) =>
    post<{ injection_id: number; count: number; lines: number }>(`/sources/${id}/inject`, { scenario: "anomaly_burst", count }),
  injections: (id: string) => req<{ items: Injection[] }>(`/sources/${id}/injections`),
  models: () => req<{ items: Model[] }>("/models"),
  registerModel: (path: string, name?: string) => post<Model>("/models/register", { path, name: name || undefined }),
  activateModel: (id: number) => post<Model>(`/models/${id}/activate`),
  trainModel: (b: Record<string, unknown>) => post<Run>("/models/train", b),
  runs: (kind?: string) => req<{ items: Run[] }>(`/runs${q({ kind })}`),
  run: (id: string) => req<Run>(`/runs/${id}`),
  runLog: (id: string, tail = 60) => req<{ lines: string[] }>(`/runs/${id}/log${q({ tail })}`),
  runExperiment: (b: Record<string, unknown>) => post<Run>("/experiments/run", b),
  experimentFiles: (id: string) => req<{ items: Artifact[] }>(`/experiments/${id}/files`),
  fileUrl: (path: string) => `${BASE}/files${q({ path })}`,
  fileText: async (path: string) => {
    const r = await fetch(`${BASE}/files${q({ path })}`);
    if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
    return r.text();
  },
};
