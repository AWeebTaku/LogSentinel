import { Button, NumberInput } from "@carbon/react";
import { Play, Stop } from "@carbon/icons-react";
import { useState } from "react";
import { api } from "../api";
import { DefList, Info, Notice, Page, RunStatusTag } from "../components/common";
import { ago, fmtInt } from "../format";
import { usePoll } from "../hooks";

export default function Playground() {
  const [rate, setRate] = useState(2000);
  const [everyMin, setEveryMin] = useState(60);
  const [everyMax, setEveryMax] = useState(180);
  const [countMin, setCountMin] = useState(10);
  const [countMax, setCountMax] = useState(50);
  const [count, setCount] = useState(20);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const cur = usePoll(api.currentPlayground, 1000);
  const run = cur.data?.run ?? null;
  const prog = cur.data?.progress;
  const running = run?.status === "running";

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null); setMsg(null); setBusy(true);
    try { await fn(); setMsg(ok); } catch (e) { setErr((e as Error).message); }
    setBusy(false); cur.reload();
  };

  return (
    <Page title="Playground" lead="Personal test tool: traffic plus random anomaly bursts, to exercise detect -> triage -> retrain.">
      <Notice error={err ?? cur.error} />
      {msg && <p className="muted" role="status" style={{ marginBottom: ".5rem" }}>{msg}</p>}
      <Info title="Not production">
        There is no real log-generating system behind this project, so this replays the bundled
        HDFS test dataset for ordinary traffic and fires random anomaly bursts on a timer. It only
        produces traffic -- start an engine separately (Source page, "Watch an external feed") to
        actually detect and alert on what this sends. Run it against staging only.
      </Info>

      <div className="grid-2">
        <div className="panel">
          <h2>Start</h2>
          <div className="row">
            <NumberInput id="pg-rate" label="Events per second" min={10} max={200000} step={500} value={rate}
              disabled={running} onChange={(_e, { value }) => setRate(Number(value))} />
          </div>
          <div className="row" style={{ marginTop: "1rem" }}>
            <NumberInput id="pg-every-min" label="Anomaly burst every, min (s)" min={5} max={3600} step={5}
              value={everyMin} disabled={running} onChange={(_e, { value }) => setEveryMin(Number(value))} />
            <NumberInput id="pg-every-max" label="...max (s)" min={5} max={3600} step={5}
              value={everyMax} disabled={running} onChange={(_e, { value }) => setEveryMax(Number(value))} />
          </div>
          <div className="row" style={{ marginTop: "1rem" }}>
            <NumberInput id="pg-count-min" label="Burst size, min sessions" min={1} max={2000} step={5}
              value={countMin} disabled={running} onChange={(_e, { value }) => setCountMin(Number(value))} />
            <NumberInput id="pg-count-max" label="...max sessions" min={1} max={2000} step={5}
              value={countMax} disabled={running} onChange={(_e, { value }) => setCountMax(Number(value))} />
          </div>
          <div className="actions">
            <Button renderIcon={Play} disabled={running || busy}
              onClick={() => act(() => api.startPlayground({
                rate, anomaly_every_min: everyMin, anomaly_every_max: everyMax,
                anomaly_count_min: countMin, anomaly_count_max: countMax,
              }), "Playground started.")}>
              Start
            </Button>
            <Button kind="danger--tertiary" renderIcon={Stop} disabled={!running || busy}
              onClick={() => run && act(() => api.stopPlayground(run.id), "Stop requested.")}>
              Stop
            </Button>
          </div>
        </div>

        <div className="panel">
          <h2>Current run</h2>
          {!run ? <p className="muted">Not running. Start one on the left.</p> : (
            <>
              <DefList items={[
                ["Run", <span className="num">{run.id}</span>], ["Status", <RunStatusTag status={run.status} />],
                ["Started", ago(run.created_ns)], ["Events sent", fmtInt(prog?.sent)],
                ["Anomaly bursts (auto)", fmtInt(prog?.anomaly_bursts)],
              ]} />
              <p className="muted" style={{ marginTop: "1rem" }}>
                {running ? "Producing continuously. No fixed end -- stop it when you're done." : "Not running."}
              </p>
            </>
          )}
        </div>
      </div>

      {running && (
        <div className="panel">
          <h2>Inject now</h2>
          <p className="muted" style={{ marginBottom: "1rem", maxWidth: "70ch" }}>
            Fire an anomaly burst immediately, on top of the random timer above.
          </p>
          <div className="row">
            <NumberInput id="pg-inject-count" label="Anomalous sessions" min={1} max={2000} step={5} value={count}
              onChange={(_e, { value }) => setCount(Number(value))} />
            <Button disabled={busy || !prog?.watermark}
              onClick={() => run && act(() => api.injectPlaygroundNow(run.id, count), `Injected ${count} anomalous sessions.`)}>
              Inject anomaly burst
            </Button>
          </div>
          {!prog?.watermark && <p className="muted" style={{ marginTop: ".5rem" }}>Available once traffic starts flowing.</p>}
        </div>
      )}
    </Page>
  );
}
