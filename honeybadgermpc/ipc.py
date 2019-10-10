import logging
import asyncio

from zmq import ROUTER, DEALER, IDENTITY
from zmq.asyncio import Context
from pickle import dumps, loads
from psutil import cpu_count

from honeybadgermpc.mpc import Mpc
from honeybadgermpc.config import HbmpcConfig, ConfigVars
from honeybadgermpc.utils.misc import wrap_send, subscribe_recv
from honeybadgermpc.utils.misc import print_exception_callback


class NodeCommunicator(object):
    LAST_MSG = None

    def __init__(self, peers_config, my_id, linger_timeout):
        self.peers_config = peers_config
        self.my_id = my_id

        self.bytes_sent = 0
        self.benchmark_logger = logging.LoggerAdapter(
            logging.getLogger("benchmark_logger"), {"node_id": my_id}
        )

        self._dealer_tasks = []
        self._router_task = None
        self.linger_timeout = linger_timeout
        self.zmq_context = Context(io_threads=cpu_count())

        n = len(peers_config)
        self._receiver_queue = asyncio.Queue()
        self._sender_queues = [None] * n
        for i in range(n):
            if i == self.my_id:
                self._sender_queues[i] = self._receiver_queue
            else:
                self._sender_queues[i] = asyncio.Queue()

    def send(self, node_id, msg):
        msg = (self.my_id, msg) if node_id == self.my_id else msg
        self._sender_queues[node_id].put_nowait(msg)

    async def recv(self):
        return await self._receiver_queue.get()

    async def __aenter__(self):
        await self._setup()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # Add None to the sender queues and drain out all the messages.
        for i in range(len(self._sender_queues)):
            if i != self.my_id:
                self._sender_queues[i].put_nowait(NodeCommunicator.LAST_MSG)
        await asyncio.gather(*self._dealer_tasks)
        logging.debug("Dealer tasks finished.")
        self._router_task.cancel()
        logging.debug("Router task cancelled.")
        self.zmq_context.destroy(linger=self.linger_timeout * 1000)
        self.benchmark_logger.info("Total bytes sent out: %d", self.bytes_sent)

    async def _setup(self):
        # Setup one router for a party, this acts as a
        # server for receiving messages from other parties.
        router = self.zmq_context.socket(ROUTER)
        router.bind(f"tcp://*:{self.peers_config[self.my_id].port}")
        # Start a task to receive messages on this node.
        self._router_task = asyncio.create_task(self._recv_loop(router))
        self._router_task.add_done_callback(print_exception_callback)

        # Setup one dealer per receving party. This is used
        # as a client to send messages to other parties.
        for i in range(len(self.peers_config)):
            if i != self.my_id:
                dealer = self.zmq_context.socket(DEALER)
                # This identity is sent with each message. Setting it to my_id, this is
                # used to appropriately route the message. This is not a good idea since
                # a node can pretend to send messages on behalf of other nodes.
                dealer.setsockopt(IDENTITY, str(self.my_id).encode())
                dealer.connect(
                    f"tcp://{self.peers_config[i].ip}:{self.peers_config[i].port}"
                )
                # Setup a task which reads messages intended for this
                # party from a queue and then sends them to this node.
                task = asyncio.create_task(
                    self._process_node_messages(
                        i, self._sender_queues[i], dealer.send_multipart
                    )
                )
                self._dealer_tasks.append(task)

    async def _recv_loop(self, router):
        while True:
            sender_id, raw_msg = await router.recv_multipart()
            msg = loads(raw_msg)
            # logging.debug("[RECV] FROM: %s, MSG: %s,", sender_id, msg)
            self._receiver_queue.put_nowait((int(sender_id), msg))

    async def _process_node_messages(self, node_id, node_msg_queue, send_to_node):
        while True:
            msg = await node_msg_queue.get()
            if msg is NodeCommunicator.LAST_MSG:
                logging.debug("No more messages to Node: %d can be sent.", node_id)
                break
            raw_msg = dumps(msg)
            self.bytes_sent += len(raw_msg)
            # logging.debug("[SEND] TO: %d, MSG: %s", node_id, msg)
            await send_to_node([raw_msg])


