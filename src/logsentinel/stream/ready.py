"""Wait until an engine consumer group has a STABLE partition assignment before producing.

Each worker rewrites its ready file (with its partition count) on every assignment callback, so a file can be
stale while the group is still rebalancing. Producing during a rebalance makes partitions move mid-run and the new
owner re-reads from the last committed offset (duplicates). Ready therefore means: every worker has a file, the counts
sum to exactly the number of partitions, and no file changed for `settle_s` seconds.
"""
import time
from pathlib import Path


def is_ready(run_dir: Path, workers: int, partitions: int, settle_s: float, now: float | None = None) -> bool:
    files = [run_dir / f"ready-{w}" for w in range(workers)]
    if not all(f.exists() for f in files):
        return False
    try:
        assigned = sum(int(f.read_text() or 0) for f in files)
    except ValueError:
        return False                      # a file was caught mid-write
    newest = max(f.stat().st_mtime for f in files)
    return assigned == partitions and (now or time.time()) - newest >= settle_s


def wait_ready(run_dir: Path, workers: int, partitions: int, procs, timeout: float = 120.0, settle_s: float = 3.0) -> None:
    t0 = time.time()
    while not is_ready(run_dir, workers, partitions, settle_s):
        if time.time() - t0 > timeout or any(p.poll() is not None for p in procs):
            raise RuntimeError("engine workers did not reach a stable assignment; see worker logs")
        time.sleep(0.2)
