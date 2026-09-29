"""Parse the broker's JVM GC and safepoint log (-Xlog with time decorations) into pauses on the epoch clock."""
import re
from datetime import datetime

_TS = re.compile(r"^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d{4})\]")
_GC = re.compile(r"Pause (\w+).*?(\d+(?:\.\d+)?)ms\s*$")
_SP = re.compile(r"Safepoint \"(\w+)\".*Total: (\d+) ns")


def _epoch(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()


def parse_pauses(text: str) -> list[dict]:
    """[{t, ms, kind}] where kind is 'gc:<Young|Full|Remark|Cleanup>' or 'safepoint:<reason>'. t is the log time,
    i.e. when the pause ENDED (JVM logs GC pauses on completion)."""
    out = []
    for line in text.splitlines():
        m = _TS.match(line)
        if not m:
            continue
        t = _epoch(m.group(1))
        g = _GC.search(line)
        if g:
            out.append({"t": t, "ms": float(g.group(2)), "kind": f"gc:{g.group(1)}"})
            continue
        s = _SP.search(line)
        if s:
            out.append({"t": t, "ms": int(s.group(2)) / 1e6, "kind": f"safepoint:{s.group(1)}"})
    return out
