"""HoneyBadgerMPC: Confidentiality Layer for Consortium Blockchains."""

import logging.config
import yaml


with open('honeybadgermpc/logging.yaml', 'r') as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
