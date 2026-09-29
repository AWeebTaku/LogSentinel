import type { Status } from "./api";

export const fmtInt = (n: number | null | undefined) => (n == null ? "n/a" : Math.round(n).toLocaleString("en-US"));
export const fmtMs = (n: number | null | undefined) =>
  n == null ? "n/a" : n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${n.toFixed(n < 10 ? 1 : 0)} ms`;
export const fmtScore = (n: number) => n.toFixed(3);
export const fmtPct = (n: number | null | undefined) => (n == null ? "n/a" : `${(n * 100).toFixed(1)}%`);

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  return n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** "12 s ago" style age for a wall-clock timestamp in nanoseconds. */
export function ago(ns: number, nowMs = Date.now()): string {
  const s = Math.max(0, Math.round((nowMs - ns / 1e6) / 1000));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`;
}

export const STATUS_LABEL: Record<Status, string> = {
  open: "Open", acknowledged: "Acknowledged", resolved: "Resolved", false_positive: "False positive",
};

// Mirrors store/db.py TRANSITIONS: the actions offered for an alert in each state.
export const TRANSITIONS: Record<Status, Status[]> = {
  open: ["acknowledged", "resolved", "false_positive"],
  acknowledged: ["resolved", "false_positive", "open"],
  resolved: ["open"],
  false_positive: ["open"],
};

export const ACTION_LABEL: Record<Status, string> = {
  open: "Reopen", acknowledged: "Acknowledge", resolved: "Resolve", false_positive: "Mark false positive",
};

/** Equal-width histogram edges -> Carbon bar chart rows. */
export function histogramRows(edges: number[], counts: number[]) {
  return counts.map((value, i) => ({ group: "Alerts", key: `${edges[i].toFixed(2)}`, value }));
}
