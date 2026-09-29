import { Button, InlineNotification, Tag } from "@carbon/react";
import type { ReactNode } from "react";
import type { Status } from "../api";
import { STATUS_LABEL } from "../format";

export function Page({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <section className="page">
      <header className="page-head">
        <h1>{title}</h1>
        {lead && <p>{lead}</p>}
      </header>
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function Notice({ error, title = "Something went wrong" }: { error?: Error | string | null; title?: string }) {
  if (!error) return null;
  return (
    <InlineNotification
      kind="error" lowContrast hideCloseButton title={title}
      subtitle={typeof error === "string" ? error : error.message}
    />
  );
}

export function Info({ title, children }: { title: string; children?: ReactNode }) {
  return <InlineNotification kind="info" lowContrast hideCloseButton title={title} subtitle={children as string} />;
}

export function Empty({ title, body, action }: { title: string; body: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{body}</p>
      {action && <Button kind="primary" size="md" onClick={action.onClick}>{action.label}</Button>}
    </div>
  );
}

const ALERT_TAG: Record<Status, "red" | "blue" | "green" | "gray"> = {
  open: "red", acknowledged: "blue", resolved: "green", false_positive: "gray",
};
export const AlertStatusTag = ({ status }: { status: Status }) => (
  <Tag type={ALERT_TAG[status]} size="sm">{STATUS_LABEL[status]}</Tag>
);

const RUN_TAG: Record<string, "blue" | "green" | "red" | "gray" | "magenta" | "cool-gray"> = {
  running: "blue", succeeded: "green", finished: "green", failed: "red", stopped: "gray", lost: "magenta",
  registered: "cool-gray", active: "green", archived: "gray",
};
export const RunStatusTag = ({ status }: { status: string }) => (
  <Tag type={RUN_TAG[status] ?? "gray"} size="sm">{status}</Tag>
);

export function DefList({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>
      ))}
    </dl>
  );
}
