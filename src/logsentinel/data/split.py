import random
from collections.abc import Iterable

from .sessions import Session


def split_sessions(
    sessions: Iterable[Session], train: float = 0.6, val: float = 0.1,
    mode: str = "chronological", seed: int = 42,
) -> list[Session]:
    """Assign train/val/test. Anomalous sessions that land in train are dropped (unsupervised setting).

    chronological: input order (both loaders yield time order); first `train` fraction -> train,
                   next `val` -> val, rest -> test. No future leakage, but anomaly rate can drift
                   across splits (HDFS_v1 is front-loaded).
    random:        seeded shuffle before cutting. Keeps the natural anomaly rate in val/test; use as
                   a robustness check, not as the headline number (mixes past and future).
    """
    s = list(sessions)
    n = len(s)
    order = list(range(n))
    if mode == "random":
        random.Random(seed).shuffle(order)
    elif mode != "chronological":
        raise ValueError(f"unknown split mode {mode!r}")
    a, b = int(n * train), int(n * (train + val))
    out = []
    for rank, i in enumerate(order):
        x = s[i]
        if rank < a:
            if x.label:
                continue
            x.split = "train"
        elif rank < b:
            x.split = "val"
        else:
            x.split = "test"
        out.append(x)
    out.sort(key=lambda x: x.ts)  # keep time order in the output file either way
    return out
