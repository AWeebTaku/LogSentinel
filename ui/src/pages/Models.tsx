import {
  Button, Checkbox, NumberInput, Select, SelectItem, SkeletonText, Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
  TextInput,
} from "@carbon/react";
import { useState } from "react";
import { api, type Model } from "../api";
import { Empty, Notice, Page, RunStatusTag } from "../components/common";
import { ago } from "../format";
import { usePoll } from "../hooks";

const num = (x: unknown) => (typeof x === "number" ? (Math.abs(x) < 10 ? x.toFixed(4) : String(Math.round(x))) : x == null ? "n/a" : String(x));

/** Flat, comparable facts about a model: training meta plus any attached metrics. */
function facts(m: Model): Record<string, string> {
  const e = m.meta.early;
  const out: Record<string, string> = {
    Parser: String(m.meta.parser ?? "n/a"), Detector: String(m.meta.model ?? "n/a"),
    "Threshold rule": String(m.meta.threshold_rule ?? "n/a"), Threshold: num(m.meta.threshold),
    Features: num(m.meta.n_features), "Training sessions": num(m.meta.n_train),
    "Age check": e ? `${e.age_s} s, ${e.model}` : "none",
  };
  for (const [k, v] of Object.entries(m.metrics ?? {})) out[`Metric: ${k}`] = num(v);
  return out;
}

