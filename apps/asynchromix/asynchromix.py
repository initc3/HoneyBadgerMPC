"""
Implementation of Asynchromix MPC Coordinator using an EVM blockchain
"""
from web3 import Web3, HTTPProvider
import time
import asyncio
import logging
from contextlib import contextmanager
import subprocess
from honeybadgermpc.router import SimpleRouter
from honeybadgermpc.utils.misc import (
    subscribe_recv,
    wrap_send,
    print_exception_callback,
    flatten_lists,
)
from honeybadgermpc.field import GF
from honeybadgermpc.preprocessing import PreProcessedElements
from honeybadgermpc.polynomial import EvalPoint, polynomials_over
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.offline_randousha import randousha
from honeybadgermpc.offline_randousha import generate_triples
from honeybadgermpc.offline_randousha import generate_bits
from honeybadgermpc.mpc import Mpc
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiplyArrays
from honeybadgermpc.progs.mixins.constants import MixinConstants
from butterfly_network import iterated_butterfly_network
from ethereum.tools._solidity import compile_code as compile_source
from web3.contract import ConciseContract
import os


field = GF(Subgroup.BLS12_381)


async def wait_for_receipt(w3, tx_hash):
    while True:
        tx_receipt = w3.eth.getTransactionReceipt(tx_hash)
        if tx_receipt is not None:
            break
        await asyncio.sleep(5)
    return tx_receipt


########
# Client
########


class AsynchromixClient(object):
    def __init__(self, sid, myid, send, recv, w3, contract, req_mask):
        self.sid = sid
        self.myid = myid
        self.contract = contract
        self.w3 = w3
        self.req_mask = req_mask
        self._task = asyncio.ensure_future(self._run())
        self._task.add_done_callback(print_exception_callback)

    async def _run(self):
        contract_concise = ConciseContract(self.contract)
        await asyncio.sleep(60)  # give the servers a head start
        # Client sends several batches of messages then quits
        for epoch in range(1000):
            logging.info(f"[Client] Starting Epoch {epoch}")
            receipts = []
            for i in range(32):
                m = f"message:{epoch}:{i}"
                task = asyncio.ensure_future(self.send_message(m))
                task.add_done_callback(print_exception_callback)
                receipts.append(task)
            receipts = await asyncio.gather(*receipts)

            while True:  # wait before sending next
                if contract_concise.outputs_ready() > epoch:
                    break
                await asyncio.sleep(5)

    async def _get_inputmask(self, idx):
        # Private reconstruct
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        poly = polynomials_over(field)
        eval_point = EvalPoint(field, n, use_omega_powers=False)
        shares = []
        for i in range(n):
            share = self.req_mask(i, idx)
            shares.append(share)
        shares = await asyncio.gather(*shares)
        shares = [(eval_point(i), share) for i, share in enumerate(shares)]
        mask = poly.interpolate_at(shares, 0)
        return mask

    async def join(self):
        await self._task

    async def send_message(self, m):
        # Submit a message to be mixed
        contract_concise = ConciseContract(self.contract)

        # Step 1. Wait until there is input available, and enough triples
        while True:
            inputmasks_available = contract_concise.inputmasks_available()
            # logging.infof'inputmasks_available: {inputmasks_available}')
            if inputmasks_available >= 1:
                break
            await asyncio.sleep(5)

        # Step 2. Reserve the input mask
        tx_hash = self.contract.functions.reserve_inputmask().transact(
            {"from": self.w3.eth.accounts[0]}
        )
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        rich_logs = self.contract.events.InputMaskClaimed().processReceipt(tx_receipt)
        if rich_logs:
            inputmask_idx = rich_logs[0]["args"]["inputmask_idx"]
        else:
            raise ValueError

        # Step 3. Fetch the input mask from the servers
        inputmask = await self._get_inputmask(inputmask_idx)
        message = int.from_bytes(m.encode(), "big")
        maskedinput = message + inputmask
        maskedinput_bytes = self.w3.toBytes(hexstr=hex(maskedinput.value))
        maskedinput_bytes = maskedinput_bytes.rjust(32, b"\x00")

        # Step 4. Publish the masked input
        tx_hash = self.contract.functions.submit_message(
            inputmask_idx, maskedinput_bytes
        ).transact({"from": self.w3.eth.accounts[0]})
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)


########
# Server
########


