import os
import pickle
import asyncio
import sys
import struct
import socket

from .passive import PassiveMpc


class Senders(object):
    def __init__(self, queues, config):
        self.queues = queues
        self.config = config

    async def connect(self):
        # Setup all connections first before sending messages

        # XXX BEGIN temporary hack
        # ``socket.getaddrinfo``, called in open_connection may fail thus causing an
        # unhandled exception.
        # A connection management mechanism is needed to that failed connections are
        # re-tried etc.
        # Basically nodes should be capable to join when they try to connect but if late
        # it should not crash the whole thing, or more precisely prevent other nodes
        # from participating in the protocol.
        while True:
            try:
                addrinfo_list = [
                    socket.getaddrinfo(self.config[i].ip, self.config[i].port)[0][4]
                    for i in range(len(self.queues))
                ]
            except socket.gaierror:
                continue
            else:
                break
        # XXX END temporary hack

        streams = [asyncio.open_connection(
                addrinfo_list[i][0],
                addrinfo_list[i][1],
            ) for i in range(len(self.queues))]
        streams = await asyncio.gather(*streams)
        writers = [stream[1] for stream in streams]

        # Setup tasks to consume messages from queues
        # This is to ensure that messages are delivered in the correct order
        for i, q in enumerate(self.queues):
            recvid = "%s:%d" % (self.config[i].ip, self.config[i].port)
            asyncio.ensure_future(self.process_queue(writers[i], q, recvid))

    async def process_queue(self, writer, q, recvid):
        try:
            while True:
                msg = await q.get()
                if msg is None:
                    print('Close the connection')
                    writer.close()
                    await writer.wait_closed()
                    break
                # print('SEND %8s [%2d -> %s]' % (msg[1][0], msg[0], recvid))
                data = pickle.dumps(msg)
                padded_msg = struct.pack('>I', len(data)) + data
                writer.write(padded_msg)
                await writer.drain()
        except ConnectionResetError:
            print("WARNING: Connection with peer [%s] reset." % recvid)
        except ConnectionRefusedError:
            print("WARNING: Connection with peer [%s] refused." % recvid)
        except BrokenPipeError:
            print("WARNING: Connection with peer [%s] broken." % recvid)

    def close(self):
        for q in self.queues:
            q.put_nowait(None)


class Listener(object):
    def __init__(self, q, port):
        self.q = q
        serverFuture = asyncio.start_server(self.handle_client, "", port)
        self.serverTask = asyncio.ensure_future(serverFuture)
        self.tasks = []

    async def handle_client(self, reader, writer):
        self.tasks.append(asyncio.current_task())
        # print("Received new connection", writer.get_extra_info("peername"))
        while True:
            raw_msglen = await self.recvall(reader, 4)
            if raw_msglen is None:
                break
            msglen = struct.unpack('>I', raw_msglen)[0]
            received_raw_msg = await self.recvall(reader, msglen)
            if received_raw_msg is None:
                break
            received_msg = pickle.loads(received_raw_msg)
            # print('RECV %8s [from %2d]' % (received_msg[1][0], received_msg[0]))
            await self.q.put(received_msg)

    async def recvall(self, reader, n):
        # Helper function to recv n bytes or return None if EOF is hit
        data = b''
        while len(data) < n:
            packet = await reader.read(n)
            if len(packet) == 0:
                return None
            data += packet
        return data

    async def getMessage(self):
        return await self.q.get()

    async def close(self):
        server = await self.serverTask
        server.close()
        await server.wait_closed()
        for task in self.tasks:
            task.cancel()


class NodeDetails(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


def setup_sockets(config, n, id):
    senderQueues = [asyncio.Queue() for _ in range(n)]
    sender = Senders(senderQueues, config)
    listenerQueue = asyncio.Queue()
    listener = Listener(listenerQueue, config[id].port)

    def makeSend(i):
        def _send(j, o):
            # print('SEND %8s [%2d -> %2d]' % (o[0], i, j))
            if i == j:
                # If attempting to send the message to yourself
                # then skip the network stack.
                listenerQueue.put_nowait((i, o))
            else:
                senderQueues[j].put_nowait((i, o))

        return _send

    def makeRecv(j):
        async def _recv():
            (i, o) = await listener.getMessage()
            # print('RECV %8s [%2d -> %2d]' % (o[0], i, j))
            return (i, o)
        return _recv

    return (makeSend(id), makeRecv(id), sender, listener)


async def runProgramAsProcesses(program, config, t, id):
    send, recv, sender, listener = setup_sockets(config, len(config), id)
    # Need to give time to the listener coroutine to start
    #  or else the sender will get a connection refused.

    # XXX HACK! Increase wait time. Must find better way if possible -- e.g:
    # try/except retry logic ...
    await asyncio.sleep(2)
    await sender.connect()
    await asyncio.sleep(1)
    context = PassiveMpc('sid', N, t, id, send, recv, program)
    results = await asyncio.ensure_future(context._run())
    await asyncio.sleep(1)
    sender.close()
    await listener.close()
    await asyncio.sleep(1)
    return results


if __name__ == "__main__":
    from .passive import generate_test_zeros, generate_test_triples
    from .passive import test_prog1, test_prog2
    from .exceptions import ConfigurationError
    from .config import load_config

    configfile = os.environ.get('HBMPC_CONFIG')

    # override configfile if passed to command
    try:
        configfile = sys.argv[1]
    except IndexError:
        pass

    if not configfile:
        raise ConfigurationError('Environment variable `HBMPC_CONFIG` must be set'
                                 ' or a config file must be given as first argument.')

    config_dict = load_config(configfile)
    N = config_dict['N']
    t = config_dict['t']
    nodeid = int(config_dict['nodeid'])
    host = config_dict['host']
    port = config_dict['port']
    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }
    network_info[nodeid] = NodeDetails(host, port)

    # Only one party needs to generate the initial shares
    if nodeid == 0:
        print('Generating random shares of zero in sharedata/')
        generate_test_zeros('sharedata/test_zeros', 1000, N, t)
        print('Generating random shares of triples in sharedata/')
        generate_test_triples('sharedata/test_triples', 1000, N, t)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(
            runProgramAsProcesses(test_prog1, network_info, t, nodeid))
        loop.run_until_complete(
            runProgramAsProcesses(test_prog2, network_info, t, nodeid))
    finally:
        loop.close()
