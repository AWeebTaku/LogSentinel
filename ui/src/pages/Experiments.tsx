import { Button, Checkbox, NumberInput, Select, SelectItem, SkeletonText, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@carbon/react";
import { Download } from "@carbon/icons-react";
import { useEffect, useState } from "react";
import { api, type Artifact } from "../api";
import { DefList, Empty, Notice, Page, RunStatusTag } from "../components/common";
import { ago, fmtBytes, fmtInt, fmtMs } from "../format";
import { usePoll } from "../hooks";

const PRESETS = [
  { id: "stream_benchmark", label: "Stream benchmark", text: "Replay test sessions through Kafka into engine workers and measure throughput, latency and detection quality." },
  { id: "offline_subset", label: "Offline experiments", text: "Re-run part of the offline grid (detection quality, parser ablation, thresholds) and regenerate the tables and figures." },
  { id: "offline_report", label: "Rebuild report", text: "Regenerate tables and figures from the stored offline results. Takes a few seconds." },
] as const;

type Preset = (typeof PRESETS)[number]["id"];
const DATASETS = ["hdfs", "bgl", "thunderbird"], PARSERS = ["raw", "regex", "drain"], MODELS = ["iforest", "pca", "ae"];

function StreamSummary({ path }: { path: string }) {
  const s = usePoll(async () => JSON.parse(await api.fileText(path)) as Record<string, any>, 60000, [path]); // eslint-disable-line @typescript-eslint/no-explicit-any
  const d = s.data;
  if (!d) return null;
  const lat = d.latency_ms?.event_to_alert;
  return (
    <DefList items={[
      ["Sessions scored", `${fmtInt(d.sessions_scored)} of ${fmtInt(d.sessions_expected)}`],
      ["Consumer rate", `${fmtInt(d.consumer_rate_eps)} events per second`],
      ["Event to alert", lat ? `p50 ${fmtMs(lat.p50)}, p95 ${fmtMs(lat.p95)}, p99 ${fmtMs(lat.p99)}` : "n/a"],
      ["Live F1", d.stream_alert_any_time ? d.stream_alert_any_time.f1.toFixed(3) : "n/a"],
      ["Final full-session F1", d.final_full_session ? d.final_full_session.f1.toFixed(3) : "n/a"],
      ["Backlog after last send", `${d.drain_seconds_after_last_send?.toFixed(1)} s`],
    ]} />
  );
}

function ArtifactView({ a }: { a: Artifact }) {
  const [text, setText] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const isText = /\.(md|csv|json|txt)$/.test(a.path);
  useEffect(() => {
    if (open && isText && text === null) api.fileText(a.path).then((t) => setText(t.slice(0, 20000))).catch(() => setText("Could not load this file."));
  }, [open, isText, text, a.path]);
  return (
    <TableRow>
      <TableCell className="num">{a.path.replace(/^results\//, "")}</TableCell><TableCell>{fmtBytes(a.size)}</TableCell>
      <TableCell>
        {isText && <Button size="sm" kind="ghost" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Preview"}</Button>}
        <Button size="sm" kind="ghost" renderIcon={Download} iconDescription="Download" href={api.fileUrl(a.path)} target="_blank">Open</Button>
        {open && text !== null && <pre className="log num" style={{ marginTop: ".5rem" }}>{text}</pre>}
      </TableCell>
    </TableRow>
  );
}

export default function Experiments() {
  const [preset, setPreset] = useState<Preset>("stream_benchmark");
  const [rate, setRate] = useState(5000);
  const [sessions, setSessions] = useState(5000);
  const [workers, setWorkers] = useState(1);
  const [ds, setDs] = useState<string[]>(["bgl"]);
  const [ps, setPs] = useState<string[]>(["regex", "drain"]);
  const [ms, setMs] = useState<string[]>(["iforest", "pca"]);
  const [seeds, setSeeds] = useState(1);
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const runs = usePoll(() => api.runs("experiment"), 2000);
  const chosen = runs.data?.items.find((r) => r.id === sel) ?? null;
  const files = usePoll(() => (chosen && chosen.status !== "running" ? api.experimentFiles(chosen.id) : Promise.resolve({ items: [] })), 5000, [chosen?.id, chosen?.status]);
  const log = usePoll(() => (chosen ? api.runLog(chosen.id, 40) : Promise.resolve(null)), 2000, [chosen?.id]);

  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const run = async () => {
    setErr(null);
    try {
      const body: Record<string, unknown> = { preset };
      if (preset === "stream_benchmark") Object.assign(body, { rate, sessions, workers });
      if (preset === "offline_subset") Object.assign(body, { datasets: ds, parsers: ps, models: ms, seeds: Array.from({ length: seeds }, (_, i) => i) });
      const r = await api.runExperiment(body);
      setSel(r.id); runs.reload();
    } catch (e) { setErr((e as Error).message); }
  };
  const items = files.data?.items ?? [];
  const images = items.filter((f) => f.path.endsWith(".png"));
  const others = items.filter((f) => !f.path.endsWith(".png"));
  const summary = others.find((f) => f.path.endsWith("summary.json"));
  const invalid = preset === "offline_subset" && (ds.length === 0 || ps.length === 0 || ms.length === 0);

  return (
    <Page title="Experiments" lead="Run the measurements behind the paper and download the tables and figures they produce.">
      <Notice error={err ?? runs.error} />
      <div className="tabs-inline" role="tablist" aria-label="Experiment type">
        {PRESETS.map((p) => (
          <Button key={p.id} role="tab" aria-selected={preset === p.id} size="sm" kind={preset === p.id ? "primary" : "tertiary"} onClick={() => setPreset(p.id)}>{p.label}</Button>
        ))}
      </div>

      <div className="panel">
        <p className="muted" style={{ marginBottom: "1rem", maxWidth: "70ch" }}>{PRESETS.find((p) => p.id === preset)!.text}</p>
        {preset === "stream_benchmark" && (
          <div className="row">
            <NumberInput id="e-rate" label="Events per second (0 = burst)" min={0} max={200000} step={1000} value={rate} onChange={(_e, { value }) => setRate(Number(value))} />
            <NumberInput id="e-sess" label="Sessions" min={100} max={172519} step={1000} value={sessions} onChange={(_e, { value }) => setSessions(Number(value))} />
            <Select id="e-workers" labelText="Engine workers" value={String(workers)} onChange={(e) => setWorkers(Number(e.target.value))}>
              {[1, 2, 4].map((n) => <SelectItem key={n} value={String(n)} text={String(n)} />)}
            </Select>
          </div>
        )}
        {preset === "offline_subset" && (
          <div className="row" style={{ alignItems: "flex-start" }}>
            <fieldset><legend className="muted">Datasets</legend>{DATASETS.map((v) => <Checkbox key={v} id={`d-${v}`} labelText={v} checked={ds.includes(v)} onChange={() => toggle(ds, setDs, v)} />)}</fieldset>
            <fieldset><legend className="muted">Parsers</legend>{PARSERS.map((v) => <Checkbox key={v} id={`p-${v}`} labelText={v} checked={ps.includes(v)} onChange={() => toggle(ps, setPs, v)} />)}</fieldset>
            <fieldset><legend className="muted">Detectors</legend>{MODELS.map((v) => <Checkbox key={v} id={`m-${v}`} labelText={v} checked={ms.includes(v)} onChange={() => toggle(ms, setMs, v)} />)}</fieldset>
            <NumberInput id="e-seeds" label="Seeds per cell" min={1} max={5} value={seeds} onChange={(_e, { value }) => setSeeds(Number(value))} helperText="HDFS cells take minutes" />
          </div>
        )}
        <div className="actions"><Button onClick={run} disabled={invalid}>Run</Button></div>
        {invalid && <p className="muted" style={{ marginTop: ".5rem" }}>Pick at least one dataset, parser and detector.</p>}
      </div>

      <div className="split">
        <div className="panel">
          <h2>Runs</h2>
          {runs.loading ? <SkeletonText paragraph lineCount={3} /> : (runs.data?.items.length ?? 0) === 0 ? (
            <Empty title="No experiments yet" body="Choose a type above and press Run. Progress and results show up here." />
          ) : (
            <Table size="sm" aria-label="Experiment runs">
              <TableHead><TableRow><TableHeader>Run</TableHeader><TableHeader>Status</TableHeader><TableHeader>Started</TableHeader></TableRow></TableHead>
              <TableBody>
                {runs.data!.items.slice(0, 12).map((r) => (
                  <TableRow key={r.id} onClick={() => setSel(r.id)} style={{ cursor: "pointer", outline: r.id === sel ? "2px solid var(--cds-focus)" : undefined, outlineOffset: -2 }}>
                    <TableCell className="num">{r.id.replace("exp-", "")}</TableCell><TableCell><RunStatusTag status={r.status} /></TableCell><TableCell>{ago(r.created_ns)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <aside className="panel" aria-label="Run detail">
          {!chosen ? <p className="muted">Select a run to see its progress and results.</p> : (
            <>
              <h2>{chosen.id.replace("exp-", "")}</h2>
              <p><RunStatusTag status={chosen.status} /></p>
              {chosen.status === "running" && <p className="muted">Running. This page updates on its own.</p>}
              {chosen.status === "failed" && <p className="muted">The run failed. The log below shows why.</p>}
              {summary && <StreamSummary path={summary.path} />}
              <h3>Log</h3>
              <pre className="log num" aria-label="Run log">{(log.data?.lines ?? []).join("\n") || "No output yet."}</pre>
            </>
          )}
        </aside>
      </div>

      {chosen && chosen.status !== "running" && (
        <div className="panel">
          <h2>Results</h2>
          {items.length === 0 ? <p className="muted">No result files found for this run.</p> : (
            <>
              {images.length > 0 && <div className="thumbs" style={{ marginBottom: "1rem" }}>{images.map((f) => <a key={f.path} href={api.fileUrl(f.path)} target="_blank" rel="noreferrer"><img src={api.fileUrl(f.path)} alt={f.path.split("/").pop() ?? "figure"} /></a>)}</div>}
              <Table size="sm" aria-label="Result files">
                <TableHead><TableRow><TableHeader>File</TableHeader><TableHeader>Size</TableHeader><TableHeader>View</TableHeader></TableRow></TableHead>
                <TableBody>{others.map((f) => <ArtifactView key={f.path} a={f} />)}</TableBody>
              </Table>
            </>
          )}
        </div>
      )}
    </Page>
  );
}
