import asyncio
from collections import defaultdict
import logging

from honeybadgermpc.exceptions import RedundantMessageError, AbandonedNodeError


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
# logger.setLevel(logging.NOTSET)


def handle_conf_messages(*, sender, message, conf_values, pid, bv_signal):
    _, r, v = message
    assert v in ((0,), (1,), (0, 1))
    if sender in conf_values[r][v]:
        logger.warning(
            f"[{pid}] Redundant CONF received {message} by {sender}",
            extra={"nodeid": pid, "epoch": r},
        )
        # FIXME: Raise for now to simplify things & be consistent
        # with how other TAGs are handled. Will replace the raise
        # with a continue statement as part of
        # https://github.com/initc3/HoneyBadgerBFT-Python/issues/10
        raise RedundantMessageError("Redundant CONF received {}".format(message))

    conf_values[r][v].add(sender)
    logger.debug(
        f"[{pid}] add v = {v} to conf_value[{r}] = {conf_values[r]}",
        extra={"nodeid": pid, "epoch": r},
    )

    bv_signal.set()


async def wait_for_conf_values(
    *,
    pid,
    n,
    f,
    epoch,
    conf_sent,
    bin_values,
    values,
    conf_values,
    bv_signal,
    broadcast,
):
    conf_sent[epoch][tuple(values)] = True
    logger.debug(
        f"[{pid}] broadcast {('CONF', epoch, tuple(values))}",
        extra={"nodeid": pid, "epoch": epoch},
    )
    broadcast(("CONF", epoch, tuple(bin_values[epoch])))
    while True:
        logger.debug(
            f"[{pid}] looping ... conf_values[epoch] is: {conf_values[epoch]}",
            extra={"nodeid": pid, "epoch": epoch},
        )
        if 1 in bin_values[epoch] and len(conf_values[epoch][(1,)]) >= n - f:
            return set((1,))
        if 0 in bin_values[epoch] and len(conf_values[epoch][(0,)]) >= n - f:
            return set((0,))
        if (
            sum(
                len(senders)
                for conf_value, senders in conf_values[epoch].items()
                if senders and set(conf_value).issubset(bin_values[epoch])
            )
            >= n - f
        ):
            return set((0, 1))

        bv_signal.clear()
        await bv_signal.wait()


