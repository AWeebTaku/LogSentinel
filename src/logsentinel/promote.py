"""Promote a trained model bundle from one instance's database into another's.

For the staging + production instance-isolation setup (see README.md): a model trained and
validated in staging never appears in production's own database (each instance has its own
LOGSENTINEL_DB on purpose, so training can't touch what's live). This registers an already-trained
bundle directly into a target database and activates it -- no need for the target instance's API
to be reachable or in --app-mode full.

On one machine, both instances already share the same `models/` directory on disk (same repo
checkout), so there is nothing to copy -- only the target database needs to learn the bundle
exists. On separate machines, copy/rsync the bundle directory to the target machine's `models/`
first (its path must resolve there too), then run this pointed at the target's database file.

    python -m logsentinel.promote models/hdfs-drain-pca-20261103-000132 --to data/prod.db
    python -m logsentinel.promote models/hdfs-drain-pca-20261103-000132 --to data/prod.db --no-activate
"""
import argparse
from pathlib import Path

from .store import db


def promote(bundle_dir: Path, to_db: Path, activate: bool = True, name: str | None = None) -> dict:
    with db.connect(to_db) as con:
        m = db.register_model(con, bundle_dir, name)
        if activate:
            m = db.activate_model(con, m["id"])
        return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", help="trained model bundle directory (needs bundle.joblib + meta.json)")
    ap.add_argument("--to", required=True, metavar="DB_PATH", help="target instance's database file (its LOGSENTINEL_DB)")
    ap.add_argument("--name", default=None, help="registered name (default: the bundle directory's own name)")
    ap.add_argument("--no-activate", action="store_true", help="register only; don't make it the active model")
    a = ap.parse_args()

    bundle_dir = Path(a.bundle)
    if not bundle_dir.is_dir():
        raise SystemExit(f"{bundle_dir} is not a directory")
    to_db = Path(a.to)
    if not to_db.exists():
        print(f"note: {to_db} doesn't exist yet -- it will be created fresh (schema only), as if this "
              f"were the target instance's first model")

    m = promote(bundle_dir, to_db, activate=not a.no_activate, name=a.name)
    print(f"registered {m['name']} v{m['version']} (id {m['id']}, dataset {m['dataset']!r}) in {to_db}"
          f"{' and activated it' if m['status'] == 'active' else ' (not activated: --no-activate)'}")


if __name__ == "__main__":
    main()