class AsynchromixServer(object):
    def __init__(self, sid, myid, send, recv, w3, contract):
        self.sid = sid
        self.myid = myid
        self.contract = contract
        self.w3 = w3
        self._task1a = asyncio.ensure_future(self._offline_inputmasks_loop())
        self._task1a.add_done_callback(print_exception_callback)
        self._task1b = asyncio.ensure_future(self._offline_mixes_loop())
        self._task1b.add_done_callback(print_exception_callback)
        self._task2 = asyncio.ensure_future(self._client_request_loop())
        self._task2.add_done_callback(print_exception_callback)
        self._task3 = asyncio.ensure_future(self._mixing_loop())
        self._task3.add_done_callback(print_exception_callback)
        self._task4 = asyncio.ensure_future(self._mixing_initiate_loop())
        self._task4.add_done_callback(print_exception_callback)

        self._subscribe_task, subscribe = subscribe_recv(recv)

        def _get_send_recv(tag):
            return wrap_send(tag, send), subscribe(tag)

        self.get_send_recv = _get_send_recv

        self._inputmasks = []
        self._triples = []
        self._bits = []

    async def join(self):
        await self._task1a
        await self._task1b
        await self._task2
        await self._task3
        await self._task4
        await self._subscribe_task

    #######################
    # Step 1. Offline Phase
    #######################
    """
    1a. offline mixes (bits and triples)
    1b. offline inputmasks
    The bits and triples are consumed by each mixing epoch.

    The input masks may be claimed at a different rate than
    than the mixing epochs so they are replenished in a separate
    task
    """

    async def _preprocess_report(self):
        # Submit the preprocessing report
        tx_hash = self.contract.functions.preprocess_report(
            [len(self._triples), len(self._bits), len(self._inputmasks)]
        ).transact({"from": self.w3.eth.accounts[self.myid]})

        # Wait for the tx receipt
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        return tx_receipt

    async def _offline_mixes_loop(self):
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()
        preproc_round = 0
        PER_MIX_TRIPLES = contract_concise.PER_MIX_TRIPLES()  # noqa: N806
        PER_MIX_BITS = contract_concise.PER_MIX_BITS()  # noqa: N806

        # Start up:
        await self._preprocess_report()

        while True:
            # Step 1a. I) Wait for more triples/bits to be needed
            while True:
                mixes_available = contract_concise.mixes_available()

                # Policy: try to maintain a buffer of mixes
                target = 10
                if mixes_available < target:
                    break
                # already have enough triples/bits, sleep
                await asyncio.sleep(5)

            # Step 1a. II) Run generate triples and generate_bits
            logging.info(
                f"[{self.myid}] mixes available: {mixes_available} \
                   target: {target}"
            )
            logging.info(f"[{self.myid}] Initiating Triples {PER_MIX_TRIPLES}")
            send, recv = self.get_send_recv(f"preproc:mixes:triples:{preproc_round}")
            start_time = time.time()
            triples = await generate_triples(
                n, t, PER_MIX_TRIPLES, self.myid, send, recv, field
            )
            end_time = time.time()
            logging.info(f"[{self.myid}] Triples finished in {end_time-start_time}")

            # Bits
            logging.info(f"[{self.myid}] Initiating Bits {PER_MIX_BITS}")
            send, recv = self.get_send_recv(f"preproc:mixes:bits:{preproc_round}")
            start_time = time.time()
            bits = await generate_bits(n, t, PER_MIX_BITS, self.myid, send, recv, field)
            end_time = time.time()
            logging.info(f"[{self.myid}] Bits finished in {end_time-start_time}")

            # Append each triple
            self._triples += triples
            self._bits += bits

            # Step 1a. III) Submit an updated report
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1

    async def _offline_inputmasks_loop(self):
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()
        K = contract_concise.K()  # noqa: N806
        preproc_round = 0
        k = K // (n - 2 * t)  # batch size
        while True:
            # Step 1b. I) Wait until needed
            while True:
                inputmasks_available = contract_concise.inputmasks_available()
                totalmasks = contract_concise.preprocess()[2]
                # Policy: try to maintain a buffer of 10 * K input masks
                target = 10 * K
                if inputmasks_available < target:
                    break
                # already have enough input masks, sleep
                await asyncio.sleep(5)

            # Step 1b. II) Run Randousha
            logging.info(
                f"[{self.myid}] totalmasks: {totalmasks} \
                inputmasks available: {inputmasks_available} \
                target: {target} Initiating Randousha {k * (n - 2*t)}"
            )
            send, recv = self.get_send_recv(f"preproc:inputmasks:{preproc_round}")
            start_time = time.time()
            rs_t, rs_2t = zip(*await randousha(n, t, k, self.myid, send, recv, field))
            assert len(rs_t) == len(rs_2t) == k * (n - 2 * t)

            # Note: here we just discard the rs_2t
            # In principle both sides of randousha could be used with
            # a small modification to randousha
            end_time = time.time()
            logging.info(f"[{self.myid}] Randousha finished in {end_time-start_time}")
            self._inputmasks += rs_t

            # Step 1b. III) Submit an updated report
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1

    async def _client_request_loop(self):
        # Task 2. Handling client input
        # TODO: if a client requests a share,
        # check if it is authorized and if so send it along
        pass

    async def _mixing_loop(self):
        # Task 3. Participating in mixing epochs
        contract_concise = ConciseContract(self.contract)
        pp_elements = PreProcessedElements()
        n = contract_concise.n()
        t = contract_concise.t()
        K = contract_concise.K()  # noqa: N806
        PER_MIX_TRIPLES = contract_concise.PER_MIX_TRIPLES()  # noqa: N806
        PER_MIX_BITS = contract_concise.PER_MIX_BITS()  # noqa: N806

        epoch = 0
        while True:
            # 3.a. Wait for the next mix to be initiated
            while True:
                epochs_initiated = contract_concise.epochs_initiated()
                if epochs_initiated > epoch:
                    break
                await asyncio.sleep(5)

            # 3.b. Collect the inputs
            inputs = []
            for idx in range(epoch * K, (epoch + 1) * K):
                # Get the public input
                masked_input, inputmask_idx = contract_concise.input_queue(idx)
                masked_input = field(int.from_bytes(masked_input, "big"))
                # Get the input masks
                inputmask = self._inputmasks[inputmask_idx]

                m_share = masked_input - inputmask
                inputs.append(m_share)

            # 3.c. Collect the preprocessing
            triples = self._triples[
                (epoch + 0) * PER_MIX_TRIPLES : (epoch + 1) * PER_MIX_TRIPLES
            ]
            bits = self._bits[(epoch + 0) * PER_MIX_BITS : (epoch + 1) * PER_MIX_BITS]

            # Hack explanation... the relevant mixins are in triples
            key = (self.myid, n, t)
            for mixin in (pp_elements._triples, pp_elements._one_minus_ones):
                if key in mixin.cache:
                    del mixin.cache[key]
                    del mixin.count[key]

            # 3.d. Call the MPC program
            async def prog(ctx):
                pp_elements._init_data_dir()

                # Overwrite triples and one_minus_ones
                for kind, elems in zip(("triples", "one_minus_one"), (triples, bits)):
                    if kind == "triples":
                        elems = flatten_lists(elems)
                    elems = [e.value for e in elems]

                    mixin = pp_elements.mixins[kind]
                    mixin_filename = mixin.build_filename(ctx.N, ctx.t, ctx.myid)
                    mixin._write_preprocessing_file(
                        mixin_filename, ctx.t, ctx.myid, elems, append=False
                    )

                pp_elements._init_mixins()

                logging.info(f"[{ctx.myid}] Running permutation network")
                inps = list(map(ctx.Share, inputs))
                assert len(inps) == K

                shuffled = await iterated_butterfly_network(ctx, inps, K)
                shuffled_shares = ctx.ShareArray(list(map(ctx.Share, shuffled)))

                opened_values = await shuffled_shares.open()
                msgs = [
                    m.value.to_bytes(32, "big").decode().strip("\x00")
                    for m in opened_values
                ]

                return msgs

            send, recv = self.get_send_recv(f"mpc:{epoch}")
            logging.info(f"[{self.myid}] MPC initiated:{epoch}")

            # Config just has to specify mixins used by switching_network
            config = {MixinConstants.MultiplyShareArray: BeaverMultiplyArrays()}

            ctx = Mpc(f"mpc:{epoch}", n, t, self.myid, send, recv, prog, config)
            result = await ctx._run()
            logging.info(f"[{self.myid}] MPC complete {result}")

            # 3.e. Output the published messages to contract
            result = ",".join(result)
            tx_hash = self.contract.functions.propose_output(epoch, result).transact(
                {"from": self.w3.eth.accounts[self.myid]}
            )
            tx_receipt = await wait_for_receipt(self.w3, tx_hash)
            rich_logs = self.contract.events.MixOutput().processReceipt(tx_receipt)
            if rich_logs:
                epoch = rich_logs[0]["args"]["epoch"]
                output = rich_logs[0]["args"]["output"]
                logging.info(f"[{self.myid}] MIX OUTPUT[{epoch}] {output}")
            else:
                pass

            epoch += 1

        pass

    async def _mixing_initiate_loop(self):
        # Task 4. Initiate mixing epochs
        contract_concise = ConciseContract(self.contract)
        K = contract_concise.K()  # noqa: N806
        while True:
            # Step 4.a. Wait until there are k values then call initiate_mix
            while True:
                inputs_ready = contract_concise.inputs_ready()
                mixes_avail = contract_concise.mixes_available()
                if inputs_ready >= K and mixes_avail >= 1:
                    break
                await asyncio.sleep(5)

            # Step 4.b. Call initiate mix
            tx_hash = self.contract.functions.initiate_mix().transact(
                {"from": self.w3.eth.accounts[0]}
            )
            tx_receipt = await wait_for_receipt(self.w3, tx_hash)
            rich_logs = self.contract.events.MixingEpochInitiated().processReceipt(
                tx_receipt
            )
            if rich_logs:
                epoch = rich_logs[0]["args"]["epoch"]
                logging.info(f"[{self.myid}] Mixing epoch initiated: {epoch}")
            else:
                logging.info(f"[{self.myid}] initiate_mix failed (redundant?)")
            await asyncio.sleep(10)