async def binaryagreement(sid, pid, n, f, coin, input_msg, decide, broadcast, receive):
    """Binary consensus from [MMR14]. It takes an input ``vi`` and will
    finally write the decided value into ``decide`` channel.

    :param sid: session identifier
    :param pid: my id number
    :param N: the number of parties
    :param f: the number of byzantine parties
    :param coin: a ``common coin(r)`` is called to block until receiving a bit
    :param input: ``input()`` is called to receive an input
    :param decide: ``decide(0)`` or ``decide(1)`` is eventually called
    :param broadcast: broadcast channel
    :param receive: receive channel
    :return: blocks until
    """
    # Messages received are routed to either a shared coin, the broadcast, or AUX
    est_values = defaultdict(lambda: [set(), set()])
    aux_values = defaultdict(lambda: [set(), set()])
    conf_values = defaultdict(lambda: {(0,): set(), (1,): set(), (0, 1): set()})
    est_sent = defaultdict(lambda: [False, False])
    conf_sent = defaultdict(lambda: {(0,): False, (1,): False, (0, 1): False})
    bin_values = defaultdict(set)

    # This event is triggered whenever bin_values or aux_values changes
    bv_signal = asyncio.Event()

    async def _recv():
        while True:  # not finished[pid]:
            (sender, msg) = await receive()
            logger.debug(
                f"[{pid}] receive {msg} from node {sender}",
                extra={"nodeid": pid, "epoch": msg[1]},
            )
            assert sender in range(n)
            if msg[0] == "EST":
                # BV_Broadcast message
                _, r, v = msg
                assert v in (0, 1)
                if sender in est_values[r][v]:
                    # FIXME: raise or continue? For now will raise just
                    # because it appeared first, but maybe the protocol simply
                    # needs to continue.
                    print(f"[{pid}] Redundant EST received by {sender}", msg)
                    logger.warning(
                        f"[{pid}] Redundant EST message received by {sender}: {msg}",
                        extra={"nodeid": pid, "epoch": msg[1]},
                    )
                    raise RedundantMessageError("Redundant EST received {}".format(msg))
                    # continue

                est_values[r][v].add(sender)
                # Relay after reaching first threshold
                if len(est_values[r][v]) >= f + 1 and not est_sent[r][v]:
                    est_sent[r][v] = True
                    broadcast(("EST", r, v))
                    logger.debug(
                        f"[{pid}] broadcast {('EST', r, v)}",
                        extra={"nodeid": pid, "epoch": r},
                    )

                # Output after reaching second threshold
                if len(est_values[r][v]) >= 2 * f + 1:
                    logger.debug(
                        f"[{pid}] add v = {v} to bin_value[{r}] = {bin_values[r]}",
                        extra={"nodeid": pid, "epoch": r},
                    )
                    bin_values[r].add(v)
                    logger.debug(
                        f"[{pid}] bin_values[{r}] is now: {bin_values[r]}",
                        extra={"nodeid": pid, "epoch": r},
                    )
                    bv_signal.set()

            elif msg[0] == "AUX":
                # Aux message
                _, r, v = msg
                assert v in (0, 1)
                if sender in aux_values[r][v]:
                    # FIXME: raise or continue? For now will raise just
                    # because it appeared first, but maybe the protocol simply
                    # needs to continue.
                    print("Redundant AUX received", msg)
                    raise RedundantMessageError("Redundant AUX received {}".format(msg))

                logger.debug(
                    f"[{pid}] add sender = {sender} to aux_value[{r}][{v}] = \
                        {aux_values[r][v]}",
                    extra={"nodeid": pid, "epoch": r},
                )
                aux_values[r][v].add(sender)
                logger.debug(
                    f"[{pid}] aux_value[{r}][{v}] is now: {aux_values[r][v]}",
                    extra={"nodeid": pid, "epoch": r},
                )

                bv_signal.set()

            elif msg[0] == "CONF":
                handle_conf_messages(
                    sender=sender,
                    message=msg,
                    conf_values=conf_values,
                    pid=pid,
                    bv_signal=bv_signal,
                )

    # Run the receive loop in the background
    _thread_recv = asyncio.create_task(_recv())
    try:
        # Block waiting for the input
        vi = await input_msg()
        assert vi in (0, 1)
        est = vi
        r = 0
        already_decided = None
        while True:  # Unbounded number of rounds
            logger.debug(
                f"[{pid}] Starting with est = {est}", extra={"nodeid": pid, "epoch": r}
            )

            if not est_sent[r][est]:
                est_sent[r][est] = True
                broadcast(("EST", r, est))

            while len(bin_values[r]) == 0:
                # Block until a value is output
                bv_signal.clear()
                await bv_signal.wait()

            w = next(iter(bin_values[r]))  # take an element
            logger.debug(
                f"[{pid}] broadcast {('AUX', r, w)}", extra={"nodeid": pid, "epoch": r}
            )
            broadcast(("AUX", r, w))

            values = None
            logger.debug(
                f"block until at least N-f ({n-f}) AUX values are received",
                extra={"nodeid": pid, "epoch": r},
            )
            while True:
                logger.debug(
                    f"[{pid}] bin_values[{r}]: {bin_values[r]}",
                    extra={"nodeid": pid, "epoch": r},
                )
                logger.debug(
                    f"[{pid}] aux_values[{r}]: {aux_values[r]}",
                    extra={"nodeid": pid, "epoch": r},
                )
                # Block until at least N-f AUX values are received
                if 1 in bin_values[r] and len(aux_values[r][1]) >= n - f:
                    values = set((1,))
                    # print('[sid:%s] [pid:%d] VALUES 1 %d' % (sid, pid, r))
                    break
                if 0 in bin_values[r] and len(aux_values[r][0]) >= n - f:
                    values = set((0,))
                    # print('[sid:%s] [pid:%d] VALUES 0 %d' % (sid, pid, r))
                    break
                if sum(len(aux_values[r][v]) for v in bin_values[r]) >= n - f:
                    values = set((0, 1))
                    # print('[sid:%s] [pid:%d] VALUES BOTH %d' % (sid, pid, r))
                    break
                bv_signal.clear()
                await bv_signal.wait()

            logger.debug(
                f"[{pid}] Completed AUX phase with values = {values}",
                extra={"nodeid": pid, "epoch": r},
            )

            # CONF phase
            logger.debug(
                f"[{pid}] block until at least N-f ({n-f}) CONF values\
                are received",
                extra={"nodeid": pid, "epoch": r},
            )
            if not conf_sent[r][tuple(values)]:
                values = await wait_for_conf_values(
                    pid=pid,
                    n=n,
                    f=f,
                    epoch=r,
                    conf_sent=conf_sent,
                    bin_values=bin_values,
                    values=values,
                    conf_values=conf_values,
                    bv_signal=bv_signal,
                    broadcast=broadcast,
                )
            logger.debug(
                f"[{pid}] Completed CONF phase with values = {values}",
                extra={"nodeid": pid, "epoch": r},
            )

            logger.debug(
                f"[{pid}] Block until receiving the common coin value",
                extra={"nodeid": pid, "epoch": r},
            )
            # Block until receiving the common coin value
            s = await coin(r)
            logger.debug(
                f"[{pid}] Received coin with value = {s}",
                extra={"nodeid": pid, "epoch": r},
            )

            try:
                est, already_decided = set_new_estimate(
                    values=values, s=s, already_decided=already_decided, decide=decide
                )
            except AbandonedNodeError:
                # print('[sid:%s] [pid:%d] QUITTING in round %d' % (sid,pid,r))
                logger.debug(f"[{pid}] QUIT!", extra={"nodeid": pid, "epoch": r})
                return

            r += 1
    finally:
        if asyncio.get_event_loop().is_running():
            _thread_recv.cancel()


