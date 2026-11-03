import "@carbon/charts-react/styles.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-sans/300.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import { Content, GlobalTheme, Header, HeaderGlobalAction, HeaderGlobalBar, HeaderName } from "@carbon/react";
import { Asleep, Light } from "@carbon/icons-react";
import React from "react";
import ReactDOM from "react-dom/client";
import Playground from "./pages/Playground";
import "./styles.scss";
import { ThemeProvider, useTheme } from "./theme";

// Its own standalone portal, not part of the admin/operator app: one page, no nav, no router --
// see README.md, "Setting up a real log source" / the Playground section for what this is for.
function Shell() {
  const { theme, toggle } = useTheme();
  return (
    <GlobalTheme theme={theme}>
      <Header aria-label="LogSentinel Playground">
        <HeaderName prefix="">LogSentinel Playground</HeaderName>
        <HeaderGlobalBar>
          <HeaderGlobalAction
            aria-label={theme === "g100" ? "Switch to light theme" : "Switch to dark theme"} tooltipAlignment="end" onClick={toggle}
          >
            {theme === "g100" ? <Light size={20} /> : <Asleep size={20} />}
          </HeaderGlobalAction>
        </HeaderGlobalBar>
      </Header>
      <Content><Playground /></Content>
    </GlobalTheme>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <Shell />
    </ThemeProvider>
  </React.StrictMode>,
);
