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
import Source from "./pages/Source";
import { useTheme } from "./theme";

const LINKS = [
  ["/", "Dashboard"], ["/alerts", "Alerts"], ["/source", "Source"], ["/models", "Models"], ["/experiments", "Experiments"],
] as const;

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

export default function App() {
  const { theme, toggle } = useTheme();
  const { pathname } = useLocation();
  return (
    <GlobalTheme theme={theme}>
      <Header aria-label="LogSentinel">
        <HeaderName href="#/" prefix="">LogSentinel</HeaderName>
        <HeaderNavigation aria-label="Sections">
          {LINKS.map(([to, label]) => (
            <HeaderMenuItem key={to} href={`#${to}`} isCurrentPage={to === "/" ? pathname === "/" : pathname.startsWith(to)}>
              {label}
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
          <Route path="/" element={<Dashboard />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/source" element={<Source />} />
          <Route path="/models" element={<Models />} />
          <Route path="/experiments" element={<Experiments />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Content>
    </GlobalTheme>
  );
}
