"""HoneyBadgerMPC: Confidentiality Layer for Consortium Blockchains."""

import logging.config
import os
import yaml


with open('honeybadgermpc/logging.yaml', 'r') as f:
    os.makedirs("benchmark", exist_ok=True)
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
