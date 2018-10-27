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
        'nodeid': '0',
        'host': 'hbmpc_node_0',
        'port': 23264,
        'peers': {
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
        'nodeid': cfgparser.get('addrinfo', 'id'),
        'host': cfgparser.get('addrinfo', 'host'),
        'port': cfgparser.getint('addrinfo', 'port'),
        'peers': dict(cfgparser.items('peers')),
    }
    return config
