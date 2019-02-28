"""
Module for ``honeybadgermpc``'s configuration.

This module can be used to:

* define default configuration settings
* load a configuration
* validate a comfiguration

Sample config can be found at: conf/sample.ini
"""


from configparser import ConfigParser
from argparse import ArgumentParser


class NodeDetails(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


class HbmpcConfig(object):
    N = None
    t = None
    my_id = None
    peers = None
    skip_preprocessing = False
    extras = None

    @staticmethod
    def load_config():
        parser = ArgumentParser(description='Runs an HBMPC program.')

        parser.add_argument(
            '-d',
            '--distributed',
            dest='is_dist',
            action="store_true",
            help='Indicates that the program is being run in a distributed setting. \
                This will validate all `default` and `required` parameters.')

        parser.add_argument(
            '-f',
            '--config-file',
            type=str,
            dest='config_file_path',
            help='Path from where to load the HBMPC config file.')

        args = parser.parse_args()

        if args.is_dist:
            cfgparser = ConfigParser()

            with open(args.config_file_path) as file_object:
                cfgparser.read_file(file_object)

            HbmpcConfig.N = cfgparser.getint('general', 'N')
            HbmpcConfig.t = cfgparser.getint('general', 't')
            HbmpcConfig.my_id = cfgparser.getint('general', 'my_id')
            HbmpcConfig.peers = {
                int(peerid): NodeDetails(
                    addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
                for peerid, addrinfo in dict(cfgparser.items('peers')).items()
            }

            HbmpcConfig.skip_preprocessing = cfgparser.getboolean(
                'general', 'skip_preprocessing', fallback=False)
            if cfgparser.has_section("extra"):
                HbmpcConfig.extras = dict(cfgparser.items('extra'))

            # Ensure the required values are set before this method terminates
            assert HbmpcConfig.my_id is not None, "Node Id: missing"
            assert HbmpcConfig.N is not None, "N: missing"
            assert HbmpcConfig.t is not None, "t: missing"
            assert HbmpcConfig.peers is not None, "peers: missing"
