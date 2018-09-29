import _pickle as pickle
import asyncio
import sys
import os
import struct
import socket


class Sender(object):
    def __init__(self):
        self.receivers = {}
        self.loop = asyncio.get_event_loop()

    async def send(self, msg, ip, port):
        data = pickle.dumps(msg)
        padded_msg = struct.pack('>I', len(data)) + data
        key = "%s:%d" % (ip, port)
        try:
            if key not in self.receivers:
                receiver = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                receiver.connect((ip, port))
                receiver.setblocking(False)
                self.receivers[key] = receiver
            else:
                receiver = self.receivers[key]

            if receiver is not None:
                await self.loop.sock_sendall(receiver, padded_msg)
                # print('SEND %8s [%2d -> %s]' % (msg[1][0], msg[0], ip))
        except ConnectionResetError:
            print("WARNING: Connection with peer [%s] reset." % ip)
            self.receivers[key] = None
        except ConnectionRefusedError:
            print("WARNING: Connection with peer [%s] refused." % ip)
            self.receivers[key] = None
        except BrokenPipeError:
            print("WARNING: Connection with peer [%s] broken." % ip)
            self.receivers[key] = None

    def close(self):
        for receiver in self.receivers.values():
            if receiver is not None:
                receiver.close()


def handle_result(future):
    if not future.cancelled() and future.exception():
        # Stop the loop otherwise the loop continues to await for the prog to
        # finish which will never happen since the recvloop has terminated.
        loop.stop()
        future.result()


class Listener(object):
    def __init__(self, q, port):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('', port))
        server.listen(10)
        server.setblocking(False)
        self.server = server
        self.q = q
        self.loop = asyncio.get_event_loop()
        self.tasks = [self.loop.create_task(self.runServer())]

    async def runServer(self):
        while True:
            client, address = await self.loop.sock_accept(self.server)
            # print("Received connection from", address)
            self.tasks.append(self.loop.create_task(self.handle_client(client)))

    async def handle_client(self, client):
        while True:
            raw_msglen = await self.recvall(client, 4)
            if raw_msglen is None:
                break
            msglen = struct.unpack('>I', raw_msglen)[0]
            received_raw_msg = await self.recvall(client, msglen)
            if received_raw_msg is None:
                break
            received_msg = pickle.loads(received_raw_msg)
            # print('RECV %8s [from %2d]' % (received_msg[1][0], received_msg[0]))
            await self.q.put(received_msg)

    async def recvall(self, sock, n):
        # Helper function to recv n bytes or return None if EOF is hit
        data = b''
        while len(data) < n:
            packet = await self.loop.sock_recv(sock, n - len(data))
            if not packet:
                return None
            data += packet
        return data

    async def getMessage(self):
        return await self.q.get()

    def close(self):
        for task in self.tasks:
            task.cancel()


class NodeDetails(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


def process_router(config, id):
    sender = Sender()
    q = asyncio.Queue()
    listener = Listener(q, config[id].port)

    def makeSend(i):
        def _send(j, o):
            # print('SEND %8s [%2d -> %2d]' % (o[0], i, j))
            if i == j:
                # If attempting to send the message to yourself
                # then skip the network stack.
                q.put_nowait((i, o))
            else:
                loop = asyncio.get_event_loop()
                loop.create_task(sender.send((i, o), config[j].ip, config[j].port))

        return _send

    def makeRecv(j):
        async def _recv():
            (i, o) = await listener.getMessage()
            # print('RECV %8s [%2d -> %2d]' % (o[0], i, j))
            return (i, o)
        return _recv

    return (makeSend(id), makeRecv(id), sender, listener)


if __name__ == "__main__":
    from .passive import runProgramAsProcesses
    from .passive import generate_test_zeros, generate_test_triples
    from .passive import test_prog1, test_prog2

    # The "ALIAS" environment variable should be set.
    # It should be of the form <prefix>_<party_id> for each of the parties.
    # N - total number of parties
    # t - total number of corrupt parties
    # port - port to be used for communication between parties
    N, t, port = int(sys.argv[1]), int(sys.argv[2]), 7000
    host = os.environ.get('ALIAS').split("_")
    prefix, id = host[0] + "_", int(host[1])

    # Use this config if you want to test it on multiple processes on the same server
    # id = int(sys.argv[2])
    # config = {
    #     i: NodeDetails("localhost", p) for i, p in enumerate(range(port, port+n))}

    # Only one party needs to generate the initial shares
    if id == 0:
        print('Generating random shares of zero in sharedata/')
        generate_test_zeros('sharedata/test_zeros', 1000, N, t)
        print('Generating random shares of triples in sharedata/')
        generate_test_triples('sharedata/test_triples', 1000, N, t)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        config = {i: NodeDetails(prefix+str(i), port) for i in range(N)}
        loop.run_until_complete(runProgramAsProcesses(test_prog1, config, N, t, id))
        config = {i: NodeDetails(prefix+str(i), port-1000) for i in range(N)}
        loop.run_until_complete(runProgramAsProcesses(test_prog2, config, N, t, id))
    finally:
        loop.close()
