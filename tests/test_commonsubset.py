import random
import asyncio
from pytest import mark

from honeybadgermpc.broadcast.commoncoin import shared_coin
from honeybadgermpc.broadcast.binaryagreement import binaryagreement
from honeybadgermpc.broadcast.reliablebroadcast import reliablebroadcast
from honeybadgermpc.broadcast.commonsubset import commonsubset
from honeybadgermpc.broadcast.crypto.boldyreva import dealer


# Make the threshold signature common coins
async def make_commonsubset(sid, pid, n, f, pk, sk, input_msg, send, recv, bcast):

    coin_recvs = [None] * n
    aba_recvs = [None] * n
    rbc_recvs = [None] * n

    aba_inputs = [asyncio.Queue(1) for _ in range(n)]
    aba_outputs = [asyncio.Queue(1) for _ in range(n)]
    rbc_outputs = [asyncio.Queue(1) for _ in range(n)]

    async def _recv():
        while True:
            (sender, (tag, j, msg)) = await recv()
            if tag == "ACS_COIN":
                coin_recvs[j].put_nowait((sender, msg))
            elif tag == "ACS_RBC":
                rbc_recvs[j].put_nowait((sender, msg))
            elif tag == "ACS_ABA":
                aba_recvs[j].put_nowait((sender, msg))
            else:
                raise ValueError("Unknown tag: %s", tag)

    recv_tasks = []
    recv_tasks.append(asyncio.create_task(_recv()))

    async def _setup(j):
        def coin_bcast(o):
            bcast(("ACS_COIN", j, o))

        coin_recvs[j] = asyncio.Queue()
        coin, coin_recv_task = await shared_coin(
            sid + "COIN" + str(j), pid, n, f, pk, sk, coin_bcast, coin_recvs[j].get
        )

        def aba_bcast(o):
            bcast(("ACS_ABA", j, o))

        aba_recvs[j] = asyncio.Queue()
        aba_task = asyncio.create_task(
            binaryagreement(
                sid + "ABA" + str(j),
                pid,
                n,
                f,
                coin,
                aba_inputs[j].get,
                aba_outputs[j].put_nowait,
                aba_bcast,
                aba_recvs[j].get,
            )
        )

        def rbc_send(k, o):
            send(k, ("ACS_RBC", j, o))

        # Only leader gets input
        rbc_input = await input_msg() if j == pid else None
        rbc_recvs[j] = asyncio.Queue()
        rbc_outputs[j] = asyncio.create_task(
            reliablebroadcast(
                sid + "RBC" + str(j),
                pid,
                n,
                f,
                j,
                rbc_input,
                rbc_recvs[j].get,
                rbc_send,
            )
        )

        return coin_recv_task, aba_task

    returned_tasks = await asyncio.gather(*[_setup(j) for j in range(n)])
    work_tasks = []
    for c_task, rcv_task in returned_tasks:
        recv_tasks.append(c_task)
        work_tasks.append(rcv_task)

    return (
        commonsubset(
            pid,
            n,
            f,
            rbc_outputs,
            [_.put_nowait for _ in aba_inputs],
            [_.get for _ in aba_outputs],
        ),
        recv_tasks,
        work_tasks,
    )


@mark.asyncio
async def test_commonsubset(test_router):
    n, f, seed = 4, 1, None
    # Generate keys
    sid = "sidA"
    pk, sks = dealer(n, f + 1, seed=seed)
    rnd = random.Random(seed)
    # print('SEED:', seed)
    router_seed = rnd.random()
    sends, recvs, bcasts = test_router(n, seed=router_seed)

    inputs = [None] * n
    threads = [None] * n
    for i in range(n):
        inputs[i] = asyncio.Queue(1)

        threads[i] = make_commonsubset(
            sid, i, n, f, pk, sks[i], inputs[i].get, sends[i], recvs[i], bcasts[i]
        )

    await asyncio.gather(*[inputs[i].put("<[ACS Input %d]>" % i) for i in range(n)])
    results = await asyncio.gather(*threads)
    acs, recv_task_lists, work_task_lists = zip(*results)
    outs = await asyncio.gather(*acs)
    for work_task_list in work_task_lists:
        await asyncio.gather(*work_task_list)
    for recv_task_list in recv_task_lists:
        for task in recv_task_list:
            task.cancel()
    assert len(set(outs)) == 1