def set_new_estimate(*, values, s, already_decided, decide):
    if len(values) == 1:
        v = next(iter(values))
        if v == s:
            if already_decided is None:
                already_decided = v
                decide(v)
            elif already_decided == v:
                # Here corresponds to a proof that if one party
                # decides at round r, then in all the following
                # rounds, everybody will propose r as an
                # estimation. (Lemma 2, Lemma 1) An abandoned
                # party is a party who has decided but no enough
                # peers to help him end the loop.  Lemma: # of
                # abandoned party <= t
                raise AbandonedNodeError
        est = v
    else:
        est = s
    return est, already_decided


async def run_binary_agreement(config, pbk, pvk, n, f, nodeid):
    from honeybadgermpc.broadcast.commoncoin import shared_coin
    import random

    sid_c = "sid_coin"
    sid_ba = "sid_ba"

    async with ProcessProgramRunner(config, n, f, nodeid) as program_runner:
        send_c, recv_c = program_runner.get_send_recv(sid_c)

        def bcast_c(o):
            for i in range(n):
                send_c(i, o)

        coin, crecv_task = await shared_coin(
            sid_c, nodeid, n, f, pbk, pvk, bcast_c, recv_c
        )

        inputq = asyncio.Queue()
        outputq = asyncio.Queue()

        send_ba, recv_ba = program_runner.get_send_recv(sid_ba)

        def bcast_ba(o):
            for i in range(n):
                send_ba(i, o)

        ba_task = binaryagreement(
            sid_ba,
            nodeid,
            n,
            f,
            coin,
            inputq.get,
            outputq.put_nowait,
            bcast_ba,
            recv_ba,
        )

        inputq.put_nowait(random.randint(0, 1))

        await ba_task

        logger.info("[%d] BA VALUE: %s", nodeid, await outputq.get())
        # logger.info("[%d] COIN VALUE: %s", nodeid, await coin(0))
        crecv_task.cancel()


if __name__ == "__main__":
    import pickle
    import base64
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
            run_binary_agreement(
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
