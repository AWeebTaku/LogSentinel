"""One pass over a sessions file -> cached sparse event-count matrices.

For every session we count (a) masked messages, interned into a vocabulary, and (b) raw message
content hashed into fixed buckets. Parser arms (parsing/parsers.py) are column maps over (a);
the raw arm uses (b) directly. Cached in data/features/<dataset>.<mode>.*
"""
import gzip
import json
from array import array
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from zlib import crc32

import numpy as np
import scipy.sparse as sp

from ..common.config import ROOT, load_config
from ..data.sessions import read_sessions
from ..parsing.content import content, mask

RAW_BUCKETS = 4096


@dataclass
class CountFeatures:
    ids: list[str]
    labels: np.ndarray        # 0/1 per session
    splits: np.ndarray        # 'train' | 'val' | 'test'
    vocab: list[str]          # masked message per column of X_mask
    X_mask: sp.csr_matrix
    X_raw: sp.csr_matrix

    def rows(self, split: str) -> np.ndarray:
        return np.flatnonzero(self.splits == split)


def _csr(ptr, idx, dat, ncols) -> sp.csr_matrix:
    return sp.csr_matrix(
        (np.frombuffer(dat, dtype=np.float32), np.frombuffer(idx, dtype=np.int32), np.array(ptr)),
        shape=(len(ptr) - 1, ncols),
    )


def featurize(path: Path, dataset: str) -> CountFeatures:
    vocab: dict[str, int] = {}
    seen: dict[str, tuple[int, int]] = {}  # raw content -> (mask id, raw bucket)
    ids, labels, splits = [], [], []
    m_ptr, m_idx, m_dat = [0], array("i"), array("f")
    r_ptr, r_idx, r_dat = [0], array("i"), array("f")
    for n, s in enumerate(read_sessions(path)):
        mc, rc = Counter(), Counter()
        for line in s.lines:
            c = content(line, dataset)
            hit = seen.get(c)
            if hit is None:
                m = mask(c)
                mid = vocab.setdefault(m, len(vocab))
                hit = seen[c] = (mid, crc32(c.encode("utf-8", "ignore")) % RAW_BUCKETS)
                if len(seen) > 3_000_000:  # bound memory; ids stay stable through `vocab`
                    seen.clear()
            mc[hit[0]] += 1
            rc[hit[1]] += 1
        for cnt, idx, dat, ptr in ((mc, m_idx, m_dat, m_ptr), (rc, r_idx, r_dat, r_ptr)):
            idx.extend(cnt.keys())
            dat.extend(cnt.values())
            ptr.append(len(idx))
        ids.append(s.id)
        labels.append(s.label)
        splits.append(s.split)
        if n and n % 100_000 == 0:
            print(f"  {dataset}: {n:,} sessions, vocab={len(vocab):,}", flush=True)
    return CountFeatures(
        ids, np.array(labels, dtype=np.int8), np.array(splits), list(vocab),
        _csr(m_ptr, m_idx, m_dat, len(vocab)), _csr(r_ptr, r_idx, r_dat, RAW_BUCKETS),
    )


def _dir() -> Path:
    d = ROOT / load_config()["processed_dir"] / ".." / "features"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def load_or_build(dataset: str, mode: str) -> CountFeatures:
    base = _dir() / f"{dataset}.{mode}"
    meta = base.parent / f"{base.name}.meta.json.gz"
    if meta.exists():
        with gzip.open(meta, "rt") as f:
            m = json.load(f)
        return CountFeatures(
            m["ids"], np.array(m["labels"], dtype=np.int8), np.array(m["splits"]), m["vocab"],
            sp.load_npz(f"{base}.mask.npz"), sp.load_npz(f"{base}.raw.npz"),
        )
    src = ROOT / load_config()["processed_dir"] / f"{dataset}.{mode}.sessions.jsonl.gz"
    print(f"featurizing {src.name} ...", flush=True)
    cf = featurize(src, dataset)
    sp.save_npz(f"{base}.mask.npz", cf.X_mask)
    sp.save_npz(f"{base}.raw.npz", cf.X_raw)
    with gzip.open(meta, "wt") as f:
        json.dump({"ids": cf.ids, "labels": cf.labels.tolist(), "splits": cf.splits.tolist(),
                   "vocab": cf.vocab}, f)
    return cf
