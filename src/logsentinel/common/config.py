from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def load_config(name: str = "data") -> dict:
    with open(ROOT / "configs" / f"{name}.yaml") as f:
        return yaml.safe_load(f)
