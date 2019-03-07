import logging
import asyncio
from collections import defaultdict
from pickle import dumps, loads
from honeybadgermpc.betterpairing import ZR
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit import PolyCommit
from honeybadgermpc.symmetric_crypto import SymmetricCrypto
from honeybadgermpc.exceptions import HoneyBadgerMPCError
from honeybadgermpc.protocols.reliablebroadcast import reliablebroadcast


class HbAVSSMessageType:
    OK = "OK"
    AVSS = "AVSS"
    RBC = "RBC"


class HbAvssLight(object):
    def __init__(self, public_keys, private_key, g, h, n, t, my_id, send, recv):
        self.public_keys, self.private_key = public_keys, private_key
        self.n, self.t, self.my_id = n, t, my_id
        self.g = g
        self.poly_commit = PolyCommit(g, h)
        # A different set of send, recv values must be passed for each AVSS object.
        # If the same sends, recvs are reused then the recv_loops of the two objects
        # can get values belonging to the other object.
        self.send, self.recv = send, recv
        self.field = ZR
        self.poly = polynomials_over(self.field)

        # When running multiple AVSSes, the messages are forwarded to the correct
        # RBC/AVSS using these queues. The key is the AVSS ID which is sent along
        # with each RBC/AVSS message.
        self.rbc_queues = defaultdict(asyncio.Queue)
        self.avss_queues = defaultdict(asyncio.Queue)

        # This is used for generating the AVSS Id.
        self.counter = 0

    def __enter__(self):
        # Start the recv loop. This receives messages for all running AVSSes.
        # It puts the messages intened for a specific AVSS in its queue based
        # on the AVSS id.
        self.recv_loop_task = asyncio.create_task(self._recv_loop())
        return self

    def __exit__(self, type, value, traceback):
        self.recv_loop_task.cancel()

    async def _recv_loop(self):
        while True:
            sender_id, recvd_msg = await self.recv()
            # 0th element in recvd_msg is the AVSS ID
            msg_type, avss_id = recvd_msg[0]
            logging.debug("[%d]MsgType [%s] AvssId [%s].", self.my_id, msg_type, avss_id)
            if msg_type == HbAVSSMessageType.RBC:
                await self.rbc_queues[avss_id].put((sender_id, recvd_msg))
            elif msg_type == HbAVSSMessageType.AVSS:
                await self.avss_queues[avss_id].put((sender_id, recvd_msg))
            else:
                logging.error("Invalid message type [%s] received.", msg_type)
                raise HoneyBadgerMPCError("Invalid message type received in recv_loop.")

    async def _process_avss_msg(self, avss_id, avss_msg, recv):
        def multicast(msg):
            for i in range(self.n):
                self.send(i, msg)

        commitments, ephemeral_public_key, encrypted_witnesses = loads(avss_msg)
        shared_key = pow(ephemeral_public_key, self.private_key)
        share, witness = SymmetricCrypto.decrypt(
            str(shared_key).encode("utf-8"), encrypted_witnesses[self.my_id])
        if self.poly_commit.verify_eval(commitments, self.my_id+1, share, witness):
            multicast(((HbAVSSMessageType.AVSS, avss_id), HbAVSSMessageType.OK))
        else:
            logging.error("PolyCommit verification failed.")
            raise HoneyBadgerMPCError("PolyCommit verification failed.")

        oks_recvd = 0
        while oks_recvd < 2*self.t + 1:
            _, avss_msg = await recv()  # First value is the `sid`
            if avss_msg[1] == HbAVSSMessageType.OK:
                oks_recvd += 1

        logging.debug("[%d][HbAVSSLight] 2t+1 OKs received.", self.my_id)
        return share

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

    async def avss(self, value=None, dealer_id=None, client_mode=False):
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

        # Choose the avss_id based on the order this is called
        avss_id = f"AVSS-{self.counter}"
        self.counter += 1
        logging.debug("[%d] Starting AVSS [%s]", self.my_id, avss_id)

        broadcast_msg = None if self.my_id != dealer_id else self._get_dealer_msg(value)
        # In the client_mode, the dealer is the last node
        n = self.n if not client_mode else self.n+1

        avss_msg = await reliablebroadcast(
            (HbAVSSMessageType.RBC, avss_id),
            self.my_id,
            n,
            self.t,
            dealer_id,
            broadcast_msg,
            self.rbc_queues[avss_id].get,
            self.send
        )

        if client_mode and self.my_id == dealer_id:
            # In client_mode, the dealer is not supposed to do
            # anything after sending the initial value.
            return

        logging.debug("[%d][HbAVSSLight] RBC completed.", self.my_id)
        share = await self._process_avss_msg(
            avss_id, avss_msg, self.avss_queues[avss_id].get)
        logging.debug("[%d][HbAVSSLight] AVSS [%s] Completed.", self.my_id, avss_id)
        return share
