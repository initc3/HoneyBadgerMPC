import logging
import asyncio
from pickle import dumps, loads
from honeybadgermpc.betterpairing import ZR
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit import PolyCommit
from honeybadgermpc.symmetric_crypto import SymmetricCrypto
from honeybadgermpc.exceptions import HoneyBadgerMPCError
from honeybadgermpc.protocols.reliablebroadcast import reliablebroadcast
from honeybadgermpc.protocols.avid import AVID

# TODO: Move these to a separate file instead of using it from batch_reconstruction.py
from honeybadgermpc.batch_reconstruction import subscribe_recv, wrap_send


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
# logger.setLevel(logging.NOTSET)


class HbAVSSMessageType:
    OK = "OK"
    # IMPLICATE = "IMPLICATE"
    READY = "READY"


class HbAvss(object):
    # base class of HbAvss containing light and batch version
    def __init__(self, public_keys, private_key, g, h, n, t, my_id, send, recv):
        self.public_keys, self.private_key = public_keys, private_key
        self.n, self.t, self.my_id = n, t, my_id
        self.g = g
        self.poly_commit = PolyCommit(g, h)

        # Create a mechanism to split the `recv` channels based on `tag`
        self.subscribe_recv_task, self.subscribe_recv = subscribe_recv(recv)

        # Create a mechanism to split the `send` channels based on `tag`
        def _send(tag):
            return wrap_send(tag, send)
        self.get_send = _send

        # This is added to consume the share the moment it is generated.
        # This is especially helpful when running multiple AVSSes in parallel.
        self.output_queue = asyncio.Queue()

        self.field = ZR
        self.poly = polynomials_over(self.field)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.subscribe_recv_task.cancel()


class HbAvssLight(HbAvss):
    async def _process_avss_msg(self, avss_id, dealer_id, avss_msg):
        tag = f"{dealer_id}-{avss_id}-AVSS"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        def multicast(msg):
            for i in range(self.n):
                send(i, msg)

        commitments, ephemeral_public_key, encrypted_witnesses = loads(avss_msg)
        shared_key = pow(ephemeral_public_key, self.private_key)
        share, witness = SymmetricCrypto.decrypt(
            str(shared_key).encode("utf-8"), encrypted_witnesses[self.my_id])
        if self.poly_commit.verify_eval(commitments, self.my_id+1, share, witness):
            multicast(HbAVSSMessageType.OK)
        else:
            logging.error("PolyCommit verification failed.")
            raise HoneyBadgerMPCError("PolyCommit verification failed.")

        # to handle the case that a (malicious) node sends
        # an OK message multiple times
        ok_set = set()
        while len(ok_set) < 2 * self.t + 1:
            sender, avss_msg = await recv()  # First value is the `sid`
            if avss_msg == HbAVSSMessageType.OK and sender not in ok_set:
                ok_set.add(sender)

        # Output the share as an integer so it is not tied to a type like ZR/GFElement
        share_int = int(share)
        self.output_queue.put_nowait((dealer_id, avss_id, share_int))

        logger.debug("[%d] 2t+1 OKs received.", self.my_id)
        return share_int

    def _get_dealer_msg(self, value):
        phi = self.poly.random(self.t, value)
        commitments, aux_poly = self.poly_commit.commit(phi)
        ephemeral_secret_key = self.field.random()
        ephemeral_public_key = pow(self.g, ephemeral_secret_key)
        z = [None]*self.n
        for i in range(self.n):
            witness = self.poly_commit.create_witness(aux_poly, i+1)
            shared_key = pow(self.public_keys[i], ephemeral_secret_key)
            z[i] = SymmetricCrypto.encrypt(
                str(shared_key).encode("utf-8"), (phi(i+1), witness))

        return dumps((commitments, ephemeral_public_key, z))

    async def avss(self, avss_id, value=None, dealer_id=None, client_mode=False):
        """
        avss_id: This must be an integer. This must start from 0 per dealer. This is
        important since it used to ensure an in order delivery of values at each node
        per dealer i.e. if a node deals two values, then the shares of those values
        need to be received in the order that they are dealt.

        Eg:
        => If there are 4 nodes and node 0 wants to deal two values:

        node 0: avss(0, value=value1, dealer_id=0)
        node 1: avss(0, dealer_id=0)
        node 2: avss(0, dealer_id=0)
        node 3: avss(0, dealer_id=0)

        node 0: avss(1, value=value2, dealer_id=0)
        node 1: avss(1, dealer_id=0)
        node 2: avss(1, dealer_id=0)
        node 3: avss(1, dealer_id=0)

        => Now, if node 1 wants to deal a value next,
        => the avss_id still must start from 0:

        node 0: avss(0, value=value3, dealer_id=1)
        node 1: avss(0, dealer_id=1)
        node 2: avss(0, dealer_id=1)
        node 3: avss(0, dealer_id=1)
        """
        # If `value` is passed then the node is a 'Sender'
        # `dealer_id` must be equal to `self.my_id`
        if value is not None:
            if dealer_id is None:
                dealer_id = self.my_id
            assert dealer_id == self.my_id, "Only dealer can share a value."
        # If `value` is not passed then the node is a 'Recipient'
        # Verify that the `dealer_id` is not the same as `self.my_id`
        elif dealer_id is not None:
            assert dealer_id != self.my_id
        if client_mode:
            assert dealer_id is not None
            assert dealer_id == self.n
        assert type(avss_id) is int

        logger.debug("[%d] Starting Light AVSS. Id: %s, Dealer Id: %d, Client Mode: %s",
                     self.my_id, avss_id, dealer_id, client_mode)

        broadcast_msg = None if self.my_id != dealer_id else self._get_dealer_msg(value)
        # In the client_mode, the dealer is the last node
        n = self.n if not client_mode else self.n+1

        tag = f"{dealer_id}-{avss_id}-RBC"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)
        avss_msg = await reliablebroadcast(
            tag,
            self.my_id,
            n,
            self.t,
            dealer_id,
            broadcast_msg,
            recv,
            send
        )

        if client_mode and self.my_id == dealer_id:
            # In client_mode, the dealer is not supposed to do
            # anything after sending the initial value.
            return

        logger.debug("[%d] RBC completed.", self.my_id)
        share = await self._process_avss_msg(avss_id, dealer_id, avss_msg)
        logger.debug("[%d] AVSS [%s] completed.", self.my_id, avss_id)
        return share

    async def avss_parallel(self, avss_id, k, values=None, dealer_id=None):
        """
        Run a HbAVSSLight in parallel for each of the values.

        avss_id: This must be an integer. This must start from 0 per dealer.
        Look at the `avss` method above for a detailed explanation.
        """
        if values is not None:
            assert len(values) == k
        avss_tasks = [None]*k
        for i in range(k):
            v = None if values is None else values[i]
            avss_tasks[i] = asyncio.create_task(self.avss(k*avss_id+i, v, dealer_id))
        return await asyncio.gather(*avss_tasks)


