import { useCallback, useEffect, useRef, useState } from "react";

/** Poll `fn` every `ms` (paused while the tab is hidden). Keeps the last good data if a poll fails. */
export function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const tick = useRef<() => void>(() => {});

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      if (!document.hidden) {
        try {
          const d = await fnRef.current();
          if (alive) { setData(d); setError(undefined); }
        } catch (e) {
          if (alive) setError(e as Error);
        }
        if (alive) setLoading(false);
      }
      if (alive) timer = setTimeout(run, ms);
    };
    tick.current = () => { if (timer) clearTimeout(timer); void run(); };
    setLoading(true);
    void run();
    return () => { alive = false; if (timer) clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);

  const reload = useCallback(() => tick.current(), []);
  return { data, error, loading, reload };
}
