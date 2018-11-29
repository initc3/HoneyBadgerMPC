import os
import pickle
import asyncio
import sys
import struct
import socket
from .logger import BenchmarkLogger
from .mpc import Mpc
from .program_runner import ProgramRunner


async def wait_for_preprocessing():
    while not os.path.exists("sharedata/READY"):
        print(f"waiting for preprocessing sharedata/READY")
        await asyncio.sleep(1)


async def robust_open_connection(host, port):
    backoff = 1
    for _ in range(4):
        try:
            return await asyncio.open_connection(host, port)
        except (ConnectionRefusedError, ConnectionResetError):
            print('backing off:', backoff, 'seconds')
            await asyncio.sleep(backoff)
            backoff *= 2


class Senders(object):
    def __init__(self, queues, config, nodeid):
        self.queues = queues
        self.config = config
        self.totalBytesSent = 0
        self.benchlogger = BenchmarkLogger.get(nodeid)
        self.tasks = []

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
                    socket.getaddrinfo(
                        self.config[i].ip, self.config[i].port)[0][4]
                    for i in range(len(self.queues))
                ]
            except socket.gaierror:
                continue
            else:
                break
        # XXX END temporary hack

        streams = [robust_open_connection(
            addrinfo_list[i][0],
            addrinfo_list[i][1],
        ) for i in range(len(self.queues))]
        streams = await asyncio.gather(*streams)
        writers = [stream[1] for stream in streams]

        # Setup tasks to consume messages from queues
        # This is to ensure that messages are delivered in the correct order
        for i, q in enumerate(self.queues):
            recvid = "%s:%d" % (self.config[i].ip, self.config[i].port)
            self.tasks.append(
                asyncio.ensure_future(self.process_queue(writers[i], q, recvid))
            )

    async def process_queue(self, writer, q, recvid):
        try:
            writer._bytesSent = 0
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=1)
                except asyncio.TimeoutError:
                    # FIXME: debug diagnostic below
                    # print('timeout sending to:', recvid,
                    #       'sent:', writer._bytesSent)
                    # Option 1: heartbeat
                    msg = "heartbeat"
                    # Option 2: no heartbeat
                    # continue

                if msg is None:
                    print('Close the connection')
                    writer.close()
                    await writer.wait_closed()
                    break
                # print('[%2d] SEND %8s [%2d -> %s]' % (
                #      msg[0], msg[1][1][0], msg[1][0], recvid
                # ))
                # time2 = os.times()
                data = pickle.dumps(msg)
                # pickle_time = str(os.times()[4] - time2[4])
                # print('pickle time ' + pickle_time)
                padded_msg = struct.pack('>I', len(data)) + data
                self.totalBytesSent += len(padded_msg)
                writer.write(padded_msg)
                await writer.drain()
                writer._bytesSent += len(padded_msg)
        except ConnectionResetError:
            print("WARNING: Connection with peer [%s] reset." % recvid)
        except ConnectionRefusedError:
            print("WARNING: Connection with peer [%s] refused." % recvid)
        except BrokenPipeError:
            print("WARNING: Connection with peer [%s] broken." % recvid)

    async def close(self):
        await asyncio.gather(*[q.put(None) for q in self.queues])
        await asyncio.gather(*self.tasks)
        self.benchlogger.info("Total bytes sent out: %d", self.totalBytesSent)


