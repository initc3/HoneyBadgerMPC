import asyncio
import logging


async def commonsubset(pid, n, f, rbc_out, aba_in, aba_out):
    """The BKR93 algorithm for asynchronous common subset.

    :param pid: my identifier
    :param N: number of nodes
    :param f: fault tolerance
    :param rbc_out: an array of :math:`N` (blocking) output functions,
        returning a string
    :param aba_in: an array of :math:`N` (non-blocking) functions that
        accept an input bit
    :param aba_out: an array of :math:`N` (blocking) output functions,
        returning a bit
    :return: an :math:`N`-element array, each element either ``None`` or a
        string
    """
    assert len(rbc_out) == n
    assert len(aba_in) == n
    assert len(aba_out) == n

    aba_inputted = [False] * n
    aba_values = [0] * n
    rbc_values = [None] * n

    async def _recv_rbc(j):
        # Receive output from reliable broadcast
        rbc_values[j] = await rbc_out[j]

        if not aba_inputted[j]:
            # Provide 1 as input to the corresponding bin agreement
            aba_inputted[j] = True
            aba_in[j](1)

    r_threads = [asyncio.create_task(_recv_rbc(j)) for j in range(n)]

    async def _recv_aba(j):
        # Receive output from binary agreement
        aba_values[j] = await aba_out[j]()  # May block
        # print pid, j, 'ENTERING CRITICAL'
        if sum(aba_values) >= n - f:
            # Provide 0 to all other aba
            for k in range(n):
                if not aba_inputted[k]:
                    aba_inputted[k] = True
                    aba_in[k](0)
                    # print pid, 'ABA[%d] input -> %d' % (k, 0)
        # print pid, j, 'EXITING CRITICAL'

    # Wait for all binary agreements
    await asyncio.gather(*[asyncio.create_task(_recv_aba(j)) for j in range(n)])

    assert sum(aba_values) >= n - f  # Must have at least N-f committed

    # Wait for the corresponding broadcasts
    for j in range(n):
        if aba_values[j]:
            await r_threads[j]
            assert rbc_values[j] is not None
        else:
            r_threads[j].cancel()
            rbc_values[j] = None

    return tuple(rbc_values)


async def make_commonsubset(sid, pid, n, f, pk, sk, input_msg, send, recv, bcast):
    from honeybadgermpc.protocols.commoncoin import shared_coin
    from honeybadgermpc.protocols.binaryagreement import binaryagreement
    from honeybadgermpc.protocols.reliablebroadcast import reliablebroadcast

    coin_recvs = [None] * n
    aba_recvs = [None] * n
    rbc_recvs = [None] * n

    aba_inputs = [asyncio.Queue(1) for _ in range(n)]
    aba_outputs = [asyncio.Queue(1) for _ in range(n)]
    rbc_outputs = [asyncio.Queue(1) for _ in range(n)]

    async def _recv():
        while True:
            (sender, (tag, j, msg)) = await recv()
            if tag == 'ACS_COIN':
                coin_recvs[j].put_nowait((sender, msg))
            elif tag == 'ACS_RBC':
                rbc_recvs[j].put_nowait((sender, msg))
            elif tag == 'ACS_ABA':
                aba_recvs[j].put_nowait((sender, msg))
            else:
                raise ValueError("Unknown tag: %s", tag)

    recv_tasks = []
    recv_tasks.append(asyncio.create_task(_recv()))

    async def _setup(j):
        def coin_bcast(o):
            bcast(('ACS_COIN', j, o))

        coin_recvs[j] = asyncio.Queue()
        coin, coin_recv_task = await shared_coin(
            sid + 'COIN' + str(j), pid, n, f, pk, sk, coin_bcast, coin_recvs[j].get)

        def aba_bcast(o):
            bcast(('ACS_ABA', j, o))

        aba_recvs[j] = asyncio.Queue()
        aba_task = asyncio.create_task(
            binaryagreement(sid+'ABA'+str(j), pid, n, f, coin, aba_inputs[j].get,
                            aba_outputs[j].put_nowait, aba_bcast, aba_recvs[j].get))

        def rbc_send(k, o):
            send(k, ('ACS_RBC', j, o))

        # Only leader gets input
        rbc_input = await input_msg() if j == pid else None
        rbc_recvs[j] = asyncio.Queue()
        rbc_outputs[j] = asyncio.create_task(
            reliablebroadcast(sid+'RBC'+str(j), pid, n, f, j, rbc_input,
                              rbc_recvs[j].get, rbc_send))

        return coin_recv_task, aba_task

    returned_tasks = await asyncio.gather(*[_setup(j) for j in range(n)])
    work_tasks = []
    for c_task, rcv_task in returned_tasks:
        recv_tasks.append(c_task)
        work_tasks.append(rcv_task)

    return commonsubset(pid, n, f, rbc_outputs, [_.put_nowait for _ in aba_inputs],
                        [_.get for _ in aba_outputs]), recv_tasks, work_tasks


