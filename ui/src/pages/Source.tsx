import {
  Button, NumberInput, ProgressBar, Select, SelectItem, SkeletonText, Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@carbon/react";
import { Play, Stop } from "@carbon/icons-react";
import { useState } from "react";
import { api, type Run } from "../api";
import { DefList, Info, Notice, Page, RunStatusTag } from "../components/common";
import { ago, fmtInt, fmtMs, fmtPct } from "../format";
import { usePoll } from "../hooks";

const hi = (r: Run) => (r.summary ?? {}) as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function Source({ variant = "admin" }: { variant?: "operator" | "admin" }) {
  const [rate, setRate] = useState(2000);
  const [sessions, setSessions] = useState(10000);
  const [workers, setWorkers] = useState(1);
  const [scenario, setScenario] = useState("normal");
  const [bundle, setBundle] = useState("active:hdfs");   // operator never changes this: always whatever was promoted/activated
  const [count, setCount] = useState(100);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isOp = variant === "operator";
  // /models, /sources/{id}/injections and /runs are all admin-only routes (refused server-side in
  // operator mode), so operator must never poll them -- it has no injection panel or model picker
  // to feed anyway.
  const cur = usePoll(api.currentSource, 1000);
  const run = cur.data?.run ?? null;
  const prog = cur.data?.progress;
  const running = run?.status === "running";
  const streaming = running && prog?.phase === "running";
  const models = usePoll(isOp ? () => Promise.resolve({ items: [] }) : api.models, 5000);
  const inj = usePoll(() => (run && !isOp ? api.injections(run.id) : Promise.resolve({ items: [] })), 2000, [run?.id, isOp]);
  const runs = usePoll(isOp ? () => Promise.resolve({ items: [] }) : () => api.runs("source"), 4000);
  const active = models.data?.items.find((m) => m.status === "active");

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null); setMsg(null); setBusy(true);
    try { await fn(); setMsg(ok); } catch (e) { setErr((e as Error).message); }
    setBusy(false); cur.reload(); inj.reload(); runs.reload();
  };
  const pct = prog?.total ? Math.min(100, ((prog.sent ?? 0) / prog.total) * 100) : 0;
  const etaS = prog?.total && prog.rate && streaming ? Math.max(0, (prog.total - (prog.sent ?? 0)) / prog.rate) : null;

  return (
    <Page
      title="Source"
      lead={isOp
        ? "Start or stop live ingestion. This instance runs whatever model was promoted to it; it never trains or tests."
        : "Replay HDFS logs through Kafka and the detection engine, and inject scenarios while it runs."}
    >
      <Notice error={err ?? cur.error} />
      {msg && <p className="muted" role="status" style={{ marginBottom: ".5rem" }}>{msg}</p>}
      {/* operator can't read /models (admin-only route): a missing active model surfaces as the
          409 Start returns, not a client-side check here */}
      {!isOp && !active && !models.loading && (
        <Info title="No active model">Register and activate a model under Models before starting a source.</Info>
      )}
      {isOp && (
        <Info title="External log source">
          This never produces log traffic itself -- it only starts the detection engine watching
          whatever arrives on Kafka's logs-raw topic. Run a log source separately: for now, before a
          real log shipper exists, that's <code>python -m logsentinel.stream.live_feed</code> (or{" "}
          <code>make live-feed</code>), which stands in for a real system continuously generating
          logs. When a real shipper exists, it publishes to the same topic and nothing here changes.
        </Info>
      )}

      <div className="grid-2">
        <div className="panel">
          <h2>{isOp ? "Start watching" : "Start a run"}</h2>
          {isOp ? (
            <div className="row">
              <Select id="s-workers-op" labelText="Engine workers" value={String(workers)} disabled={running} onChange={(e) => setWorkers(Number(e.target.value))}>
                {[1, 2, 4].map((n) => <SelectItem key={n} value={String(n)} text={String(n)} />)}
              </Select>
            </div>
          ) : (
            <>
              <div className="row">
                <NumberInput id="s-rate" label="Events per second" min={10} max={200000} step={500} value={rate}
                  disabled={running} onChange={(_e, { value }) => setRate(Number(value))} helperText="Spike runs 10x this mid-stream" />
                <NumberInput id="s-sessions" label="Sessions to replay" min={100} max={172519} step={1000} value={sessions}
                  disabled={running} onChange={(_e, { value }) => setSessions(Number(value))} helperText="About 19 lines each" />
              </div>
              <div className="row" style={{ marginTop: "1rem" }}>
                <Select id="s-scn" labelText="Scenario" value={scenario} disabled={running} onChange={(e) => setScenario(e.target.value)}>
                  <SelectItem value="normal" text="Normal traffic" />
                  <SelectItem value="spike" text="Traffic spike (10x for 20% of the run)" />
                  <SelectItem value="drift" text="Concept drift (not available yet)" disabled />
                </Select>
                <Select id="s-workers" labelText="Engine workers" value={String(workers)} disabled={running} onChange={(e) => setWorkers(Number(e.target.value))}>
                  {[1, 2, 4].map((n) => <SelectItem key={n} value={String(n)} text={String(n)} />)}
                </Select>
                <Select id="s-model" labelText="Model" value={bundle} disabled={running} onChange={(e) => setBundle(e.target.value)}>
                  <SelectItem value="active:hdfs" text={active ? `Active: ${active.name} v${active.version}` : "Active model"} />
                  {(models.data?.items ?? []).map((m) => (
                    <SelectItem key={m.id} value={`models/${m.path.split("/").pop()}`} text={`${m.name} v${m.version}`} />
                  ))}
                </Select>
              </div>
            </>
          )}
          <div className="actions">
            <Button renderIcon={Play} disabled={running || busy}
              onClick={() => act(
                () => (isOp ? api.watchSource({ workers }) : api.startSource({ rate, sessions, workers, scenario, bundle })),
                isOp ? "Watching for live traffic." : "Source started.",
              )}>
              {isOp ? "Start watching" : "Start source"}
            </Button>
            <Button kind="danger--tertiary" renderIcon={Stop} disabled={!running || busy} onClick={() => run && act(() => api.stopSource(run.id), "Stop requested. The engine drains and flushes first.")}>Stop</Button>
          </div>
        </div>

        <div className="panel">
          <h2>Current run</h2>
          {cur.loading ? <SkeletonText paragraph lineCount={4} /> : !run ? (
            <p className="muted">No run yet. Start one on the left.</p>
          ) : isOp ? (
            <>
              <DefList items={[
                ["Run", <span className="num">{run.id}</span>], ["Status", <RunStatusTag status={run.status} />],
                ["Phase", prog?.phase && prog.phase !== run.status ? prog.phase : "same as status"],
                ["Started", ago(run.created_ns)], ["Workers", String(prog?.workers ?? "n/a")],
              ]} />
              <p className="muted" style={{ marginTop: "1rem" }}>
                {running ? "Watching logs-raw for events. No fixed end -- stop it when you're done." : "Not running."}
              </p>
              {run.status === "failed" && <p className="muted" style={{ marginTop: ".75rem" }}>The run failed. See the supervisor log under results/sources/{run.id}/log.</p>}
            </>
          ) : (
            <>
              <DefList items={[
                ["Run", <span className="num">{run.id}</span>], ["Status", <RunStatusTag status={run.status} />],
                ["Phase", prog?.phase && prog.phase !== run.status ? prog.phase : "same as status"], ["Scenario", prog?.scenario ?? "n/a"],
                ["Started", ago(run.created_ns)], ["Time left", etaS == null ? "n/a" : `about ${Math.ceil(etaS)} s`],
              ]} />
              <div style={{ marginTop: "1rem" }}>
                <ProgressBar label="Replay progress" value={pct} max={100} size="small"
                  helperText={`${fmtInt(prog?.sent)} of ${fmtInt(prog?.total)} events`}
                  status={run.status === "failed" ? "error" : running ? "active" : "finished"} />
              </div>
              {run.status === "failed" && <p className="muted" style={{ marginTop: ".75rem" }}>The run failed. See the supervisor log under results/sources/{run.id}/log.</p>}
            </>
          )}
        </div>
      </div>

      {!isOp && (
        <div className="panel">
          <h2>Inject a scenario</h2>
          <p className="muted" style={{ marginBottom: "1rem", maxWidth: "70ch" }}>
            Sends known-anomalous sessions (from the held-out test split) into the live stream, stamped with the current stream time.
            The table shows how many were alerted on and how quickly.
          </p>
          <div className="row">
            <NumberInput id="i-count" label="Anomalous sessions" min={1} max={2000} step={50} value={count} onChange={(_e, { value }) => setCount(Number(value))} />
            <Button disabled={!streaming || busy} onClick={() => run && act(() => api.inject(run.id, count), `Injected ${count} anomalous sessions.`)}>Inject anomaly burst</Button>
          </div>
          {!streaming && <p className="muted" style={{ marginTop: ".5rem" }}>Available while a run is streaming.</p>}
          {(inj.data?.items.length ?? 0) > 0 && (
            <div style={{ marginTop: "1rem" }}><Table size="sm" aria-label="Injections">
              <TableHead><TableRow>
                <TableHeader>#</TableHeader><TableHeader>Sessions</TableHeader><TableHeader>Alerted</TableHeader>
                <TableHeader>Detection rate</TableHeader><TableHeader>Median time to alert</TableHeader><TableHeader>Slowest</TableHeader>
              </TableRow></TableHead>
              <TableBody>
                {inj.data!.items.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell className="num">{i.id}</TableCell><TableCell className="num">{i.count}</TableCell>
                    <TableCell className="num">{i.detected}</TableCell><TableCell className="num">{fmtPct(i.detected / i.count)}</TableCell>
                    <TableCell className="num">{fmtMs(i.time_to_alert_ms_p50)}</TableCell><TableCell className="num">{fmtMs(i.time_to_alert_ms_max)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table></div>
          )}
        </div>
      )}

      {!isOp && (
        <div className="panel">
          <h2>Recent runs</h2>
          {(runs.data?.items.length ?? 0) === 0 ? <p className="muted">Finished runs are listed here with their detection quality.</p> : (
            <Table size="sm" aria-label="Recent runs">
              <TableHead><TableRow>
                <TableHeader>Run</TableHeader><TableHeader>Status</TableHeader><TableHeader>Started</TableHeader>
                <TableHeader>Sessions</TableHeader><TableHeader>Alerts</TableHeader><TableHeader>Live P / R / F1</TableHeader><TableHeader>Injected alerted</TableHeader>
              </TableRow></TableHead>
              <TableBody>
                {runs.data!.items.slice(0, 8).map((r) => {
                  const s = hi(r); const st = s.stream_alert_any_time;
                  return (
                    <TableRow key={r.id}>
                      <TableCell className="num">{r.id}</TableCell><TableCell><RunStatusTag status={r.status} /></TableCell>
                      <TableCell>{ago(r.created_ns)}</TableCell>
                      <TableCell className="num">{s.sessions_scored ? fmtInt(s.sessions_scored) : "n/a"}</TableCell>
                      <TableCell className="num">{s.alerts != null ? fmtInt(s.alerts) : "n/a"}</TableCell>
                      <TableCell className="num">{st ? `${st.precision.toFixed(2)} / ${st.recall.toFixed(2)} / ${st.f1.toFixed(2)}` : "n/a"}</TableCell>
                      <TableCell className="num">{s.injected_sessions ? `${s.injected_alerted} of ${s.injected_sessions}` : "n/a"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </Page>
  );
}
