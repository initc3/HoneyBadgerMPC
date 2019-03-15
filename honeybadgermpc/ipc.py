import pickle
import asyncio
import struct
import socket
import logging
from .mpc import Mpc
from .config import HbmpcConfig, ConfigVars
from .program_runner import ProgramRunner
from .preprocessing import wait_for_preprocessing, preprocessing_done


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
# logger.setLevel(logging.NOTSET)


async def robust_open_connection(host, port):
    backoff = 1
    for _ in range(4):
        try:
            return await asyncio.open_connection(host, port)
        except (ConnectionRefusedError, ConnectionResetError):
            logger.info(f'backing off: {backoff} seconds')
            await asyncio.sleep(backoff)
            backoff *= 2


class Senders(object):
    def __init__(self, queues, config, nodeid):
        self.queues = queues
        self.config = config
        self.totalBytesSent = 0
        self.benchlogger = logging.LoggerAdapter(
            logging.getLogger("benchmark_logger"), {"node_id": nodeid})
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
                    # logger.debug(f'timeout sending to: {recvid} \
                    # sent: {writer._bytesSent}')
                    # Option 1: heartbeat
                    msg = "heartbeat"
                    # Option 2: no heartbeat
                    # continue

                if msg is None:
                    logger.debug('Close the connection')
                    writer.close()
                    await writer.wait_closed()
                    break

                # logger.debug('[%2d] SEND %8s [%2d -> %s]' % (
                #      msg[0], msg[1][1][0], msg[1][0], recvid
                # ))

                # start_time = os.times()
                data = pickle.dumps(msg)
                # pickle_time = str(os.times()[4] - start_time[4])
                # logger.debug(f'pickle time {pickle_time}')
                padded_msg = struct.pack('>I', len(data)) + data
                self.totalBytesSent += len(padded_msg)
                writer.write(padded_msg)
                await writer.drain()
                writer._bytesSent += len(padded_msg)
        except ConnectionResetError:
            logger.warning(f"Connection with peer [{recvid}] reset.")
        except ConnectionRefusedError:
            logger.warning(f"Connection with peer [{recvid}] refused.")
        except BrokenPipeError:
            logger.warning(f"Connection with peer [{recvid}] broken   .")

    async def close(self):
        await asyncio.gather(*[q.put(None) for q in self.queues])
        await asyncio.gather(*self.tasks)
        self.benchlogger.info("Total bytes sent out: %d", self.totalBytesSent)


class Listener(object):
    def __init__(self, port):
        self.queues = {}
        self.tasks = []
        server_future = asyncio.start_server(self.handle_client, "", port)
        self.serverTask = asyncio.ensure_future(server_future)

    def get_program_queue(self, sid):
        assert sid not in self.queues
        self.queues[sid] = asyncio.Queue()
        return self.queues[sid]

    def clear_all_program_queues(self):
        self.queues = {}

    async def handle_client(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.append(task)

        def cb(future):
            try:
                future.result()
            except asyncio.CancelledError:
                logger.warning("handle_client was cancelled.")
                return
        task.add_done_callback(cb)

        logger.debug(f"Received new connection {writer.get_extra_info('peername')}")
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
                # logger.debug(f"received heartbeat {reader._whoFrom}")
                continue
            sid, received_msg = unpickled
            if reader._whoFrom is None:
                reader._whoFrom = received_msg[0]
                logger.debug(f"{reader._whoFrom} {reader}")
            assert reader._whoFrom == received_msg[0]

            logger.debug('[%s] RECV %s' % (sid, received_msg))
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
                logger.info(f'recv timeout {reader._whoFrom} reading: \
                {n - len(data)} bytesRead: {reader._bytesRead}')
                continue
            if len(packet) == 0:
                return None
            data += packet
        return data

    async def get_message(self, sid):
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


class ProcessProgramRunner(ProgramRunner):
    def __init__(self, network_config, n, t, nodeid, config={}):
        self.network_config = network_config
        self.N, self.t, self.nodeid = n, t, nodeid
        self.senders = Senders(
            [asyncio.Queue() for _ in range(n)], network_config, nodeid)
        self.listener = Listener(network_config[nodeid].port)
        self.programs = []
        self.config = config
        self.config[ConfigVars.Reconstruction] = HbmpcConfig.reconstruction

    def get_send_and_recv(self, sid):
        listener_queue = self.listener.get_program_queue(sid)

        def make_send(i, sid):
            def _send(j, o):
                logger.debug('[%s] SEND %8s [%2d -> %2d]' % (sid, o, i, j))
                if i == j:
                    # If attempting to send the message to yourself
                    # then skip the network stack.
                    listener_queue.put_nowait((i, o))
                else:
                    self.senders.queues[j].put_nowait((sid, (i, o)))

            return _send

        def make_recv(j, sid):
            async def _recv():
                (i, o) = await self.listener.get_message(sid)
                logger.debug('[%s] RECV %8s [%2d -> %2d]' % (sid, o, i, j))
                return (i, o)
            return _recv

        return make_send(self.nodeid, sid), make_recv(self.nodeid, sid)

    def add(self, sid, program, **kwargs):
        send, recv = self.get_send_and_recv(sid)
        context = Mpc(
                'sid',
                self.N,
                self.t,
                self.nodeid,
                sid,
                send,
                recv,
                program,
                self.config,
                **kwargs,
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
        self.listener.clear_all_program_queues()
        return results

    async def close(self):
        await self.senders.close()
        await self.listener.close()


if __name__ == "__main__":
    from .mpc import test_prog1, test_prog2, test_batchopening
    from .preprocessing import PreProcessedElements

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        if not HbmpcConfig.skip_preprocessing:
            # Only one party needs to generate the initial shares
            if HbmpcConfig.my_id == 0:
                pp_elements = PreProcessedElements()
                logger.info('Generating random shares of zero in sharedata/')
                pp_elements.generate_zeros(1000, HbmpcConfig.N, HbmpcConfig.t)
                logger.info('Generating random shares of triples in sharedata/')
                pp_elements.generate_triples(1000, HbmpcConfig.N, HbmpcConfig.t)
                preprocessing_done()
            else:
                loop.run_until_complete(wait_for_preprocessing())
        program_runner = ProcessProgramRunner(
            HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id)
        loop.run_until_complete(program_runner.start())
        program_runner.add(1, test_prog1)
        program_runner.add(2, test_prog2)
        program_runner.add(3, test_batchopening)
        loop.run_until_complete(program_runner.join())
        loop.run_until_complete(program_runner.close())
    finally:
        loop.close()
