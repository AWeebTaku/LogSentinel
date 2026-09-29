"""HDFS_v1 (LogHub): labels are per BlockId, not per line, so we group lines by block."""
import csv
import re
from collections.abc import Iterator
from pathlib import Path

from .sessions import Session

_BLK = re.compile(r"blk_-?\d+")


def load_block_labels(label_csv: Path) -> dict[str, int]:
    with open(label_csv, newline="") as f:
        return {r["BlockId"]: int(r["Label"] == "Anomaly") for r in csv.DictReader(f)}


def iter_hdfs_sessions(log_path: Path, label_csv: Path, max_lines: int | None = None) -> Iterator[Session]:
    """Yield one Session per labeled block, ordered by first appearance in the log.

    Memory: holds every line of the log in RAM until the end (~2.5 GB for the full 1.5 GB file).
    # ponytail: in-memory grouping, switch to an on-disk sort if the box has < 8 GB free.
    A line may mention several blocks (e.g. replication); it is added to each of them.
    Blocks missing from the label file are dropped (counted by the caller via the returned sessions).
    """
    labels = load_block_labels(label_csv)
    blocks: dict[str, list[str]] = {}
    first_seen: dict[str, int] = {}
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if max_lines and i >= max_lines:
                break
            line = line.rstrip("\n")
            for blk in set(_BLK.findall(line)):
                if blk not in first_seen:
                    first_seen[blk] = i
                    blocks[blk] = []
                blocks[blk].append(line)
    for blk, first in sorted(first_seen.items(), key=lambda kv: kv[1]):
        if blk in labels:
            yield Session(id=blk, label=labels[blk], ts=float(first), lines=blocks[blk])
