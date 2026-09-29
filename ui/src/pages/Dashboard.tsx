import { ProgressBar, SkeletonText, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@carbon/react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ScoreHistogram, TimeChart } from "../components/charts";
import { Empty, Kpi, Notice, Page, RunStatusTag } from "../components/common";
import { ago, fmtInt, fmtMs, fmtScore } from "../format";
import { usePoll } from "../hooks";

const lastNonNull = <T,>(xs: T[], pick: (x: T) => number | null) => {
  for (let i = xs.length - 1; i >= 0; i--) {
    const v = pick(xs[i]);
    if (v != null) return v;
  }
  return null;
};

export default function Dashboard() {
  const nav = useNavigate();
  const src = usePoll(api.currentSource, 2000);
  const run = src.data?.run ?? null;
  const runId = run?.id;
  const metrics = usePoll(() => (runId ? api.metrics(runId, 180) : Promise.resolve({ items: [] })), 1500, [runId]);
  const stats = usePoll(() => api.stats(runId), 3000, [runId]);
  const recent = usePoll(() => api.alerts({ run: runId, limit: 8 }), 3000, [runId]);

  const pts = metrics.data?.items ?? [];
  const last = pts.at(-1);
  const prog = src.data?.progress;
  const error = src.error ?? metrics.error ?? stats.error;

  if (src.loading) return <Page title="Dashboard"><SkeletonText paragraph lineCount={6} /></Page>;
  if (!run) {
    return (
      <Page title="Dashboard" lead="Live throughput, lag, latency and alerts for the running pipeline.">
        <Notice error={error} title="API unavailable" />
        <Empty
          title="No pipeline has run yet"
          body="Start a source to replay HDFS logs through Kafka and the detection engine. Live metrics and alerts appear here within a few seconds."
          action={{ label: "Open Source", onClick: () => nav("/source") }}
        />
      </Page>
    );
  }
  const pct = prog?.total ? Math.min(100, ((prog.sent ?? 0) / prog.total) * 100) : 0;

  return (
    <Page title="Dashboard" lead="Live throughput, lag, latency and alerts for the current run.">
      <Notice error={error} />
      <div className="panel">
        <div className="row" style={{ alignItems: "center" }}>
          <div><span className="muted">Run </span><span className="num">{run.id}</span></div>
          <RunStatusTag status={run.status} />
          <div className="muted">{prog?.phase && prog.phase !== run.status ? `Phase: ${prog.phase}, ` : ""}{prog?.scenario ? `scenario: ${prog.scenario}` : ""}</div>
          <div style={{ flex: 1, minWidth: "16rem" }}>
            <ProgressBar
              label="Replay progress" size="small" value={pct} max={100}
              helperText={`${fmtInt(prog?.sent)} of ${fmtInt(prog?.total)} events`}
              status={run.status === "failed" ? "error" : run.status === "running" ? "active" : "finished"}
            />
          </div>
        </div>
      </div>

      <div className="kpis" role="group" aria-label="Key metrics">
        <Kpi label="Events per second" value={fmtInt(last?.rate_eps)} sub="consumed by the engine" />
        <Kpi label="Consumer lag" value={fmtInt(last?.lag)} sub="messages behind the producer" />
        <Kpi label="Open sessions" value={fmtInt(last?.open_sessions)} sub="held in engine state" />
        <Kpi label="Alerts" value={fmtInt(stats.data?.total)} sub={`${fmtInt(stats.data?.by_status.open)} open`} />
        <Kpi label="Alert latency p99" value={fmtMs(lastNonNull(pts, (p) => p.alert_lat_p99))} sub="event to alert, last alerting second" />
        <Kpi label="Batch time p95" value={fmtMs(last?.batch_ms_p95)} sub="per micro-batch, all sessions" />
      </div>

      <div className="grid-2">
        <div className="panel"><TimeChart title="Throughput" unit="events per second" points={pts} series={[{ label: "Events/s", pick: (p) => p.rate_eps }]} /></div>
        <div className="panel"><TimeChart title="Consumer lag" unit="messages" points={pts} series={[{ label: "Lag", pick: (p) => p.lag }]} /></div>
        <div className="panel">
          <TimeChart
            title="Latency" unit="milliseconds" points={pts}
            series={[
              { label: "Alert p50", pick: (p) => p.alert_lat_p50 }, { label: "Alert p95", pick: (p) => p.alert_lat_p95 },
              { label: "Alert p99", pick: (p) => p.alert_lat_p99 }, { label: "Batch p95", pick: (p) => p.batch_ms_p95 },
            ]}
          />
        </div>
        <div className="panel">
          {stats.data && stats.data.score_histogram.counts.length > 0
            ? <ScoreHistogram edges={stats.data.score_histogram.edges} counts={stats.data.score_histogram.counts} />
            : <Empty title="No alerts yet" body="The score distribution appears once the engine raises its first alert." />}
        </div>
      </div>

      <div className="panel">
        <h2>Latest alerts</h2>
        {recent.data && recent.data.items.length === 0 ? (
          <p className="muted">No alerts for this run so far.</p>
        ) : (
          <Table size="sm" aria-label="Latest alerts">
            <TableHead>
              <TableRow>
                <TableHeader>Session</TableHeader><TableHeader>Kind</TableHeader><TableHeader>Score</TableHeader>
                <TableHeader>Status</TableHeader><TableHeader>Raised</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {(recent.data?.items ?? []).map((a) => (
                <TableRow key={a.id} onClick={() => nav("/alerts")} style={{ cursor: "pointer" }}>
                  <TableCell className="num">{a.session_key}</TableCell><TableCell>{a.kind}</TableCell>
                  <TableCell className="num">{fmtScore(a.score)}</TableCell><TableCell>{a.status}</TableCell>
                  <TableCell>{ago(a.created_ns)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </Page>
  );
}
