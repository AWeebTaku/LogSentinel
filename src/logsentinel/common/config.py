import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]

# All Kafka clients in this project read the port from here (default 9092), so a second,
# fully independent instance (its own Kafka, own DB via LOGSENTINEL_DB, own install dir via
# LOGSENTINEL_TOOLS) can run on the same machine without colliding with the first -- e.g. a
# staging deployment for training/testing next to the production one actually serving alerts.
KAFKA_PORT = int(os.environ.get("LOGSENTINEL_KAFKA_PORT", "9092"))
KAFKA_BOOTSTRAP = f"127.0.0.1:{KAFKA_PORT}"


def load_config(name: str = "data") -> dict:
    with open(ROOT / "configs" / f"{name}.yaml") as f:
        return yaml.safe_load(f)