export default function Models() {
  const models = usePoll(api.models, 3000);
  const jobs = usePoll(() => api.runs("train"), 2000);
  const [picked, setPicked] = useState<number[]>([]);
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [parser, setParser] = useState("drain");
  const [model, setModel] = useState("pca");
  const [rule, setRule] = useState("tuned_val");
  const [earlyAge, setEarlyAge] = useState(0);
  const [earlyModel, setEarlyModel] = useState("ae");
  const [tname, setTname] = useState("");
  const [logFor, setLogFor] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const log = usePoll(() => (logFor ? api.runLog(logFor) : Promise.resolve(null)), 2000, [logFor]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null); setMsg(null);
    try { await fn(); setMsg(ok); } catch (e) { setErr((e as Error).message); }
    models.reload(); jobs.reload();
  };
  const items = models.data?.items ?? [];
  const cmp = items.filter((m) => picked.includes(m.id));
  const keys = [...new Set(cmp.flatMap((m) => Object.keys(facts(m))))];

  return (
    <Page title="Models" lead="Registered detection bundles. The active model is what new sources and engines load.">
      <Notice error={err ?? models.error} />
      {msg && <p className="muted" role="status" style={{ marginBottom: ".5rem" }}>{msg}</p>}

      <div className="panel">
        <h2>Registry</h2>
        {models.loading ? <SkeletonText paragraph lineCount={4} /> : items.length === 0 ? (
          <Empty title="No models registered" body="Register a trained bundle folder from models/, or train one below. Then activate it." />
        ) : (
          <Table size="sm" aria-label="Model registry">
            <TableHead><TableRow>
              <TableHeader>Compare</TableHeader><TableHeader>Name</TableHeader><TableHeader>Status</TableHeader>
              <TableHeader>Parser</TableHeader><TableHeader>Detector</TableHeader><TableHeader>Age check</TableHeader>
              <TableHeader>Registered</TableHeader><TableHeader>Action</TableHeader>
            </TableRow></TableHead>
            <TableBody>
              {items.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <Checkbox id={`cmp-${m.id}`} labelText={`Compare ${m.name}`} hideLabel checked={picked.includes(m.id)}
                      onChange={(_e, { checked }) => setPicked((p) => (checked ? [...p, m.id].slice(-2) : p.filter((x) => x !== m.id)))} />
                  </TableCell>
                  <TableCell><span className="num">{m.name}</span> v{m.version}</TableCell>
                  <TableCell><RunStatusTag status={m.status} /></TableCell>
                  <TableCell>{String(m.meta.parser ?? "n/a")}</TableCell><TableCell>{String(m.meta.model ?? "n/a")}</TableCell>
                  <TableCell>{m.meta.early ? `${m.meta.early.age_s} s` : "none"}</TableCell><TableCell>{ago(m.created_ns)}</TableCell>
                  <TableCell>
                    <Button size="sm" kind="tertiary" disabled={m.status === "active"}
                      onClick={() => act(() => api.activateModel(m.id), `${m.name} v${m.version} is now active. Restart engines to use it.`)}>
                      Activate
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {cmp.length > 0 && (
        <div className="panel">
          <h2>{cmp.length === 1 ? "Model details" : "Compare models"}</h2>
          <Table size="sm" aria-label="Model comparison">
            <TableHead><TableRow><TableHeader>Property</TableHeader>{cmp.map((m) => <TableHeader key={m.id}>{m.name} v{m.version}</TableHeader>)}</TableRow></TableHead>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k}><TableCell>{k}</TableCell>{cmp.map((m) => <TableCell key={m.id} className="num">{facts(m)[k] ?? "n/a"}</TableCell>)}</TableRow>
              ))}
            </TableBody>
          </Table>
          {cmp.length === 1 && <p className="muted" style={{ marginTop: ".5rem" }}>Tick a second model to compare side by side.</p>}
        </div>
      )}

      <div className="grid-2">
        <div className="panel">
          <h2>Register an existing bundle</h2>
          <div className="row">
            <TextInput id="reg-path" labelText="Bundle folder" placeholder="models/hdfs-drain-pca" value={path} onChange={(e) => setPath(e.target.value.trim())}
              helperText="Must be inside the project's models/ folder" />
            <TextInput id="reg-name" labelText="Name (optional)" value={name} onChange={(e) => setName(e.target.value.trim())} />
          </div>
          <div className="actions"><Button size="md" disabled={!path} onClick={() => act(() => api.registerModel(path, name), "Registered.")}>Register</Button></div>
        </div>

        <div className="panel">
          <h2>Train a new model</h2>
          <div className="row">
            <Select id="t-parser" labelText="Parser" value={parser} onChange={(e) => setParser(e.target.value)}>
              <SelectItem value="drain" text="Drain templates" /><SelectItem value="regex" text="Regex masking" />
            </Select>
            <Select id="t-model" labelText="Detector" value={model} onChange={(e) => setModel(e.target.value)}>
              <SelectItem value="pca" text="PCA residual" /><SelectItem value="iforest" text="Isolation Forest" /><SelectItem value="ae" text="Autoencoder" />
            </Select>
            <Select id="t-rule" labelText="Threshold rule" value={rule} onChange={(e) => setRule(e.target.value)}>
              <SelectItem value="tuned_val" text="Tuned on validation (uses labels)" /><SelectItem value="percentile99" text="99th percentile of normal" />
              <SelectItem value="three_sigma" text="Mean plus 3 sigma of normal" />
            </Select>
          </div>
          <div className="row" style={{ marginTop: "1rem" }}>
            <NumberInput id="t-age" label="Age check (log seconds, 0 = off)" min={0} max={3600} step={10} value={earlyAge}
              onChange={(_e, { value }) => setEarlyAge(Number(value))} helperText="30 catches short incomplete sessions" />
            <Select id="t-emodel" labelText="Age check detector" value={earlyModel} disabled={earlyAge === 0} onChange={(e) => setEarlyModel(e.target.value)}>
              <SelectItem value="ae" text="Autoencoder" /><SelectItem value="pca" text="PCA residual" /><SelectItem value="iforest" text="Isolation Forest" />
            </Select>
            <TextInput id="t-name" labelText="Name (optional)" value={tname} onChange={(e) => setTname(e.target.value.trim())} />
          </div>
          <div className="actions">
            <Button size="md" onClick={() => act(() => api.trainModel({ parser, model, threshold: rule, early_age: earlyAge, early_model: earlyModel, name: tname || undefined }), "Training started. It registers automatically when done.")}>Start training</Button>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Training jobs</h2>
        {(jobs.data?.items.length ?? 0) === 0 ? <p className="muted">No training jobs yet.</p> : (
          <Table size="sm" aria-label="Training jobs">
            <TableHead><TableRow><TableHeader>Job</TableHeader><TableHeader>Model</TableHeader><TableHeader>Status</TableHeader><TableHeader>Started</TableHeader><TableHeader>Log</TableHeader></TableRow></TableHead>
            <TableBody>
              {jobs.data!.items.slice(0, 8).map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="num">{r.id}</TableCell><TableCell className="num">{String((r.params as { name?: string }).name ?? "")}</TableCell>
                  <TableCell><RunStatusTag status={r.status} /></TableCell><TableCell>{ago(r.created_ns)}</TableCell>
                  <TableCell><Button size="sm" kind="ghost" onClick={() => setLogFor(logFor === r.id ? null : r.id)}>{logFor === r.id ? "Hide log" : "Show log"}</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {logFor && <pre className="log num" aria-label="Training log">{(log.data?.lines ?? []).join("\n") || "No output yet."}</pre>}
      </div>
    </Page>
  );
}
