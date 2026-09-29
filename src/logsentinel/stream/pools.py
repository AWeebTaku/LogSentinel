"""Build the pool of known-anomalous HDFS sessions used by live scenario injection.

    python -m logsentinel.stream.pools      # ~1 min, reads the processed sessions file once
"""
import argparse
import json
import random

from ..common.config import ROOT, load_config
from ..data.sessions import read_sessions

POOL = ROOT / "data" / "replay" / "hdfs.anomaly_pool.json"


def build(n: int = 400, seed: int = 7) -> int:
    src = ROOT / load_config()["processed_dir"] / "hdfs.chronological.sessions.jsonl.gz"
    anoms = [{"id": s.id, "lines": s.lines} for s in read_sessions(src, "test") if s.label == 1]
    random.Random(seed).shuffle(anoms)
    pool = anoms[:n]
    POOL.parent.mkdir(parents=True, exist_ok=True)
    POOL.write_text(json.dumps(pool))
    return len(pool)


def load() -> list[dict]:
    if not POOL.exists():
        raise FileNotFoundError("anomaly pool missing; run: python -m logsentinel.stream.pools")
    return json.loads(POOL.read_text())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    print(f"wrote {build(ap.parse_args().n)} sessions to {POOL}")
