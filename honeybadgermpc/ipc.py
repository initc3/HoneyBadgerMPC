import os
import pickle
import asyncio
import sys
import struct
import socket
from .logger import BenchmarkLogger
from .passive import PassiveMpc
from .program_runner import ProgramRunner


class Senders(object):
    def __init__(self, queues, config, nodeid):
        self.queues = queues
        self.config = config
        self.totalBytesSent = 0
        self.benchlogger = BenchmarkLogger.get(nodeid)

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
                # print('[%2d] SEND %8s [%2d -> %s]' % (
                #     msg[0], msg[1][1][0], msg[1][0], recvid
                # ))
                data = pickle.dumps(msg)
                padded_msg = struct.pack('>I', len(data)) + data
                self.totalBytesSent += len(padded_msg)
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
        self.benchlogger.info("Total bytes sent out: %d", self.totalBytesSent)


class Listener(object):
    def __init__(self, port):
        self.queues = {}
        self.tasks = []
        serverFuture = asyncio.start_server(self.handle_client, "", port)
        self.serverTask = asyncio.ensure_future(serverFuture)

    def getProgramQueue(self, pid):
        assert pid not in self.queues
        self.queues[pid] = asyncio.Queue()
        return self.queues[pid]

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
            pid, received_msg = pickle.loads(received_raw_msg)
            # print('RECV %8s [from %2d]' % (received_msg[1][0], received_msg[0]))
            await self.queues[pid].put(received_msg)

    async def recvall(self, reader, n):
        # Helper function to recv n bytes or return None if EOF is hit
        data = b''
        while len(data) < n:
            packet = await reader.read(n)
            if len(packet) == 0:
                return None
            data += packet
        return data

    async def getMessage(self, pid):
        return await self.queues[pid].get()

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


class ProcessProgramRunner(ProgramRunner):
    def __init__(self, config, N, t, nodeid):
        self.config = config
        self.N, self.t, self.nodeid, self.pid = N, t, nodeid, 0
        self.senders = Senders([asyncio.Queue() for _ in range(N)], config, nodeid)
        self.listener = Listener(config[nodeid].port)
        self.programs = []

    def getSendAndRecv(self):
        listenerQueue = self.listener.getProgramQueue(self.pid)

        def makeSend(i, pid):
            def _send(j, o):
                if i == j:
                    # If attempting to send the message to yourself
                    # then skip the network stack.
                    # print('[%2d] SEND %8s [%2d -> %2d]' % (pid, o[0], i, j))
                    listenerQueue.put_nowait((i, o))
                else:
                    self.senders.queues[j].put_nowait((pid, (i, o)))
            return _send

        def makeRecv(j, pid):
            async def _recv():
                (i, o) = await self.listener.getMessage(pid)
                # print('[%2d] RECV %8s [%2d -> %2d]' % (pid, o[0], i, j))
                return (i, o)
            return _recv

        return makeSend(self.nodeid, self.pid), makeRecv(self.nodeid, self.pid)

    def add(self, program):
        send, recv = self.getSendAndRecv()
        self.pid += 1
        context = PassiveMpc('sid', N, t, self.nodeid, self.pid, send, recv, program)
        self.programs.append(asyncio.ensure_future(context._run()))
        return send, recv

    async def join(self):
        await asyncio.sleep(1)
        await self.senders.connect()
        results = await asyncio.gather(*self.programs)
        self.senders.close()
        await asyncio.sleep(1)
        await self.listener.close()
        return results


if __name__ == "__main__":
    from .passive import generate_test_zeros, generate_test_triples
    from .passive import test_prog1, test_prog2
    from .exceptions import ConfigurationError
    from .config import load_config

    configfile = os.environ.get('HBMPC_CONFIG')
    nodeid = os.environ.get('HBMPC_NODE_ID')

    # override configfile if passed to command
    try:
        nodeid = sys.argv[1]
        configfile = sys.argv[2]
    except IndexError:
        pass

    if not nodeid:
        raise ConfigurationError('Environment variable `HBMPC_NODE_ID` must be set'
                                 ' or a node id must be given as first argument.')

    if not configfile:
        raise ConfigurationError('Environment variable `HBMPC_CONFIG` must be set'
                                 ' or a config file must be given as second argument.')

    nodeid = int(nodeid)
    config_dict = load_config(configfile)
    N = config_dict['N']
    t = config_dict['t']
    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        if not config_dict['skipPreprocessing']:
            # Only one party needs to generate the initial shares
            if nodeid == 0:
                os.makedirs("sharedata", exist_ok=True)
                print('Generating random shares of zero in sharedata/')
                generate_test_zeros('sharedata/test_zeros', 1000, N, t)
                print('Generating random shares of triples in sharedata/')
                generate_test_triples('sharedata/test_triples', 1000, N, t)
            else:
                loop.run_until_complete(asyncio.sleep(1))
        programRunner = ProcessProgramRunner(network_info, N, t, nodeid)
        programRunner.add(test_prog1)
        programRunner.add(test_prog2)
        loop.run_until_complete(programRunner.join())
    finally:
        loop.close()
