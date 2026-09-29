"""Fetch LogHub datasets from Zenodo (record 8196385), verify MD5, unzip into data/raw/<name>/.

Default: HDFS_v1 (187 MB) and BGL (57 MB).
Thunderbird (2 GB compressed, ~30 GB raw) is opt-in and streamed: only the first --tb-lines lines are
read from the tarball and the download stops there (no MD5, since the archive is never fully read).
"""
import argparse
import hashlib
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from ..common.config import ROOT, load_config

BASE = "https://zenodo.org/records/8196385/files"
DATASETS = {
    "hdfs": ("HDFS_v1.zip", "76a24b4d9a6164d543fb275f89773260"),
    "bgl": ("BGL.zip", "4452953c470f2d95fcb32d5f6e733f7a"),
}


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, raw_dir: Path) -> Path:
    fname, md5 = DATASETS[name]
    out = raw_dir / name
    if out.exists() and any(out.iterdir()):
        print(f"[{name}] already extracted at {out}")
        return out
    raw_dir.mkdir(parents=True, exist_ok=True)
    zpath = raw_dir / fname
    if not zpath.exists() or _md5(zpath) != md5:
        print(f"[{name}] downloading {fname} ...")
        urllib.request.urlretrieve(f"{BASE}/{fname}?download=1", zpath)
    if (got := _md5(zpath)) != md5:
        raise RuntimeError(f"{fname}: MD5 mismatch (got {got}, expected {md5})")
    print(f"[{name}] MD5 ok, extracting ...")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(out)
    return out


def fetch_thunderbird(raw_dir: Path, max_lines: int) -> Path:
    out = raw_dir / "thunderbird" / "Thunderbird.log"
    if out.exists():
        print(f"[thunderbird] already present at {out}")
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[thunderbird] streaming first {max_lines:,} lines from the tarball ...")
    url = f"{BASE}/Thunderbird.tar.gz?download=1"
    with urllib.request.urlopen(url) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            src = tar.extractfile(member)
            with open(out.with_suffix(".part"), "wb") as dst:
                for i, line in enumerate(src):
                    if i >= max_lines:
                        break
                    dst.write(line)
            out.with_suffix(".part").rename(out)
            return out
    raise RuntimeError("no file found in Thunderbird.tar.gz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=[*DATASETS, "thunderbird"], nargs="*", default=list(DATASETS))
    ap.add_argument("--tb-lines", type=int, default=None, help="Thunderbird lines to keep")
    args = ap.parse_args()
    cfg = load_config()
    raw_dir = ROOT / cfg["raw_dir"]
    for n in args.only:
        if n == "thunderbird":
            fetch_thunderbird(raw_dir, args.tb_lines or cfg["thunderbird"]["max_lines"])
        else:
            fetch(n, raw_dir)


if __name__ == "__main__":
    main()