async def run_common_subset(config, pbk, pvk, n, f, nodeid):
    sid = 'sidA'

    program_runner = ProcessProgramRunner(config, n, t, nodeid)
    sender, listener = program_runner.senders, program_runner.listener
    await sender.connect()

    send, recv = program_runner.get_send_and_recv(sid)

    def bcast(o):
        for i in range(n):
            send(i, o)

    input_q = asyncio.Queue(1)

    create_acs_task = asyncio.create_task(
        make_commonsubset(sid, nodeid, n, f, pbk, pvk, input_q.get, send, recv, bcast))

    await input_q.put('<[ACS Input %d]>' % nodeid)
    acs, recv_tasks, work_tasks = await create_acs_task
    acs_output = await acs
    await asyncio.gather(*work_tasks)
    for task in recv_tasks:
        task.cancel()

    logging.info(f"OUTPUT: {acs_output}")
    await sender.close()
    await listener.close()


if __name__ == "__main__":
    import os
    import sys
    import pickle
    import base64
    from honeybadgermpc.exceptions import ConfigurationError
    from honeybadgermpc.config import load_config
    from honeybadgermpc.ipc import NodeDetails, ProcessProgramRunner
    from honeybadgermpc.protocols.crypto.boldyreva import TBLSPublicKey  # noqa:F401
    from honeybadgermpc.protocols.crypto.boldyreva import TBLSPrivateKey  # noqa:F401

    configfile = os.environ.get('HBMPC_CONFIG')
    nodeid = os.environ.get('HBMPC_NODE_ID')
    pvk_string = os.environ.get('HBMPC_PV_KEY')
    pbk_string = os.environ.get('HBMPC_PB_KEY')

    # override configfile if passed to command
    try:
        nodeid = sys.argv[1]
        configfile = sys.argv[2]
        pbk_string = sys.argv[3]
        pvk_string = sys.argv[4]
    except IndexError:
        pass

    if not nodeid:
        raise ConfigurationError('Environment variable `HBMPC_NODE_ID` must be set'
                                 ' or a node id must be given as first argument.')

    if not configfile:
        raise ConfigurationError('Environment variable `HBMPC_CONFIG` must be set'
                                 ' or a config file must be given as first argument.')

    if not pvk_string:
        raise ConfigurationError('Environment variable `HBMPC_PV_KEY` must be set'
                                 ' or a config file must be given as first argument.')

    if not pbk_string:
        raise ConfigurationError('Environment variable `HBMPC_PB_KEY` must be set'
                                 ' or a config file must be given as first argument.')

    config_dict = load_config(configfile)
    n = config_dict['N']
    t = config_dict['t']
    k = config_dict['k']
    pbk = pickle.loads(base64.b64decode(pbk_string))
    pvk = pickle.loads(base64.b64decode(pvk_string))
    nodeid = int(nodeid)
    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(run_common_subset(network_info, pbk, pvk, n, t, nodeid))
    except asyncio.CancelledError:
        print("CANCELLED")
    finally:
        loop.close()
