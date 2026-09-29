"""BGL / Thunderbird (LogHub): line-level labels, first token '-' = normal, else alert category.

Line format (both datasets): `<label> <epoch_sec> <date> <node> ... <message>`.
Lines are bucketed into fixed time windows; a window is anomalous if it holds any anomalous line.
"""
from collections.abc import Iterator
from pathlib import Path

from .sessions import Session


def iter_window_sessions(
    log_path: Path, window_seconds: int = 3600, min_lines: int = 1, max_lines: int | None = None
) -> Iterator[Session]:
    cur_win: int | None = None
    lines: list[str] = []
    label = 0
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if max_lines and i >= max_lines:
                break
            parts = line.rstrip("\n").split(" ", 2)
            if len(parts) < 3 or not parts[1].isdigit():
                continue  # malformed line
            win = int(parts[1]) // window_seconds
            if cur_win is not None and win != cur_win:
                if len(lines) >= min_lines:
                    yield Session(id=f"w{cur_win}", label=label, ts=float(cur_win * window_seconds), lines=lines)
                lines, label = [], 0
            cur_win = win
            lines.append(line.rstrip("\n"))
            label |= parts[0] != "-"
    if lines and len(lines) >= min_lines:
        yield Session(id=f"w{cur_win}", label=label, ts=float(cur_win * window_seconds), lines=lines)
