import asyncio
# import logging


def simple_router(n):
    """
    Builds a set of connected channels
    @return (receives, sends)
    """
    # Create a mailbox for each party
    mbox = [asyncio.Queue() for _ in range(n)]

    def make_send(i):
        def _send(j, o):
            # logging.debug('SEND %8s [%2d -> %2d]' % (o, i, j))
            # delay = random.random() * 1.0
            # asyncio.get_event_loop().call_later(delay, mbox[j].put_nowait,(i,o))
            mbox[j].put_nowait((i, o))

        return _send

    def make_recv(j):
        async def _recv():
            (i, o) = await mbox[j].get()
            # logging.debug('RECV %8s [%2d -> %2d]' % (o, i, j))
            return (i, o)

        return _recv

    sends = {}
    receives = {}
    for i in range(n):
        sends[i] = make_send(i)
        receives[i] = make_recv(i)
    return (sends, receives)
