import argparse
import asyncio
from pathlib import Path

import plyvel

import toml

from apps.masks.httpserver import HTTPServer
from apps.masks.mpcprogrunner import MPCProgRunner
from apps.masks.mpcserver import MPCServer
from apps.masks.preprocessor import PreProcessor
from apps.sharestore import LevelDB

# from apps.utils import fetch_contract

# from honeybadgermpc.config import NodeDetails

# from honeybadgermpc.ipc import NodeCommunicator

PARENT_DIR = Path(__file__).resolve().parent


def _get_contract_context(eth_config):
    from apps.masks.config import CONTRACT_ADDRESS_FILEPATH
    from apps.utils import get_contract_address

    context = {
        "address": get_contract_address(CONTRACT_ADDRESS_FILEPATH),
        "filepath": eth_config["contract_path"],
        "name": eth_config["contract_name"],
    }
    return context


def _create_w3(eth_config):
    from web3 import HTTPProvider, Web3

    eth_rpc_hostname = eth_config["rpc_host"]
    eth_rpc_port = eth_config["rpc_port"]
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    return Web3(HTTPProvider(w3_endpoint_uri))


class MPCNet:
    def __init__(self, *, ncs, mpcservers):
        self.mpcservers = mpcservers
        # pp_elements = PreProcessedElements()
        # pp_elements.clear_preprocessing()  # deletes sharedata/ if present

    @classmethod
    async def from_toml_config(cls, config_path):
        config = toml.load(config_path)

        # TODO extract resolving of relative path into utils
        context_path = Path(config_path).resolve().parent.joinpath(config["context"])
        config["eth"]["contract_path"] = context_path.joinpath(
            config["eth"]["contract_path"]
        )

        n = config["n"]
        base_config = {k: v for k, v in config.items() if k != "servers"}

        # For NodeCommunicator
        # node_details = {
        #    i: NodeDetails(s["host"], s["dr_port"])
        #    for i, s in enumerate(config["servers"])
        # }
        contract_context = _get_contract_context(config["eth"])
        w3 = _create_w3(config["eth"])

        session_id = "sid"
        ncs = []
        mpcservers = []
        for i in range(n):
            server_config = {k: v for k, v in config["servers"][i].items()}
            server_config.update(base_config, session_id="sid")

            myid = server_config["id"]

            # NodeCommunicator / zeromq sockets
            # nc = NodeCommunicator(node_details, i, 2)
            # await nc._setup()
            # ncs.append(nc)
            from honeybadgermpc.ipc import NodeCommunicator2

            peers = [
                {"id": s["id"], "host": s["host"], "port": s["dr_port"]}
                for s in config["servers"]
                if s["id"] != myid
            ]
            nc = NodeCommunicator2(
                myid=myid,
                host=config["servers"][myid]["host"],
                port=config["servers"][myid]["dr_port"],
                peers_config=peers,
                linger_timeout=2,
            )
            await nc._setup()
            ncs.append(nc)

            # NOTE: for testing purposes, we reset (destroy) the db before each run
            db_path = PARENT_DIR.joinpath(f"db{i}")
            plyvel.destroy_db(str(db_path))
            sharestore = LevelDB(db_path)  # use leveldb
            http_context = dict(host=server_config["host"], port=server_config["port"])
            mpcserver = MPCServer(
                session_id,
                myid,
                send=nc.send,
                recv=nc.recv,
                w3=w3,
                contract_context=contract_context,
                sharestore=sharestore,
                http_context=http_context,
                preprocessor_class=PreProcessor,
                httpserver_class=HTTPServer,
                mpcprogrunner_class=MPCProgRunner,
            )
            mpcservers.append(mpcserver)

        return cls(ncs=ncs, mpcservers=mpcservers)

    async def start(self):
        for i, mpcserver in enumerate(self.mpcservers):
            await mpcserver.start()
            # await self.ncs[i]._exit()


async def main(config_file):
    mpcnet = await MPCNet.from_toml_config(config_file)
    await mpcnet.start()


if __name__ == "__main__":
    # arg parsing
    default_config_path = PARENT_DIR.joinpath("mpcnet.toml")
    parser = argparse.ArgumentParser(description="MPC network.")
    parser.add_argument(
        "-c",
        "--config-file",
        default=str(default_config_path),
        help=f"Configuration file to use. Defaults to '{default_config_path}'.",
    )
    args = parser.parse_args()

    # Launch MPC network
    asyncio.run(main(args.config_file))
