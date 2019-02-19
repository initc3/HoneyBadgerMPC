import logging

from honeybadgermpc.protocols.crypto.boldyreva import serialize
import asyncio
from collections import defaultdict
import hashlib


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
    assert pk.k == f+1
    assert pk.l == n    # noqa: E741
    received = defaultdict(dict)
    output_queue = defaultdict(lambda: asyncio.Queue(1))

    async def _recv():
        while True:     # main receive loop
            logging.debug(f'entering loop', extra={'nodeid': pid, 'epoch': '?'})
            # New shares for some round r, from sender i
            (i, (_, r, sig)) = await receive()
            logging.debug(
                          f'received i, _, r, sig: {i, _, r, sig}',
                          extra={'nodeid': pid, 'epoch': r})
            assert i in range(n)
            assert r >= 0
            if i in received[r]:
                print("redundant coin sig received", (sid, pid, i, r))
                continue

            h = pk.hash_message(str((sid, r)))

            # TODO: Accountability: Optimistically skip verifying
            # each share, knowing evidence available later
            try:
                pk.verify_share(sig, i, h)
            except AssertionError:
                print("Signature share failed!", (sid, pid, i, r))
                continue

            received[r][i] = sig

            # After reaching the threshold, compute the output and
            # make it available locally
            logging.debug(
                f'if len(received[r]) == f + 1: {len(received[r]) == f + 1}',
                extra={'nodeid': pid, 'epoch': r},
            )
            if len(received[r]) == f + 1:

                # Verify and get the combined signature
                sigs = dict(list(received[r].items())[:f+1])
                sig = pk.combine_shares(sigs)
                assert pk.verify_signature(sig, h)

                # Compute the bit from the least bit of the hash
                bit = hash(serialize(sig))[0] % 2
                logging.debug(
                    f'put bit {bit} in output queue', extra={'nodeid': pid, 'epoch': r})
                output_queue[r].put_nowait(bit)

    recv_task = asyncio.create_task(_recv())

    async def get_coin(round):
        """Gets a coin.

        :param round: the epoch/round.
        :returns: a coin.

        """
        # I have to do mapping to 1..l
        h = pk.hash_message(str((sid, round)))
        logging.debug(
                      f"broadcast {('COIN', round, sk.sign(h))}",
                      extra={'nodeid': pid, 'epoch': round})
        broadcast(('COIN', round, sk.sign(h)))
        return await output_queue[round].get()

    return get_coin, recv_task
