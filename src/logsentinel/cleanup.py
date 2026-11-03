"""Clean up previous runs, trained models, and generated data.

Always prints exactly what it would remove first -- id/path, size on disk, and age -- for every
category. Nothing is ever deleted unless --yes is passed; without it this is a pure dry-run report.

    python -m logsentinel.cleanup                          # report every category, delete nothing
    python -m logsentinel.cleanup --runs --yes              # delete ALL run records + their result dirs
    python -m logsentinel.cleanup --runs --keep-last 5 --yes
    python -m logsentinel.cleanup --runs --older-than-days 7 --yes
    python -m logsentinel.cleanup --run src-20261103-110711-c7da --yes   # one specific run
    python -m logsentinel.cleanup --models --keep-last 2 --yes   # registered bundles; active one is never touched
    python -m logsentinel.cleanup --derived-data --yes       # data/replay, data/features (rebuild: see report)
    python -m logsentinel.cleanup --raw-data --yes           # data/raw, data/processed -- slow to re-fetch, opt-in only
    python -m logsentinel.cleanup --broker-state --yes       # local Kafka's on-disk log segments; stop Kafka first
    python -m logsentinel.cleanup --all --yes                 # runs + models + derived-data (never raw-data/broker-state)
"""
import argparse
import os
import shutil
import socket
import time
from pathlib import Path

from .common.config import KAFKA_BOOTSTRAP, KAFKA_PORT, ROOT
from .store import db

DATA = ROOT / "data"
KAFKA_HOME = Path(os.environ.get("LOGSENTINEL_TOOLS", Path.home() / ".local" / "share" / "logsentinel"))
RUN_DIRS = {"sources": "source", "experiments": "experiment", "train": "train"}