class ProcessProgramRunner(object):
    def __init__(self, peers_config, n, t, my_id, mpc_config={}, linger_timeout=2):
        self.peers_config = peers_config
        self.n = n
        self.t = t
        self.my_id = my_id
        self.mpc_config = mpc_config
        self.mpc_config[ConfigVars.Reconstruction] = HbmpcConfig.reconstruction

        self.node_communicator = NodeCommunicator(peers_config, my_id, linger_timeout)
        self.progs = []

    def execute(self, sid, program, **kwargs):
        send, recv = self.get_send_recv(sid)
        context = Mpc(
            sid,
            self.n,
            self.t,
            self.my_id,
            send,
            recv,
            program,
            self.mpc_config,
            **kwargs,
        )
        program_result = asyncio.Future()

        def callback(future):
            program_result.set_result(future.result())

        task = asyncio.create_task(context._run())
        task.add_done_callback(callback)
        task.add_done_callback(print_exception_callback)
        self.progs.append(task)
        return program_result

    def get_send_recv(self, tag):
        return wrap_send(tag, self.send), self.subscribe(tag)

    async def __aenter__(self):
        await self.node_communicator.__aenter__()
        self.subscribe_task, self.subscribe = subscribe_recv(
            self.node_communicator.recv
        )
        self.send = self.node_communicator.send
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.gather(*self.progs)
        logging.debug("All programs finished.")
        await self.node_communicator.__aexit__(exc_type, exc, tb)
        logging.debug("NodeCommunicator closed.")
        self.subscribe_task.cancel()
        logging.debug("Subscribe task cancelled.")


async def verify_all_connections(peers, n, my_id):
    # Uncomment this if you want to test on multiple processes.
    # No need to uncomment this when running across servers
    # since the network latency is already present there.

    # logging.debug("Sleeping for: %d", my_id)
    # await asyncio.sleep(my_id)

    async with NodeCommunicator(peers, my_id) as node_communicator:
        for i in range(n):
            node_communicator.send(i, i)
        sender_ids = set()
        keys = set()
        for i in range(n):
            msg = await node_communicator.recv()
            sender_ids.add(msg[0])
            keys.add(msg[1])
        assert len(sender_ids) == n
        for i in range(n):
            assert i in sender_ids
        assert len(keys) == 1
        assert keys.pop() == my_id
        logging.info("Verfification completed.")


async def test_mpc_programs(peers, n, t, my_id):
    from honeybadgermpc.mpc import test_prog1, test_prog2, test_batchopening
    from honeybadgermpc.preprocessing import PreProcessedElements
    from honeybadgermpc.preprocessing import wait_for_preprocessing, preprocessing_done

    if not HbmpcConfig.skip_preprocessing:
        # Only one party needs to generate the preprocessed elements for testing
        if HbmpcConfig.my_id == 0:
            pp_elements = PreProcessedElements()
            pp_elements.generate_zeros(1000, HbmpcConfig.N, HbmpcConfig.t)
            pp_elements.generate_triples(1000, HbmpcConfig.N, HbmpcConfig.t)
            preprocessing_done()
        else:
            await wait_for_preprocessing()

    async with ProcessProgramRunner(peers, n, t, my_id) as runner:
        test_prog1  # r1 = runner.execute("0", test_prog1)
        r2 = runner.execute("1", test_prog2)
        r3 = runner.execute("2", test_batchopening)
        results = await asyncio.gather(*[r2, r3])
        return results


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    # loop.run_until_complete(
    #     verify_all_connections(HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.my_id))
    loop.run_until_complete(
        test_mpc_programs(
            HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id
        )
    )
