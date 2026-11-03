"""Retrain a bundle folding in confirmed false positives as extra normal training examples.

Unsupervised detectors (PCA/IsolationForest/AE) learn "normal" only from the training split. A
false positive is, by definition, a session whose ground-truth label is normal that the model
flagged anyway -- so confirmed false positives are free, real feedback: pull their session ids
from the alert DB, move those sessions into the training split for this run, and retrain. This
never touches the original dataset or its cached features on disk; it only relabels which split
each row belongs to for the one new bundle being built.

The new bundle is only *registered* in the given database (your own LOGSENTINEL_DB -- normally
staging's), never activated and never promoted. Review it on the Models page like any other
trained bundle, then Activate/Promote it yourself if it looks better -- same human checkpoint as
everywhere else in this project, nothing here bypasses it.

    python -m logsentinel.models.retrain_feedback
    python -m logsentinel.models.retrain_feedback --dataset hdfs --parser drain --model pca
    python -m logsentinel.models.retrain_feedback --min-false-positives 5   # skip if too few to bother

For periodic/scheduled retraining, run this on a timer (cron, systemd timer) -- it's safe to run
with nothing new to learn from: too few false positives (below --min-false-positives) and it exits
without creating a bundle.
"""
import argparse
import time
from dataclasses import replace
from pathlib import Path

from ..common.config import ROOT
from ..features.counts import CountFeatures, load_or_build
from ..store import db
from .bundle import train_bundle


def false_positive_session_keys(con, run: str | None = None) -> set[str]:
    keys: set[str] = set()
    after_id = 0
    while True:
        batch = db.list_alerts(con, status="false_positive", run=run, after_id=after_id, limit=500)
        if not batch:
            break
        keys.update(a["session_key"] for a in batch)
        after_id = batch[-1]["id"]
    return keys


def retrain(con, cf: CountFeatures, dataset: str, parser: str, model: str, threshold_rule: str, seed: int,
            min_false_positives: int, run: str | None = None, out: Path | None = None) -> dict | None:
    keys = false_positive_session_keys(con, run)
    id_to_row = {sid: i for i, sid in enumerate(cf.ids)}
    rows = sorted(id_to_row[k] for k in keys if k in id_to_row)
    skipped = len(keys) - len(rows)
    if len(rows) < min_false_positives:
        print(f"{len(rows)} false-positive session(s) found in {dataset} "
              f"(need {min_false_positives}); not enough to bother retraining." +
              (f" ({skipped} more didn't match any known session id.)" if skipped else ""))
        return None

    cf2 = replace(cf, splits=cf.splits.copy())
    cf2.splits[rows] = "train"
    b = train_bundle(cf2, dataset, parser, model, threshold_rule, seed)
    b.meta["feedback"] = {"false_positives_folded_in": len(rows), "unmatched": skipped,
                          "source_run": run or "all runs"}

    name = f"{dataset}-{parser}-{model}-fpfeedback-{time.strftime('%Y%m%d-%H%M%S')}"
    out = out or ROOT / "models" / name
    b.save(out)
    m = db.register_model(con, out, name, metrics=b.meta["feedback"])
    print(f"registered {m['name']} v{m['version']} (id {m['id']}): folded in {len(rows)} confirmed "
          f"false-positive session(s), not activated -- review it on the Models page.")
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="hdfs")
    ap.add_argument("--mode", default="chronological")
    ap.add_argument("--parser", choices=["regex", "drain"], default="drain")
    ap.add_argument("--model", choices=["iforest", "pca", "ae"], default="pca")
    ap.add_argument("--threshold", choices=["percentile99", "three_sigma", "tuned_val"], default="tuned_val")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run", default=None, help="only false positives from this run id (default: all runs)")
    ap.add_argument("--min-false-positives", type=int, default=10,
                    help="skip retraining if fewer confirmed false positives than this are found")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    cf = load_or_build(a.dataset, a.mode)
    with db.connect() as con:
        retrain(con, cf, a.dataset, a.parser, a.model, a.threshold, a.seed, a.min_false_positives, a.run, a.out)


if __name__ == "__main__":
    main()
