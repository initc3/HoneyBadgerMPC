import logging
import base64
from honeybadgermpc.broadcast.crypto.boldyreva import serialize, deserialize1
import asyncio
from collections import defaultdict
import hashlib


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
# logger.setLevel(logging.NOTSET)


class CommonCoinFailureException(Exception):
    """Raised for common coin failures."""

    pass


def hash(x):
    return hashlib.sha256(x).digest()


async def shared_coin(sid, pid, n, f, pk, sk, broadcast, receive):
    """A shared coin based on threshold signatures

    :param sid: a unique instance id
    :param pid: my id number
    :param N: number of parties
    :param f: fault tolerance, :math:`f+1` shares needed to get the coin
    :param PK: ``boldyreva.TBLSPublicKey``
    :param SK: ``boldyreva.TBLSPrivateKey``
    :param broadcast: broadcast channel
    :param receive: receive channel
    :return: a function ``getCoin()``, where ``getCoin(r)`` blocks
    """
    assert pk.k == f + 1
    assert pk.l == n  # noqa: E741
    received = defaultdict(dict)
    output_queue = defaultdict(lambda: asyncio.Queue(1))

    async def _recv():
        while True:  # main receive loop
            logger.debug(f"[{pid}] entering loop", extra={"nodeid": pid, "epoch": "?"})
            # New shares for some round r, from sender i
            (i, (_, r, sig_bytes)) = await receive()
            sig = deserialize1(sig_bytes)
            logger.debug(
                f"[{pid}] received i, _, r, sig: {i, _, r, sig}",
                extra={"nodeid": pid, "epoch": r},
            )
            assert i in range(n)
            assert r >= 0
            if i in received[r]:
                logger.error(f"redundant coin sig received {(sid, pid, i, r)}")
                continue

            h = pk.hash_message(str((sid, r)))

            # TODO: Accountability: Optimistically skip verifying
            # each share, knowing evidence available later
            try:
                pk.verify_share(sig, i, h)
            except AssertionError:
                logger.error(f"Signature share failed! {(sid, pid, i, r)}")
                continue

            received[r][i] = sig

            # After reaching the threshold, compute the output and
            # make it available locally
            logger.debug(
                f"[{pid}] if len(received[r]) == f + 1: {len(received[r]) == f + 1}",
                extra={"nodeid": pid, "epoch": r},
            )
            if len(received[r]) == f + 1:

                # Verify and get the combined signature
                sigs = dict(list(received[r].items())[: f + 1])
                sig = pk.combine_shares(sigs)
                assert pk.verify_signature(sig, h)

                # Compute the bit from the least bit of the hash
                bit = hash(serialize(sig))[0] % 2
                logger.debug(
                    f"[{pid}] put bit {bit} in output queue",
                    extra={"nodeid": pid, "epoch": r},
                )
                output_queue[r].put_nowait(bit)

    recv_task = asyncio.create_task(_recv())

    async def get_coin(round):
        """Gets a coin.

        :param round: the epoch/round.
        :returns: a coin.

        """
        # I have to do mapping to 1..l
        h = pk.hash_message(str((sid, round)))
        logger.debug(
            f"[{pid}] broadcast {('COIN', round, sk.sign(h))}",
            extra={"nodeid": pid, "epoch": round},
        )
        broadcast(("COIN", round, serialize(sk.sign(h))))
        return await output_queue[round].get()

    return get_coin, recv_task


async def run_common_coin(config, pbk, pvk, n, f, nodeid):
    async with ProcessProgramRunner(config, n, f, nodeid) as program_runner:
        send, recv = program_runner.get_send_recv("coin")

        def broadcast(o):
            for i in range(n):
                send(i, o)

        coin, crecv_task = await shared_coin(
            "sidA", nodeid, n, f, pbk, pvk, broadcast, recv
        )
        for i in range(10):
            logger.info("[%d] %d COIN VALUE: %s", nodeid, i, await coin(i))
        crecv_task.cancel()


if __name__ == "__main__":
    import pickle
    from honeybadgermpc.config import HbmpcConfig
    from honeybadgermpc.ipc import ProcessProgramRunner
    from honeybadgermpc.broadcast.crypto.boldyreva import TBLSPublicKey  # noqa:F401
    from honeybadgermpc.broadcast.crypto.boldyreva import TBLSPrivateKey  # noqa:F401

    pbk = pickle.loads(base64.b64decode(HbmpcConfig.extras["public_key"]))
    pvk = pickle.loads(base64.b64decode(HbmpcConfig.extras["private_key"]))

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            run_common_coin(
                HbmpcConfig.peers,
                pbk,
                pvk,
                HbmpcConfig.N,
                HbmpcConfig.t,
                HbmpcConfig.my_id,
            )
        )
    finally:
        loop.close()
