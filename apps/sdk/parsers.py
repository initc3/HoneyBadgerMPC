import argparse
import logging
from pathlib import Path

import plyvel

import toml

from web3 import HTTPProvider, Web3

from apps.sdk.db import LevelDB
from apps.sdk.utils import get_contract_address


class ServerConfig:
    def merge_config(self, args):
        config = toml.load(args.config_path)
        self.hbmpc_home = args.hbmpc_home or config.get(
            "hbmpc_home", self.defaults["hbmpc_home"]
        )
        self.mpc_port = args.mpc_port or config.get(
            "mpc_port", self.defaults["mpc_port"]
        )

        # eth node
        self.eth_rpc_hostname = args.eth_rpc_host or config["eth"]["rpc_host"]
        self.eth_rpc_port = args.eth_rpc_port or config["eth"].get(
            "rpc_port", self.defaults["eth_rpc_port"]
        )
        # w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
        # w3 = Web3(HTTPProvider(w3_endpoint_uri))


class ServerArgumentParser(argparse.ArgumentParser):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.default_hbmpc_home = Path.home().joinpath(".hbmpc")
        self.default_config_path = self.default_hbmpc_home.joinpath("config.toml")
        self.default_mpc_port = 7000
        self.default_http_port = 8080
        self.default_eth_rpc_port = 8545
        self.default_db_path = "~/.hbmpc/db"
        self.default_contract_name = "MPCCoordinator"
        self.default_contract_lang = "vyper"
        self._init_parser()

    def _init_parser(self):
        self.add_argument(
            "-c",
            "--config-path",
            default=str(self.default_config_path),
            help=f"Configuration file to use. Defaults to '{self.default_config_path}'.",
        )
        self.add_argument(
            "--hbmpc-home",
            type=str,
            help=(
                "Home directory to store configurations, public and private data. "
                "If not provided, will fall back on value specified in config file. "
                f"If absent from config file will default to {self.default_hbmpc_home}."
            ),
        )
        self.add_argument(
            "--id",
            type=int,
            help=(
                "Unique identifier for that server within an MPC network. "
                "If not provided, will fall back on value specified in config file. "
                "Failure to provide the id as a command line argument or in the config "
                "file will result in an error."
            ),
        )
        self.add_argument(
            "--host",
            type=str,
            help=(
                "Host or ip address of that MPC server. "
                "If not provided, will fall back on value specified in config file. "
                "Failure to provide the host as a command line argument or in the config "
                "file will result in an error."
            ),
        )
        self.add_argument(
            "--mpc-port",
            type=int,
            # default=default_mpc_port,
            help=(
                "Listening/router port for MPC communications. "
                f"Defaults to '{self.default_mpc_port}' or to what is provided in "
                "config file. Note that if that if a command line argument is provided "
                "it will overwrite what is given in the config file."
            ),
        )
        self.add_argument(
            "--http-port",
            type=int,
            # default=default_http_port,
            help=(
                "Listening port for HTTP client requests. "
                f"Defaults to '{self.default_http_port}' or to what is provided in "
                "config file. Note that if that if a command line argument is provided "
                "it will overwrite what is given in the config file."
            ),
        )
        self.add_argument(
            "--eth-rpc-host",
            type=str,
            help=(
                "RPC host or ip address to connect to an ethereum node. "
                "If not provided, will fall back on value specified in config file. "
                "Failure to provide the ethereum rpc host as a command line argument "
                "or in the config file will result in an error."
            ),
        )
        self.add_argument(
            "--eth-rpc-port",
            type=int,
            help=(
                "RPC port to connect to an ethereum node. Defaults to "
                f"'{self.default_eth_rpc_port}' or to what is provided in config file. "
                "Note that if that if a command line argument is provided it will "
                " overwrite what is given in the config file."
            ),
        )
        self.add_argument(
            "--db-path",
            type=str,
            help=(
                "Path to the directory where the db is to be located. "
                f"Defaults to '{self.default_db_path}'."
            ),
        )
        self.add_argument(
            "--reset-db", action="store_true", help="Resets the database. Be careful!",
        )
        self.add_argument(
            "--contract-address",
            type=str,
            help=(
                "The ethereum address of the deployed coordinator contract. "
                "If it is not provided, the config file will be looked at. "
            ),
        )
        self.add_argument(
            "--contract-path",
            type=str,
            help=(
                "The ethereum coordinator contract filepath. "
                "If it is not provided, the config file will be looked at. "
                "If absent from the config file, it will error."
                # TODO - review the above
            ),
        )
        self.add_argument(
            "--contract-name",
            type=str,
            help=(
                "The ethereum coordinator contract name. If it is not provided, "
                "the config file will be looked at. If absent from the config "
                f"file, it will be set as {self.default_contract_name}."
            ),
        )
        self.add_argument(
            "--contract-lang",
            type=str,
            help=(
                "The ethereum coordinator contract language. "
                "If it is not provided, the config file will be looked at. "
                "If absent from the config file, it will be set to "
                f"'{self.default_contract_lang}'."
            ),
        )

    def _merge_with_config(self, args, config):
        raise NotImplementedError

    def post_process_args(self, args, config):
        defaults = {
            "hbmpc_home": Path.home().joinpath(".hbmpc"),
            "mpc_port": 7000,
            "http_port": 8080,
            "eth_rpc_port": 8545,
            "db_path": "~/.hbmpc/db",
            "contract_name": "MPCCoordinator",
            "contract_lang": "ratel",
        }

        hbmpc_home = args.hbmpc_home or config.get("hbmpc_home", defaults["hbmpc_home"])
        mpc_port = args.mpc_port or config.get("mpc_port", defaults["mpc_port"])

        # eth node
        eth_rpc_hostname = args.eth_rpc_host or config["eth"]["rpc_host"]
        eth_rpc_port = args.eth_rpc_port or config["eth"].get(
            "rpc_port", defaults["eth_rpc_port"]
        )
        w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
        w3 = Web3(HTTPProvider(w3_endpoint_uri))

        # For NodeCommunicator
        try:
            myid = args.id or config["id"]
        except KeyError:
            logging.error(
                "Missing server id! Must be provided as a command line "
                "argument or in the config file."
            )
            raise

        try:
            host = args.host or config["host"]
        except KeyError:
            logging.error(
                "Missing server hostname or ip! Must be provided as a "
                "command line argument or in the config file."
            )
            raise
        peers = tuple(
            {"id": peer["id"], "host": peer["host"], "port": peer["mpc_port"]}
            for peer in config["peers"]
        )

        # FIXME remove after what is the node below has been better understood
        # NOTE leaving this temporarily as I would like to understand better why
        # when the NodeCommunicator is instantiated here it stalls. More precisely,
        # it will stall on processing the messages. It appears to block on the call
        # to read the queue:
        #
        #       msg = await node_msg_queue.get()
        #
        # the above is in ipc.py, in the method _process_node_messages
        #
        # from honeybadgermpc.ipc import NodeCommunicator2
        #
        # node_communicator = NodeCommunicator2(
        #    myid=myid, host=host, port=mpc_port, peers_config=peers, linger_timeout=2
        # )

        # db
        db_path = Path(f"{args.db_path}").resolve()
        if args.reset_db:
            # NOTE: for testing purposes, we reset (destroy) the db before each run
            plyvel.destroy_db(str(db_path))
        db = LevelDB(db_path)  # use leveldb

        http_port = args.http_port or config["http_port"] or defaults["http_port"]

        # contract context
        contract_path = Path(
            args.contract_path or config["contract"]["path"]
        ).expanduser()
        contract_name = args.contract_name or config["contract"]["name"]
        contract_address = args.contract_address or config["contract"].get("address")
        if not contract_address:
            contract_address = get_contract_address(
                Path(hbmpc_home).joinpath("public/contract_address")
            )
        contract_lang = args.contract_lang or config["contract"].get(
            "lang", defaults["contract_lang"]
        )
        contract_context = {
            "filepath": contract_path,
            "name": contract_name,
            "address": contract_address,
            "lang": contract_lang,
        }
        _args = {
            "hbmpc_home": hbmpc_home,
            "mpc_port": mpc_port,
            "eth_rpc_hostname": eth_rpc_hostname,
            "eth_rpc_port": eth_rpc_port,
            "myid": myid,
            "host": host,
            "peers": peers,
            "http_port": http_port,
            "db_path": db_path,
            "db": db,
            "w3": w3,
            "contract_context": contract_context,
        }
        return _args
