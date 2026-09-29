"""Turn raw datasets into time-ordered, split Session files: data/processed/<name>.sessions.jsonl.gz."""
import argparse
import json
from pathlib import Path

from ..common.config import ROOT, load_config
from ..common.env import capture_env
from .bgl import iter_window_sessions
from .hdfs import iter_hdfs_sessions
from .sessions import write_sessions
from .split import split_sessions


def _find(root: Path, pattern: str) -> Path:
    hits = sorted(root.rglob(pattern))
    if not hits:
        raise FileNotFoundError(f"{pattern} not found under {root}; run logsentinel-download first")
    return hits[0]


def _summary(name: str, sessions: list) -> dict:
    out = {"dataset": name, "sessions": len(sessions)}
    for sp in ("train", "val", "test"):
        xs = [s for s in sessions if s.split == sp]
        out[sp] = {"n": len(xs), "anomalies": sum(s.label for s in xs),
                   "lines": sum(len(s.lines) for s in xs)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["hdfs", "bgl", "thunderbird"], nargs="*", default=["hdfs", "bgl"])
    ap.add_argument("--split-mode", choices=["chronological", "random"], default=None,
                    help="default: split.mode from configs/data.yaml")
    ap.add_argument("--max-lines", type=int, default=None, help="debug: only read the first N lines")
    args = ap.parse_args()

    cfg = load_config()
    raw, proc = ROOT / cfg["raw_dir"], ROOT / cfg["processed_dir"]
    proc.mkdir(parents=True, exist_ok=True)
    sp = cfg["split"]
    mode = args.split_mode or sp.get("mode", "chronological")

    for name in args.only:
        if name == "hdfs":
            it = iter_hdfs_sessions(_find(raw / "hdfs", "HDFS.log"),
                                    _find(raw / "hdfs", "anomaly_label.csv"), args.max_lines)
        else:  # bgl and thunderbird share the line format and windowing
            w = cfg[name]
            log = "BGL.log" if name == "bgl" else "Thunderbird.log"
            it = iter_window_sessions(_find(raw / name, log),
                                      w["window_seconds"], w["min_lines"], args.max_lines)
        sessions = split_sessions(it, sp["train"], sp["val"], mode, sp.get("seed", 42))
        write_sessions(sessions, proc / f"{name}.{mode}.sessions.jsonl.gz")
        info = _summary(name, sessions) | {"env": capture_env()}
        (proc / f"{name}.{mode}.summary.json").write_text(json.dumps(info, indent=2))
        print(json.dumps({k: v for k, v in info.items() if k != "env"}, indent=2))


if __name__ == "__main__":
    main()
