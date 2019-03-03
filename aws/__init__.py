import logging.config
import yaml


with open('honeybadgermpc/logging.yaml', 'r') as f:
    logging_config = yaml.safe_load(f.read())
    logging.config.dictConfig(logging_config)
    logging.getLogger('paramiko').setLevel(logging.WARNING)
