"""Module for ``honeybadgermpc``'s configuration.

This module can be used to:

* define default configuration settings
* load a configuration
* validate a comfiguration

example of config dict:

code-block:: python

    {
        'N': 4,
        't': 1,
        'k': 4,
        'delta': -999,
        'skipPreprocessing': False,
        'peers': {
            '0': hbmpc_node_0:23264,
            '1': hbmpc_node_1:23265,
            '2': hbmpc_node_2:23266,
            '3': hbmpc_node_3:23267,
        },
    }
"""
from configparser import ConfigParser


def load_config(path):
    """Read a configuration file given by ``path`` and return a :obj:`dict`."""
    cfgparser = ConfigParser()

    with open(path) as file_object:
        cfgparser.read_file(file_object)

    config = {
        'N': cfgparser.getint('general', 'N'),
        't': cfgparser.getint('general', 't'),
        'k': cfgparser.getint('general', 'k'),
        'delta': cfgparser.getint('general', 'delta'),
        'peers': dict(cfgparser.items('peers')),
        'skipPreprocessing': cfgparser.getboolean('general', 'skipPreprocessing')
    }
    return config
