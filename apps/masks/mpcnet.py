import asyncio
from pathlib import Path

from web3 import HTTPProvider, Web3

from apps.masks.config import CONTRACT_ADDRESS_FILEPATH
from apps.masks.server import Server
from apps.utils import get_contract_address

from honeybadgermpc.preprocessing import PreProcessedElements
from honeybadgermpc.router import SimpleRouter

MPCNET_HOST = "mpcnet"


def create_servers(w3, *, n, contract_context):
    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()  # deletes sharedata/ if present

    router = SimpleRouter(n)
    sends, recvs = router.sends, router.recvs
    return [
        Server(
            "sid",
            i,
            sends[i],
            recvs[i],
            w3,
            contract_context=contract_context,
            http_host=MPCNET_HOST,
            http_port=8080 + i,
        )
        for i in range(n)
    ]


async def main(w3, *, n, contract_context):
    servers = create_servers(w3, n=n, contract_context=contract_context)
    for server in servers:
        await server.join()


if __name__ == "__main__":
    # Launch MPC network
    contract_name = "MpcCoordinator"
    contract_filename = "contract.sol"
    contract_filepath = Path(__file__).resolve().parent.joinpath(contract_filename)
    contract_address = get_contract_address(CONTRACT_ADDRESS_FILEPATH)
    contract_context = {
        "address": contract_address,
        "filepath": contract_filepath,
        "name": contract_name,
    }

    eth_rpc_hostname = "blockchain"
    eth_rpc_port = 8545
    n, t = 4, 1
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    w3 = Web3(HTTPProvider(w3_endpoint_uri))
    asyncio.run(main(w3, n=n, contract_context=contract_context))
