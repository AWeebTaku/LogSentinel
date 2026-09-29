"""Per-session line sequences: feature column and log-time offset of every line, in arrival order.

Needed to simulate online scoring offline (score after every prefix of a session) without Kafka.
Cached per bundle because the column of a line depends on the bundle's parser runtime.
"""
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..common.config import ROOT, load_config
from ..data.sessions import read_sessions
from ..models.bundle import Bundle, Scorer
from ..stream.wire import hdfs_log_time


@dataclass
class Seq:
    id: str
    label: int
    split: str
    cols: np.ndarray   # int16 feature column per line
    dt: np.ndarray     # int32 seconds since the session's first line (HDFS log time)


def from_sessions(sessions, scorer: Scorer) -> list[Seq]:
    out = []
    for s in sessions:
        cols = np.fromiter((scorer.line_col(line) for line in s.lines), np.int16, len(s.lines))
        t = [hdfs_log_time(line) for line in s.lines]
        out.append(Seq(s.id, s.label, s.split, cols, np.array(t, np.int32) - t[0]))
    return out


def build(bundle_dir: Path, mode: str = "chronological") -> list[Seq]:
    cache = Path(bundle_dir) / f"sequences.{mode}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    src = ROOT / load_config()["processed_dir"] / f"hdfs.{mode}.sessions.jsonl.gz"
    out = from_sessions(read_sessions(src), Scorer(Bundle.load(bundle_dir)))
    cache.write_bytes(pickle.dumps(out))
    return out
