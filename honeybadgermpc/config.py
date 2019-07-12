"""
Module for ``honeybadgermpc``'s configuration.

This module can be used to:

* define default configuration settings
* load a configuration
* validate a comfiguration

Sample config can be found at: conf/sample.ini
"""

from argparse import ArgumentParser
import json
from honeybadgermpc.reed_solomon import Algorithm as RSAlgorithm


class NodeDetails(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


class ConfigVars(object):
    Reconstruction = "reconstruction"


class ReconstructionConfig(object):
    def __init__(self, induce_faults, decoding_algorithm):
        self.induce_faults = induce_faults
        self.decoding_algorithm = decoding_algorithm

    @classmethod
    def default(cls):
        return cls(induce_faults=False, decoding_algorithm=RSAlgorithm.GAO)

    @classmethod
    def from_json(cls, json_config):
        res = cls.default()
        if "induce_faults" in json_config:
            res.induce_faults = json_config["induce_faults"]

        decoding_algorithms = [RSAlgorithm.WELCH_BERLEKAMP, RSAlgorithm.GAO]
        if "decoding_algorithm" in json_config:
            decoding_algorithm = json_config["decoding_algorithm"]
            assert (
                decoding_algorithm in decoding_algorithms
            ), f"decoding_algorithm must be in {decoding_algorithms}"
            res.decoding_algorithm = json_config["decoding_algorithm"]

        return res


class HbmpcConfig(object):
    N = None
    t = None
    my_id = None
    peers = None
    skip_preprocessing = False
    extras = None
    reconstruction = None

    @staticmethod
    def load_config():
        parser = ArgumentParser(description="Runs an HBMPC program.")

        parser.add_argument(
            "-d",
            "--distributed",
            dest="is_dist",
            action="store_true",
            help="Indicates that the program is being run in a distributed setting. \
                This will validate all `default` and `required` parameters.",
        )

        parser.add_argument(
            "-f",
            "--config-file",
            type=str,
            dest="config_file_path",
            help="Path from where to load the HBMPC config file.",
        )

        args = parser.parse_args()

        if args.is_dist:
            config = json.load(open(args.config_file_path))

            HbmpcConfig.N = config["N"]
            HbmpcConfig.t = config["t"]
            HbmpcConfig.my_id = config["my_id"]
            HbmpcConfig.peers = {
                peerid: NodeDetails(addrinfo.split(":")[0], int(addrinfo.split(":")[1]))
                for peerid, addrinfo in enumerate(config["peers"])
            }

            if "skip_preprocessing" in config:
                HbmpcConfig.skip_preprocessing = config["skip_preprocessing"]
            if "extra" in config:
                HbmpcConfig.extras = config["extra"]

            reconstruction_data = {}
            if "reconstruction" in config:
                reconstruction_data = config["reconstruction"]

            HbmpcConfig.reconstruction = ReconstructionConfig.from_json(
                reconstruction_data
            )

            # Ensure the required values are set before this method terminates
            assert HbmpcConfig.my_id is not None, "Node Id: missing"
            assert HbmpcConfig.N is not None, "N: missing"
            assert HbmpcConfig.t is not None, "t: missing"
            assert HbmpcConfig.peers is not None, "peers: missing"