class HbAvssBatch(HbAvss):
    def __init__(self, public_keys, private_key, g, h, n, t, my_id, send, recv):
        super(HbAvssBatch, self).__init__(public_keys,
                                          private_key, g, h, n, t, my_id, send, recv)
        self.avid_msg_queue = asyncio.Queue()
        self.tasks = []

    async def _recv_loop(self, q):
        while True:
            avid, tag, dispersal_msg_list = await q.get()
            self.tasks.append(asyncio.create_task(
                avid.disperse(tag, self.my_id, dispersal_msg_list)))

    def __enter__(self):
        self._recv_task = asyncio.create_task(self._recv_loop(self.avid_msg_queue))
        return self

    def __exit__(self, typ, value, traceback):
        self._recv_task.cancel()
        for task in self.tasks:
            task.cancel()
        super(HbAvssBatch, self).__exit__(typ, value, traceback)

    async def _process_avss_msg(self, avss_id, dealer_id, dispersal_msg):
        tag = f"{dealer_id}-{avss_id}-B-AVSS"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        def multicast(msg):
            for i in range(self.n):
                send(i, msg)

        commitments, ephemeral_public_key, encrypted_witnesses = loads(
            dispersal_msg)
        secret_size = len(commitments)

        # all_encrypted_witnesses: n
        shared_key = pow(ephemeral_public_key, self.private_key)

        shares = [None] * secret_size
        witnesses = [None] * secret_size
        # Decrypt
        for k in range(secret_size):
            shares[k], witnesses[k] = SymmetricCrypto.decrypt(
                str(shared_key).encode("utf-8"), encrypted_witnesses[k])

        # verify & send all ok
        for i in range(secret_size):
            if not self.poly_commit.verify_eval(
                    commitments[i], self.my_id+1, shares[i], witnesses[i]):
                # will be replaced by sending out IMPLICATE message later
                # multicast(HbAVSSMessageType.IMPLICATE)
                logging.error("PolyCommit verification failed.")
                raise HoneyBadgerMPCError("PolyCommit verification failed.")

        multicast(HbAVSSMessageType.OK)

        # Bracha-style agreement
        # to handle the case that a (malicious) node sends
        # an OK or READY message multiple times
        ok_set = set()
        ready_set = set()
        # if 2t+1 OK or t+1 READY -> send all ready
        while len(ok_set) < 2 * self.t + 1 and len(ready_set) < self.t + 1:
            sender, avss_msg = await recv()  # First value is the `sid`
            if avss_msg == HbAVSSMessageType.OK and sender not in ok_set:
                ok_set.add(sender)
            elif avss_msg == HbAVSSMessageType.READY and sender not in ready_set:
                ready_set.add(sender)

        multicast(HbAVSSMessageType.READY)

        # if 2t+1 ready -> output shares
        while len(ready_set) < 2 * self.t + 1:
            sender, avss_msg = await recv()  # First value is the `sid`
            if avss_msg == HbAVSSMessageType.READY and sender not in ready_set:
                ready_set.add(sender)

        return shares

    def _get_dealer_msg(self, values):
        # Sample a random degree-(t,t) bivariate polynomial φ(·,·)
        # such that each φ(0,k) = sk and φ(i,k) is Pi’s share of sk
        secret_size = len(values)
        phi = [None] * secret_size
        commitments = [None] * secret_size
        aux_poly = [None] * secret_size
        # for k ∈ [t+1]
        #   Ck, auxk <- PolyCommit(SP,φ(·,k))
        for k in range(secret_size):
            phi[k] = self.poly.random(self.t, values[k])
            commitments[k], aux_poly[k] = self.poly_commit.commit(phi[k])

        ephemeral_secret_key = self.field.random()
        ephemeral_public_key = pow(self.g, ephemeral_secret_key)
        # for each party Pi and each k ∈ [t+1]
        #   1. w[i][k] <- CreateWitnesss(Ck,auxk,i)
        #   2. z[i][k] <- EncPKi(φ(i,k), w[i][k])
        dealer_msg_list = [None] * self.n
        for i in range(self.n):
            shared_key = pow(self.public_keys[i], ephemeral_secret_key)
            z = [None] * secret_size
            for k in range(secret_size):
                witness = self.poly_commit.create_witness(aux_poly[k], i+1)
                z[k] = SymmetricCrypto.encrypt(
                    str(shared_key).encode("utf-8"), (phi[k](i+1), witness))
            dealer_msg_list[i] = dumps((commitments, ephemeral_public_key, z))

        return dealer_msg_list

    async def avss(self, avss_id, values=None, dealer_id=None, client_mode=False):
        """
        A batched version of avss similar to the one in light version
        """
        # If `values` is passed then the node is a 'Sender'
        # `dealer_id` must be equal to `self.my_id`
        if values is not None:
            if dealer_id is None:
                dealer_id = self.my_id
            assert dealer_id == self.my_id, "Only dealer can share values."
        # If `values` is not passed then the node is a 'Recipient'
        # Verify that the `dealer_id` is not the same as `self.my_id`
        elif dealer_id is not None:
            assert dealer_id != self.my_id
        if client_mode:
            assert dealer_id is not None
            assert dealer_id == self.n
        assert type(avss_id) is int

        logger.debug("[%d] Starting Batch AVSS. Id: %s, Dealer Id: %d, Client Mode: %s",
                     self.my_id, avss_id, dealer_id, client_mode)

        dispersal_msg_list = None
        if self.my_id == dealer_id:
            dispersal_msg_list = self._get_dealer_msg(values)

        # In the client_mode, the dealer is the last node
        n = self.n if not client_mode else self.n+1

        tag = f"{dealer_id}-{avss_id}-B-AVID"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        avid = AVID(n, self.t, dealer_id, recv, send, n)
        # start disperse in the background
        self.avid_msg_queue.put_nowait((avid, tag, dispersal_msg_list))
        # message can be retrieved individually
        avss_msg = await avid.retrieve(tag, self.my_id)

        if client_mode and self.my_id == dealer_id:
            # In client_mode, the dealer is not supposed to do
            # anything after sending the initial value.
            return

        logger.debug("[%d] Dispersal completed.", self.my_id)
        share = await self._process_avss_msg(avss_id, dealer_id, avss_msg)
        logger.debug("[%d] Batch AVSS [%s] completed.", self.my_id, avss_id)
        return share