def human(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def age_days(created_ns: int) -> float:
    return (time.time_ns() - created_ns) / 86_400_000_000_000


# ---- category discovery ------------------------------------------------------------------------------

def find_runs(con) -> list[dict]:
    """Every run: DB-tracked ones (results/{sources,experiments,train}/<id>) plus orphan result
    directories left behind by a wiped/replaced database."""
    items, known_dirs = [], set()
    for r in db.list_runs(con):
        d = Path(r["run_dir"]) if r["run_dir"] else None
        if d:
            known_dirs.add(d.resolve())
        items.append({"id": r["id"], "kind": r["kind"], "status": r["status"], "dir": d,
                      "created_ns": r["created_ns"], "in_db": True})
    for subdir, kind in RUN_DIRS.items():
        base = ROOT / "results" / subdir
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if d.is_dir() and d.resolve() not in known_dirs:
                items.append({"id": d.name, "kind": kind, "status": "orphan (no DB record)", "dir": d,
                              "created_ns": int(d.stat().st_mtime * 1e9), "in_db": False})
    return sorted(items, key=lambda x: x["created_ns"], reverse=True)


def find_models(con) -> list[dict]:
    return sorted(db.list_models(con), key=lambda m: m["created_ns"], reverse=True)


def find_derived_data() -> list[Path]:
    return [p for p in [DATA / "replay", DATA / "features"] if p.exists()]


def find_raw_data() -> list[Path]:
    return [p for p in [DATA / "raw", DATA / "processed"] if p.exists()]


def find_broker_state() -> list[Path]:
    return [p for p in [KAFKA_HOME / "kafka-data", KAFKA_HOME / "kafka-logs"] if p.exists()]


def kafka_is_up() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", KAFKA_PORT)) == 0


# ---- selection -----------------------------------------------------------------------------------

def select(items: list[dict], single_id: str | None, keep_last: int | None, older_than_days: float | None) -> list[dict]:
    if single_id:
        return [x for x in items if x["id"] == single_id]
    if keep_last is not None:
        return items[keep_last:]              # items is newest-first
    if older_than_days is not None:
        return [x for x in items if age_days(x["created_ns"]) >= older_than_days]
    return list(items)


# ---- reporting + deletion --------------------------------------------------------------------------

def report_runs(items: list[dict], selected: list[dict]) -> None:
    print(f"\n== Runs: {len(items)} total")
    for x in items:
        size = human(dir_size(x["dir"])) if x["dir"] and x["dir"].exists() else "no dir"
        mark = "*" if x in selected else " "
        running = "  [RUNNING, protected]" if x["status"] == "running" else ""
        print(f"  {mark} {x['kind']:<11} {x['id']:<32} {age_days(x['created_ns']):5.1f}d old  {size:>9}"
              f"  {'(db)' if x['in_db'] else '(orphan dir, no db row)'}{running}")
    print(f"  ({len(selected)} marked with * would be removed)")


def delete_runs(con, selected: list[dict]) -> tuple[int, int]:
    n = freed = 0
    for x in selected:
        if x["status"] == "running":
            print(f"  skipped (still running): {x['id']}")
            continue
        if x["dir"] and x["dir"].exists():
            freed += dir_size(x["dir"])
            shutil.rmtree(x["dir"])
        if x["in_db"]:
            con.execute("DELETE FROM runs WHERE id=?", (x["id"],))
            con.execute("DELETE FROM alerts WHERE run=?", (x["id"],))
            con.execute("DELETE FROM metrics WHERE run=?", (x["id"],))
            con.execute("DELETE FROM injections WHERE run=?", (x["id"],))
        print(f"  deleted: {x['id']}")
        n += 1
    return n, freed


def report_models(items: list[dict], selected: list[dict]) -> None:
    print(f"\n== Models: {len(items)} total")
    for m in items:
        size = human(dir_size(Path(m["path"]))) if Path(m["path"]).exists() else "no dir"
        mark = "*" if m in selected else " "
        active = "  [ACTIVE, protected]" if m["status"] == "active" else ""
        print(f"  {mark} {m['name']} v{m['version']:<3} {age_days(m['created_ns']):5.1f}d old  {size:>9}  "
              f"status={m['status']}{active}")
    print(f"  ({len(selected)} marked with * would be removed)")


def delete_models(con, selected: list[dict]) -> tuple[int, int]:
    n = freed = 0
    for m in selected:
        if m["status"] == "active":
            print(f"  skipped (active model): {m['name']} v{m['version']}")
            continue
        p = Path(m["path"])
        if p.exists():
            freed += dir_size(p)
            shutil.rmtree(p)
        con.execute("DELETE FROM models WHERE id=?", (m["id"],))
        print(f"  deleted: {m['name']} v{m['version']}")
        n += 1
    return n, freed


def report_paths(label: str, paths: list[Path], rebuild_hint: str) -> None:
    print(f"\n== {label}: {len(paths)} item(s){' -- rebuild with: ' + rebuild_hint if paths else ''}")
    for p in paths:
        print(f"  * {p.relative_to(ROOT) if ROOT in p.parents else p}  {human(dir_size(p))}")


def delete_paths(paths: list[Path]) -> tuple[int, int]:
    n = freed = 0
    for p in paths:
        freed += dir_size(p)
        shutil.rmtree(p)
        print(f"  deleted: {p}")
        n += 1
    return n, freed


# ---- CLI ------------------------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", action="store_true", help="select the run-history category")
    ap.add_argument("--models", action="store_true", help="select the trained-model-bundle category")
    ap.add_argument("--derived-data", action="store_true", help="select data/replay, data/features (cheap to rebuild)")
    ap.add_argument("--raw-data", action="store_true", help="select data/raw, data/processed (slow to re-fetch)")
    ap.add_argument("--broker-state", action="store_true", help="select the local Kafka broker's on-disk log segments")
    ap.add_argument("--all", action="store_true", help="runs + models + derived-data (never raw-data/broker-state)")
    ap.add_argument("--run", metavar="ID", help="only this one run id (implies --runs)")
    ap.add_argument("--keep-last", type=int, metavar="N", help="keep the N most recent, delete the rest")
    ap.add_argument("--older-than-days", type=float, metavar="D", help="delete only items at least D days old")
    ap.add_argument("--yes", action="store_true", help="actually delete; omit for a dry-run report only")
    a = ap.parse_args()

    do_runs = a.runs or a.all or bool(a.run)
    do_models = a.models or a.all
    do_derived = a.derived_data or a.all
    do_raw = a.raw_data
    do_broker = a.broker_state
    report_only_mode = not (do_runs or do_models or do_derived or do_raw or do_broker)
    if report_only_mode:                        # no category flags at all: show everything, delete nothing
        do_runs = do_models = do_derived = do_raw = do_broker = True

    with db.connect() as con:
        if do_runs:
            items = find_runs(con)
            selected = select(items, a.run, a.keep_last, a.older_than_days)
            report_runs(items, selected)
            if a.yes and not report_only_mode:
                n, freed = delete_runs(con, selected)
                print(f"  -> removed {n} run(s), freed {human(freed)}")

        if do_models:
            items = find_models(con)
            selected = select(items, None, a.keep_last, a.older_than_days)
            report_models(items, selected)
            if a.yes and not report_only_mode:
                n, freed = delete_models(con, selected)
                print(f"  -> removed {n} model(s), freed {human(freed)}")

    if do_derived:
        paths = find_derived_data()
        report_paths("Derived data (data/replay, data/features)", paths,
                      "python -m logsentinel.stream.pools  /  python -m logsentinel.data.build")
        if a.yes and not report_only_mode:
            n, freed = delete_paths(paths)
            print(f"  -> removed {n} item(s), freed {human(freed)}")

    if do_raw:
        paths = find_raw_data()
        report_paths("Raw/processed datasets (data/raw, data/processed)", paths,
                      "make data  (re-downloads HDFS/BGL/Thunderbird, can take a while)")
        if a.yes and not report_only_mode:
            n, freed = delete_paths(paths)
            print(f"  -> removed {n} item(s), freed {human(freed)}")

    if do_broker:
        paths = find_broker_state()
        report_paths("Kafka broker storage (outside the repo, local to this machine)", paths,
                      "nothing to rebuild -- topics are recreated automatically on next `scripts/kafka.sh start`")
        if a.yes and not report_only_mode:
            if kafka_is_up():
                print(f"  skipped: Kafka is running on {KAFKA_BOOTSTRAP} -- stop it first (scripts/kafka.sh stop)")
            else:
                n, freed = delete_paths(paths)
                print(f"  -> removed {n} item(s), freed {human(freed)}")

    if report_only_mode:
        print("\nDry run only -- nothing was deleted. Re-run with a category flag (--runs, --models, "
              "--derived-data, --raw-data, --broker-state, or --all) plus --yes to actually delete.")
    elif not a.yes:
        print("\nDry run -- nothing was deleted. Add --yes to actually delete the items marked with *.")


if __name__ == "__main__":
    main()
