import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeName = "white" | "g100";
const KEY = "logsentinel.theme";

function initial(): ThemeName {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "white" || saved === "g100") return saved;
  } catch {
    /* storage blocked: fall through to the system preference */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "white" : "g100";
}

const Ctx = createContext<{ theme: ThemeName; toggle: () => void }>({ theme: "g100", toggle: () => {} });
export const useTheme = () => useContext(Ctx);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeName>(initial);
  useEffect(() => {
    const root = document.documentElement;          // Carbon's token zones are the .cds--<theme> classes
    root.classList.remove("cds--white", "cds--g100");
    root.classList.add(`cds--${theme}`);
    root.dataset.carbonTheme = theme;
    try { localStorage.setItem(KEY, theme); } catch { /* ignore */ }
  }, [theme]);
  const value = useMemo(() => ({ theme, toggle: () => setTheme((t) => (t === "g100" ? "white" : "g100")) }), [theme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
