import {
  Content, GlobalTheme, Header, HeaderGlobalAction, HeaderGlobalBar, HeaderMenuItem, HeaderName, HeaderNavigation, Tag,
} from "@carbon/react";
import { Asleep, Light } from "@carbon/icons-react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { RunStatusTag } from "./components/common";
import { usePoll } from "./hooks";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import Experiments from "./pages/Experiments";
import Models from "./pages/Models";
import Playground from "./pages/Playground";
import Source from "./pages/Source";
import { useTheme } from "./theme";

// operator: live monitoring, alert triage, and starting/stopping its own live ingestion (that's
// an operator action, not a testing one) -- no training, no testing, no anomaly injection. The
// API refuses those routes too when run with LOGSENTINEL_APP_MODE=operator, this is not just a
// hidden nav.
// admin: the full testing/training suite on top, for whoever is standing the system up or
// evaluating models -- a separate build (admin.html) kept out of the operator deployment.
// Playground is admin-only too: it's a personal test tool (fake traffic + fake anomalies), never
// reachable from the operator build.
const VARIANTS = {
  operator: ["/", "/alerts", "/source"],
  admin: ["/", "/alerts", "/source", "/models", "/experiments", "/playground"],
} as const;

export type AppVariant = keyof typeof VARIANTS;

const pages = (variant: AppVariant) => ({
  "/": { label: "Dashboard", element: <Dashboard variant={variant} /> },
  "/alerts": { label: "Alerts", element: <Alerts /> },
  "/source": { label: "Source", element: <Source variant={variant} /> },
  "/models": { label: "Models", element: <Models /> },
  "/experiments": { label: "Experiments", element: <Experiments /> },
  "/playground": { label: "Playground", element: <Playground /> },
});

function SourceBadge() {
  const { data } = usePoll(api.currentSource, 3000);
  const run = data?.run;
  if (!run) return <Tag type="gray" size="sm">No source</Tag>;
  const p = data?.progress;
  return (
    <>
      <RunStatusTag status={run.status} />
      {run.status === "running" && p?.phase && p.phase !== run.status && <span className="muted" style={{ marginLeft: ".5rem", fontSize: ".75rem" }}>{p.phase}</span>}
    </>
  );
}

export default function App({ variant }: { variant: AppVariant }) {
  const { theme, toggle } = useTheme();
  const { pathname } = useLocation();
  const paths = VARIANTS[variant];
  const PAGES = pages(variant);
  return (
    <GlobalTheme theme={theme}>
      <Header aria-label="LogSentinel">
        <HeaderName href="#/" prefix="">LogSentinel{variant === "admin" ? " Admin" : ""}</HeaderName>
        <HeaderNavigation aria-label="Sections">
          {paths.map((to) => (
            <HeaderMenuItem key={to} href={`#${to}`} isCurrentPage={to === "/" ? pathname === "/" : pathname.startsWith(to)}>
              {PAGES[to].label}
            </HeaderMenuItem>
          ))}
        </HeaderNavigation>
        <HeaderGlobalBar>
          <div className="header-status"><SourceBadge /></div>
          <HeaderGlobalAction
            aria-label={theme === "g100" ? "Switch to light theme" : "Switch to dark theme"} tooltipAlignment="end" onClick={toggle}
          >
            {theme === "g100" ? <Light size={20} /> : <Asleep size={20} />}
          </HeaderGlobalAction>
        </HeaderGlobalBar>
      </Header>
      <Content>
        <Routes>
          {paths.map((to) => <Route key={to} path={to} element={PAGES[to].element} />)}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Content>
    </GlobalTheme>
  );
}
