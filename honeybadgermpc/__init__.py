"""HoneyBadgerMPC: Confidentiality Layer for Consortium Blockchains."""

import logging.config
import os
from pathlib import Path

import yaml


CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent

with open(CURRENT_DIR / "logging.yaml", "r") as f:
    os.makedirs(ROOT_DIR / "benchmark-logs", exist_ok=True)
    logging_config = yaml.safe_load(f.read())
    logging.config.dictConfig(logging_config)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
