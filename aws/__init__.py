import logging.config
import yaml
import os


with open("honeybadgermpc/logging.yaml", "r") as f:
    os.makedirs("benchmark-logs", exist_ok=True)
    logging_config = yaml.safe_load(f.read())
    logging.config.dictConfig(logging_config)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