class Listener(object):
    def __init__(self, port):
        self.queues = {}
        self.tasks = []
        serverFuture = asyncio.start_server(self.handle_client, "", port)
        self.serverTask = asyncio.ensure_future(serverFuture)

    def getProgramQueue(self, sid):
        assert sid not in self.queues
        self.queues[sid] = asyncio.Queue()
        return self.queues[sid]

    def clearAllProgramQueues(self):
        self.queues = {}

    async def handle_client(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.append(task)

        def cb(future):
            try:
                future.result()
            except asyncio.CancelledError:
                print("[WARNING] handle_client was cancelled.")
                return
        task.add_done_callback(cb)

        # print("Received new connection", writer.get_extra_info("peername"))
        reader._whoFrom = None
        reader._bytesRead = 0
        while True:
            raw_msglen = await self.recvall(reader, 4)
            if raw_msglen is None:
                break
            msglen = struct.unpack('>I', raw_msglen)[0]
            received_raw_msg = await self.recvall(reader, msglen)
            if received_raw_msg is None:
                break
            unpickled = pickle.loads(received_raw_msg)
            if unpickled == "heartbeat":
                print("received heartbeat", reader._whoFrom)
                continue
            sid, received_msg = unpickled
            if reader._whoFrom is None:
                reader._whoFrom = received_msg[0]
                print(reader._whoFrom, reader)
            assert reader._whoFrom == received_msg[0]

            # print(
            #     '[%d] RECV %8s [from %2d]' % (sid, received_msg[1][0], received_msg[0])
            # )
            while sid not in self.queues:
                # Wait for queue to get set up
                await asyncio.sleep(1)
            await self.queues[sid].put(received_msg)

    async def recvall(self, reader, n):
        # Helper function to recv n bytes or return None if EOF is hit
        data = b''
        while len(data) < n:
            try:
                packet = await asyncio.wait_for(reader.read(n - len(data)),
                                                timeout=4)
                reader._bytesRead += len(packet)
            except asyncio.TimeoutError:
                print('recv timeout', reader._whoFrom,
                      'reading:', n - len(data),
                      'bytesRead:', reader._bytesRead)
                continue
            if len(packet) == 0:
                return None
            data += packet
        return data

    async def getMessage(self, sid):
        return await self.queues[sid].get()

    async def close(self):
        server = await self.serverTask
        server.close()
        await server.wait_closed()
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class NodeDetails(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


class ProcessProgramRunner(ProgramRunner):
    def __init__(self, config, N, t, nodeid):
        self.config = config
        self.N, self.t, self.nodeid = N, t, nodeid
        self.senders = Senders([asyncio.Queue() for _ in range(N)], config, nodeid)
        self.listener = Listener(config[nodeid].port)
        self.programs = []

    def getSendAndRecv(self, sid):
        listenerQueue = self.listener.getProgramQueue(sid)

        def makeSend(i, sid):
            def _send(j, o):
                # print('[%s] SEND %8s [%2d -> %2d]' % (sid, o[1], i, j))
                if i == j:
                    # If attempting to send the message to yourself
                    # then skip the network stack.
                    listenerQueue.put_nowait((i, o))
                else:
                    self.senders.queues[j].put_nowait((sid, (i, o)))
            return _send

        def makeRecv(j, sid):
            async def _recv():
                (i, o) = await self.listener.getMessage(sid)
                # print('[%s] RECV %8s [%2d -> %2d]' % (sid, o[1], i, j))
                return (i, o)
            return _recv

        return makeSend(self.nodeid, sid), makeRecv(self.nodeid, sid)

    def add(self, sid, program, **kwargs):
        send, recv = self.getSendAndRecv(sid)
        context = Mpc(
            'sid', self.N, self.t, self.nodeid, sid, send, recv, program, **kwargs
        )
        self.programs.append(asyncio.ensure_future(context._run()))
        return send, recv

    async def start(self):
        await self.senders.connect()

    async def join(self):
        """
        This method waits on all the added programs to complete.
        Once all programs are done, it cleans up the programs and the queues.
        """
        results = await asyncio.gather(*self.programs)
        # Clear out all programs and queues which were using old sids
        self.programs = []
        self.listener.clearAllProgramQueues()
        return results

    async def close(self):
        await self.senders.close()
        await self.listener.close()


if __name__ == "__main__":
    from .mpc import generate_test_zeros, generate_test_triples
    from .mpc import test_prog1, test_prog2
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
                os.mknod(f"sharedata/READY")
            else:
                loop.run_until_complete(wait_for_preprocessing())
        programRunner = ProcessProgramRunner(network_info, N, t, nodeid)
        loop.run_until_complete(programRunner.start())
        programRunner.add(1, test_prog1)
        programRunner.add(2, test_prog2)
        loop.run_until_complete(programRunner.join())
        loop.run_until_complete(programRunner.close())
    finally:
        loop.close()
