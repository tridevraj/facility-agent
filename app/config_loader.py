import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path=None):
    path = path or os.environ.get("FACILITY_CONFIG") or os.path.join(BASE_DIR, "config.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("categories", "priorities", "approval", "escalation"):
        if key not in cfg:
            raise ValueError(f"config is missing '{key}'")
    return cfg
