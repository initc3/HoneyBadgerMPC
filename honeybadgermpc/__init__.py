"""HoneyBadgerMPC: Confidentiality Layer for Consortium Blockchains."""

import logging.config
from pathlib import Path

import yaml


CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent

print(f"ROOT dir: {ROOT_DIR}")

with open(CURRENT_DIR / "logging.yaml", "r") as f:
    logging_config = yaml.safe_load(f.read())
    logging.config.dictConfig(logging_config)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
