"""HoneyBadgerMPC: Confidentiality Layer for Consortium Blockchains."""

import logging.config
import os
import yaml
import sys
from honeybadgermpc.config import HbmpcConfig


with open("honeybadgermpc/logging.yaml", "r") as f:
    os.makedirs("benchmark-logs", exist_ok=True)
    logging_config = yaml.safe_load(f.read())
    logging.config.dictConfig(logging_config)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

# Skip loading the config for tests since the would have different values for sys.argv.
if "pytest" not in sys.modules:
    HbmpcConfig.load_config()
