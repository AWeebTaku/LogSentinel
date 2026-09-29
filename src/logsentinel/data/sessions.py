"""Common unit of evaluation: a Session is what the detector scores.

HDFS  -> one block (all lines sharing a blk_ id), labeled per block.
BGL   -> one fixed time window, labeled anomalous if any line in it is.
Downstream code (parsers, models, experiments) only sees Session.
"""
import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Session:
    id: str
    label: int          # 0 normal, 1 anomaly
    ts: float           # first-seen time (epoch seconds) or first line number for HDFS ordering
    lines: list[str]
    split: str = ""     # train | val | test, filled by split_sessions


def write_sessions(sessions: Iterable[Session], path: Path) -> int:
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for s in sessions:
            f.write(json.dumps(asdict(s)) + "\n")
            n += 1
    return n


def read_sessions(path: Path, split: str | None = None) -> Iterator[Session]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            s = Session(**json.loads(line))
            if split is None or s.split == split:
                yield s