###############
# Ganache test
###############


async def main_loop(w3):
    pp_elements = PreProcessedElements()
    # deletes sharedata/ if present
    pp_elements.clear_preprocessing()

    # Step 1.
    # Create the coordinator contract and web3 interface to it
    compiled_sol = compile_source(
        open(os.path.join(os.path.dirname(__file__), "asynchromix.sol")).read()
    )  # Compiled source code
    contract_interface = compiled_sol["<stdin>:AsynchromixCoordinator"]
    contract_class = w3.eth.contract(
        abi=contract_interface["abi"], bytecode=contract_interface["bin"]
    )
    # tx_hash = contract_class.constructor(w3.eth.accounts[:7],2).transact(
    #   {'from':w3.eth.accounts[0]})  # n=7, t=2

    tx_hash = contract_class.constructor(w3.eth.accounts[:4], 1).transact(
        {"from": w3.eth.accounts[0]}
    )  # n=4, t=1

    # Get tx receipt to get contract address
    tx_receipt = await wait_for_receipt(w3, tx_hash)
    contract_address = tx_receipt["contractAddress"]

    if w3.eth.getCode(contract_address) == b"":
        logging.critical("code was empty 0x, constructor may have run out of gas")
        raise ValueError

    # Contract instance in concise mode
    abi = contract_interface["abi"]
    contract = w3.eth.contract(address=contract_address, abi=abi)
    contract_concise = ConciseContract(contract)

    # Call read only methods to check
    n = contract_concise.n()

    # Step 2: Create the servers
    router = SimpleRouter(n)
    sends, recvs = router.sends, router.recvs
    servers = [
        AsynchromixServer("sid", i, sends[i], recvs[i], w3, contract) for i in range(n)
    ]

    # Step 3. Create the client
    async def req_mask(i, idx):
        # client requests input mask {idx} from server {i}
        return servers[i]._inputmasks[idx]

    client = AsynchromixClient("sid", "client", None, None, w3, contract, req_mask)

    # Step 4. Wait for conclusion
    for i, server in enumerate(servers):
        await server.join()
    await client.join()


@contextmanager
def run_and_terminate_process(*args, **kwargs):
    try:
        p = subprocess.Popen(*args, **kwargs)
        yield p
    finally:
        logging.info(f"Killing ganache-cli {p.pid}")
        p.terminate()  # send sigterm, or ...
        p.kill()  # send sigkill
        p.wait()
        logging.info("done")


def run_eth():
    w3 = Web3(HTTPProvider())  # Connect to localhost:8545
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    try:
        logging.info("entering loop")
        loop.run_until_complete(asyncio.gather(main_loop(w3)))
    finally:
        logging.info("closing")
        loop.close()


def test_asynchromix():
    import time

    # cmd = 'testrpc -a 50 2>&1 | tee -a acctKeys.json'
    # with run_and_terminate_process(cmd, shell=True,
    # stdout=sys.stdout, stderr=sys.stderr) as proc:
    cmd = "ganache-cli -p 8545 -a 50 -b 1 > acctKeys.json 2>&1"
    logging.info(f"Running {cmd}")
    with run_and_terminate_process(cmd, shell=True):
        time.sleep(5)
        run_eth()


if __name__ == "__main__":
    # Launch an ethereum test chain
    test_asynchromix()
