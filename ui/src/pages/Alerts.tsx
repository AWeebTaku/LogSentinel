import {
  Button, NumberInput, Select, SelectItem, SkeletonText, Table, TableBatchAction, TableBatchActions, TableBody, TableCell,
  TableContainer, TableHead, TableHeader, TableRow, TableSelectAll, TableSelectRow, TableToolbar, TableToolbarContent,
  TextArea, TextInput,
} from "@carbon/react";
import { useState } from "react";
import { api, type Status } from "../api";
import { AlertStatusTag, DefList, Empty, Notice, Page } from "../components/common";
import { ACTION_LABEL, STATUS_LABEL, TRANSITIONS, ago, fmtInt, fmtScore } from "../format";
import { usePoll } from "../hooks";

const BATCH: Status[] = ["acknowledged", "resolved", "false_positive"];

export default function Alerts() {
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [run, setRun] = useState("");
  const [minScore, setMinScore] = useState<number | undefined>(undefined);
  const [limit, setLimit] = useState(50);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [openId, setOpenId] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const filters = { status, kind, run, min_score: minScore, limit };
  const list = usePoll(() => api.alerts(filters), 3000, [status, kind, run, minScore, limit]);
  const stats = usePoll(() => api.stats(run || undefined), 4000, [run]);
  const detail = usePoll(() => (openId ? api.alert(openId) : Promise.resolve(null)), 3000, [openId]);
  const items = list.data?.items ?? [];
  const allSelected = items.length > 0 && items.every((a) => sel.has(a.id));

  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const apply = async (ids: number[], to: Status, text = "") => {
    setErr(null); setMsg(null);
    let ok = 0, skipped = 0;
    for (const id of ids) {
      try { await api.setStatus(id, to, text); ok++; } catch (e) {
        if ((e as { status?: number }).status === 409) skipped++; else { setErr((e as Error).message); break; }
      }
    }
    setMsg(`${STATUS_LABEL[to]}: ${ok} updated${skipped ? `, ${skipped} skipped (not allowed from their current state)` : ""}.`);
    setSel(new Set()); setNote("");
    list.reload(); detail.reload(); stats.reload();
  };

  const d = detail.data;
  const counts = stats.data?.by_status ?? {};
  return (
    <Page title="Alerts" lead="Triage what the engine flagged. Marking false positives feeds back into threshold tuning.">
      <Notice error={list.error ?? err} />
      {msg && <p className="muted" role="status" style={{ marginBottom: ".5rem" }}>{msg}</p>}
      <div className="panel">
        <div className="row">
          <Select id="f-status" labelText="Status" size="sm" value={status} onChange={(e) => { setStatus(e.target.value); setLimit(50); }}>
            <SelectItem value="" text="All" />
            {(Object.keys(STATUS_LABEL) as Status[]).map((s) => <SelectItem key={s} value={s} text={`${STATUS_LABEL[s]} (${fmtInt(counts[s] ?? 0)})`} />)}
          </Select>
          <Select id="f-kind" labelText="Kind" size="sm" value={kind} onChange={(e) => setKind(e.target.value)}>
            <SelectItem value="" text="All" /><SelectItem value="incremental" text="Incremental" />
            <SelectItem value="deadline" text="Deadline check" /><SelectItem value="deadline_eos" text="Deadline at end of stream" />
          </Select>
          <TextInput id="f-run" labelText="Run id" size="sm" placeholder="all runs" value={run} onChange={(e) => setRun(e.target.value.trim())} />
          <NumberInput id="f-score" label="Minimum score" size="sm" step={0.05} min={0} allowEmpty hideSteppers
            value={minScore ?? ""} onChange={(_e, { value }) => setMinScore(value === "" || value === undefined ? undefined : Number(value))} />
        </div>
      </div>

      <div className="split">
        <div>
          {list.loading ? <SkeletonText paragraph lineCount={8} /> : items.length === 0 ? (
            <Empty title="No alerts match" body="Change the filters, or start a source and inject an anomaly burst to see alerts arrive." />
          ) : (
            <TableContainer>
              <TableToolbar aria-label="Alert actions">
                <TableBatchActions
                  shouldShowBatchActions={sel.size > 0} totalSelected={sel.size} onCancel={() => setSel(new Set())}
                  translateWithId={(id: string) => ({ "carbon.table.batch.cancel": "Cancel", "carbon.table.batch.selectAll": "Select all",
                    "carbon.table.batch.items.selected": "alerts selected", "carbon.table.batch.item.selected": "alert selected" }[id] ?? id)}
                >
                  {BATCH.map((s) => (
                    <TableBatchAction key={s} onClick={() => apply([...sel], s)}>{ACTION_LABEL[s]}</TableBatchAction>
                  ))}
                </TableBatchActions>
                <TableToolbarContent><span className="muted" style={{ padding: "0 1rem" }}>Showing {items.length} newest</span></TableToolbarContent>
              </TableToolbar>
              <Table size="sm" aria-label="Alerts">
                <TableHead>
                  <TableRow>
                    <TableSelectAll id="sel-all" name="sel-all" ariaLabel="Select all alerts" checked={allSelected}
                      indeterminate={sel.size > 0 && !allSelected}
                      onSelect={() => setSel(allSelected ? new Set() : new Set(items.map((a) => a.id)))} />
                    <TableHeader>Session</TableHeader><TableHeader>Kind</TableHeader><TableHeader>Score</TableHeader>
                    <TableHeader>Status</TableHeader><TableHeader>Raised</TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((a) => (
                    <TableRow key={a.id} isSelected={sel.has(a.id)} onClick={() => setOpenId(a.id)}
                      style={{ cursor: "pointer", outline: a.id === openId ? "2px solid var(--cds-focus)" : undefined, outlineOffset: -2 }}>
                      <TableSelectRow id={`sel-${a.id}`} name={`sel-${a.id}`} ariaLabel={`Select alert ${a.id}`}
                        checked={sel.has(a.id)} onSelect={() => toggle(a.id)} />
                      <TableCell className="num">{a.session_key}</TableCell><TableCell>{a.kind}</TableCell>
                      <TableCell className="num">{fmtScore(a.score)}</TableCell>
                      <TableCell><AlertStatusTag status={a.status} /></TableCell><TableCell>{ago(a.created_ns)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {items.length >= limit && limit < 500 && (
                <div style={{ padding: ".75rem" }}><Button kind="tertiary" size="sm" onClick={() => setLimit((l) => Math.min(500, l + 50))}>Load 50 more</Button></div>
              )}
            </TableContainer>
          )}
        </div>

        <aside className="panel" aria-label="Alert detail">
          {!openId || !d ? (
            <p className="muted">{openId ? "Loading alert..." : "Select an alert to see its evidence and triage it."}</p>
          ) : (
            <>
              <h2>Alert {d.id}</h2>
              <p><AlertStatusTag status={d.status} /></p>
              <DefList items={[
                ["Session", <span className="num">{d.session_key}</span>], ["Run", <span className="num">{d.run}</span>],
                ["Model", d.model ?? "n/a"], ["Kind", d.kind], ["Score", <span className="num">{fmtScore(d.score)}</span>],
                ["Threshold", <span className="num">{d.threshold == null ? "n/a" : fmtScore(d.threshold)}</span>],
                ["Lines at alert", <span className="num">{fmtInt(d.n_lines)}</span>],
                ["Evidence delay", d.evidence_log_s == null ? "n/a" : `${fmtInt(d.evidence_log_s)} s of log time`],
                ["Sink lag", d.ingest_lag_ms == null ? "n/a" : `${fmtInt(d.ingest_lag_ms)} ms`], ["Raised", ago(d.created_ns)],
              ]} />
              <h3>Triage</h3>
              <TextArea id="note" labelText="Note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="actions">
                {TRANSITIONS[d.status].map((s) => (
                  <Button key={s} size="sm" kind={s === "open" ? "tertiary" : s === "false_positive" ? "secondary" : "primary"}
                    onClick={() => apply([d.id], s, note)}>{ACTION_LABEL[s]}</Button>
                ))}
              </div>
              {d.note && <><h3>Current note</h3><p>{d.note}</p></>}
              <h3>History</h3>
              {d.events.length === 0 ? <p className="muted">No triage actions yet.</p> : (
                <ul>{d.events.map((e, i) => (
                  <li key={i} style={{ marginBottom: ".5rem" }}>
                    <strong>{STATUS_LABEL[e.to_status as Status] ?? e.to_status}</strong> by {e.actor}, {ago(e.ts_ns)}
                    {e.note && <div className="muted">{e.note}</div>}
                  </li>))}</ul>
              )}
            </>
          )}
        </aside>
      </div>
    </Page>
  );
}
