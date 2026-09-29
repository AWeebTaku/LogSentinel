import argparse
from pathlib import Path

from ..common.config import ROOT
from ..features.counts import load_or_build
from .bundle import train_bundle


def main():
    ap = argparse.ArgumentParser(description="Train and save a deployable model bundle.")
    ap.add_argument("--dataset", default="hdfs")
    ap.add_argument("--mode", default="chronological")
    ap.add_argument("--parser", choices=["regex", "drain"], default="drain")
    ap.add_argument("--model", choices=["iforest", "pca", "ae"], default="pca")
    ap.add_argument("--threshold", choices=["percentile99", "three_sigma", "tuned_val"], default="tuned_val")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--early-age", type=int, default=0,
                    help="add an age check at this many log-seconds (HDFS only; see experiments/early.py)")
    ap.add_argument("--early-model", choices=["iforest", "pca", "ae"], default="ae")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or ROOT / "models" / f"{a.dataset}-{a.parser}-{a.model}"
    b = train_bundle(load_or_build(a.dataset, a.mode), a.dataset, a.parser, a.model, a.threshold, a.seed)
    if a.early_age:
        from ..features.sequences import build
        from .early import attach_early
        b.save(out)                      # sequences are cached next to the bundle and depend on its parser
        b = attach_early(b, build(out, a.mode), a.early_age, a.early_model, seed=a.seed)
    b.save(out)
    print(f"saved {out}: {b.meta}")


if __name__ == "__main__":
    main()
