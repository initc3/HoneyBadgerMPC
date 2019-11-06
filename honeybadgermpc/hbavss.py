import asyncio
import logging
import time
from pickle import dumps, loads

from honeybadgermpc.betterpairing import G1, ZR, interpolate_g1_at_x
from honeybadgermpc.broadcast.avid import AVID
from honeybadgermpc.broadcast.reliablebroadcast import reliablebroadcast
from honeybadgermpc.poly_commit_const import PolyCommitConst
from honeybadgermpc.poly_commit_lin import PolyCommitLin
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.symmetric_crypto import SymmetricCrypto
from honeybadgermpc.utils.misc import subscribe_recv, wrap_send


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# Uncomment this when you want logs from this file.
logger.setLevel(logging.NOTSET)


class HbAVSSMessageType:
    OK = "OK"
    IMPLICATE = "IMPLICATE"
    READY = "READY"
    RECOVERY = "RECOVERY"
    RECOVERY1 = "RECOVERY1"
    RECOVERY2 = "RECOVERY2"


class HbAvssLight:
    def __init__(
        self, public_keys, private_key, crs, n, t, my_id, send, recv, pc=None, field=ZR
    ):  # (# noqa: E501)
        self.public_keys, self.private_key = public_keys, private_key
        self.n, self.t, self.my_id = n, t, my_id
        self.g = crs[0]

        # Create a mechanism to split the `recv` channels based on `tag`
        self.subscribe_recv_task, self.subscribe_recv = subscribe_recv(recv)

        # Create a mechanism to split the `send` channels based on `tag`
        def _send(tag):
            return wrap_send(tag, send)

        self.get_send = _send

        # This is added to consume the share the moment it is generated.
        # This is especially helpful when running multiple AVSSes in parallel.
        self.output_queue = asyncio.Queue()

        self.field = field
        self.poly = polynomials_over(self.field)
        if pc is None:
            self.poly_commit = PolyCommitLin(crs, field=self.field)
            self.poly_commit.preprocess(5)
        else:
            self.poly_commit = pc

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.subscribe_recv_task.cancel()

    def _handle_implication(self, commitments, ephemeral_public_key, j, j_sk, j_z):
        """
        Handle the implication of AVSS.
        Return True if the implication is valid, False otherwise.
        """
        print("got implication")
        # discard if PKj ! = g^SKj
        if self.public_keys[j] != pow(self.g, j_sk):
            return False
        # decrypt and verify
        j_shared_key = pow(ephemeral_public_key, j_sk)
        try:
            j_shares, j_auxs = SymmetricCrypto.decrypt(str(j_shared_key).encode(), j_z)
        except Exception:  # TODO: specific exception
            return True
        return not self.poly_commit.batch_verify_eval(
            commitments, j + 1, j_shares, j_auxs
        )

    async def _process_avss_msg(self, avss_id, dealer_id, avss_msg):
        tag = f"{dealer_id}-{avss_id}-AVSS"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        def multicast(msg):
            for i in range(self.n):
                send(i, msg)

        commitments, ephemeral_public_key, encrypted_blobs = loads(avss_msg)
        shared_key = pow(ephemeral_public_key, self.private_key)
        share_valid = True
        try:
            shares, witnesses = SymmetricCrypto.decrypt(
                str(shared_key).encode(), encrypted_blobs[self.my_id]
            )
            if self.poly_commit.batch_verify_eval(
                commitments, self.my_id + 1, shares, witnesses
            ):
                logger.info(f"OK_timestamp: {time.time()}")
                multicast((HbAVSSMessageType.OK, ""))
            else:
                multicast((HbAVSSMessageType.IMPLICATE, self.private_key))
                share_valid = False
        except Exception:  # TODO specific exceptions
            multicast((HbAVSSMessageType.IMPLICATE, self.private_key))
            share_valid = False

        # RECEIVE LOOP
        ok_set = set()
        recovery_set = set()
        implicate_set = set()
        recovery_shares = [[] for _ in range(len(commitments))]
        sent_recovery = False
        output = False
        recovered = False
        while True:
            if len(ok_set) == 2 * self.t + 1 and share_valid and not output:
                if len(commitments) == 1:
                    self.output_queue.put_nowait((dealer_id, avss_id, int(shares[0])))
                else:
                    int_shares = [int(shares[i]) for i in range(len(shares))]
                    self.output_queue.put_nowait((dealer_id, avss_id, int_shares))
                output = True
            elif len(recovery_set) == self.t + 1 and not output:
                if len(commitments) == 1:
                    shares = [
                        self.poly.interpolate_at(recovery_shares[0], self.my_id + 1)
                    ]
                    self.output_queue.put_nowait((dealer_id, avss_id, int(shares[0])))
                else:
                    shares = [None] * len(commitments)
                    share_ints = [None] * len(commitments)
                    for i in range(len(commitments)):
                        shares[i] = self.poly.interpolate_at(
                            recovery_shares[i], self.my_id + 1
                        )
                        share_ints[i] = int(shares[i])
                    self.output_queue.put_nowait((dealer_id, avss_id, share_ints))
                output = True
                share_valid = True
                recovered = True
                multicast((HbAVSSMessageType.OK, ""))

            # Conditions where we can terminate
            if (
                len(ok_set) == self.n
                or len(implicate_set) >= self.t + 1
                or len(ok_set) >= 2 * self.t + 1
                and (sent_recovery or recovered)
            ):
                break

            sender, avss_msg = await recv()  # First value is `sid` (not true anymore?)
            if avss_msg[0] == HbAVSSMessageType.OK and sender not in ok_set:
                ok_set.add(sender)
            if (
                avss_msg[0] == HbAVSSMessageType.IMPLICATE
                and sender not in implicate_set
            ):
                implicate_set.add(sender)
            if (
                avss_msg[0] == HbAVSSMessageType.IMPLICATE
                and not sent_recovery
                and share_valid
            ):
                j_sk = avss_msg[1]
                j = sender
                # validate the implicate
                if not self._handle_implication(
                    commitments, ephemeral_public_key, j, j_sk, encrypted_blobs[j]
                ):
                    # Count an invalid implicate as an okay
                    if sender not in ok_set:
                        ok_set.add(sender)
                    continue
                sent_recovery = True
                multicast((HbAVSSMessageType.RECOVERY, self.private_key))
            if (
                avss_msg[0] == HbAVSSMessageType.RECOVERY
                and not share_valid
                and sender not in recovery_set
            ):
                try:
                    shares_j, auxs_j = SymmetricCrypto.decrypt(
                        str(ephemeral_public_key ** avss_msg[1]).encode(),
                        encrypted_blobs[sender],
                    )  # (# noqa: E501)
                except Exception:
                    ok_set.add(sender)
                    continue
                if self.poly_commit.batch_verify_eval(
                    commitments, sender + 1, shares_j, auxs_j
                ):
                    for i in range(len(commitments)):
                        recovery_shares[i].append([sender + 1, shares_j[i]])
                    recovery_set.add(sender)

    def _get_dealer_msg(self, value):
        if type(value) in (list, tuple):
            valuelist = value
        else:
            valuelist = [value]
        philist, commitlist, auxlist = [], [], []
        for val in valuelist:
            phi = self.poly.random(self.t, val)
            philist.append(phi)
            # Todo: precompute commit stuff
            commitment, aux_poly = self.poly_commit.commit(phi)
            commitlist.append(commitment)
            auxlist.append(aux_poly)
        ephemeral_secret_key = self.field.random()
        ephemeral_public_key = pow(self.g, ephemeral_secret_key)
        z = [None] * self.n
        for i in range(self.n):
            shared_key = pow(self.public_keys[i], ephemeral_secret_key)
            shares, witnesses = [], []
            for j in range(len(philist)):
                shares.append(philist[j](i + 1))
                witnesses.append(self.poly_commit.create_witness(auxlist[j], i + 1))
            z[i] = SymmetricCrypto.encrypt(
                str(shared_key).encode(), (shares, witnesses)
            )

        return dumps((commitlist, ephemeral_public_key, z))

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

        logger.debug(
            "[%d] Starting Light AVSS. Id: %s, Dealer Id: %d, Client Mode: %s",
            self.my_id,
            avss_id,
            dealer_id,
            client_mode,
        )

        broadcast_msg = None if self.my_id != dealer_id else self._get_dealer_msg(value)
        # In the client_mode, the dealer is the last node
        n = self.n if not client_mode else self.n + 1

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
            send,
            client_mode=client_mode,
        )

        if client_mode and self.my_id == dealer_id:
            # In client_mode, the dealer is not supposed to do
            # anything after sending the initial value.
            return

        logger.debug("[%d] RBC completed.", self.my_id)
        await self._process_avss_msg(avss_id, dealer_id, avss_msg)
        logger.debug("[%d] AVSS [%s] completed.", self.my_id, avss_id)

    async def avss_parallel(self, avss_id, k, values=None, dealer_id=None):
        """
        Run a HbAVSSLight in parallel for each of the values.

        avss_id: This must be an integer. This must start from 0 per dealer.
        Look at the `avss` method above for a detailed explanation.
        """
        if values is not None:
            assert len(values) == k
        avss_tasks = [None] * k
        for i in range(k):
            v = None if values is None else values[i]
            avss_tasks[i] = asyncio.create_task(
                self.avss(k * avss_id + i, v, dealer_id)
            )
        return await asyncio.gather(*avss_tasks)


class HbAvssBatch:
    def __init__(
        self, public_keys, private_key, crs, n, t, my_id, send, recv, pc=None, field=ZR
    ):  # (# noqa: E501)
        self.public_keys, self.private_key = public_keys, private_key
        self.n, self.t, self.my_id = n, t, my_id
        assert len(crs) == 3
        assert len(crs[0]) == t + 1
        self.g = crs[0][0]

        # Create a mechanism to split the `recv` channels based on `tag`
        self.subscribe_recv_task, self.subscribe_recv = subscribe_recv(recv)

        # Create a mechanism to split the `send` channels based on `tag`
        def _send(tag):
            return wrap_send(tag, send)

        self.get_send = _send

        self.field = field
        self.poly = polynomials_over(self.field)
        if pc is not None:
            self.poly_commit = pc
        else:
            self.poly_commit = PolyCommitConst(crs, field=self.field)
            self.poly_commit.preprocess_prover()
            self.poly_commit.preprocess_verifier()

        self.avid_msg_queue = asyncio.Queue()
        self.tasks = []
        self.shares_future = asyncio.Future()
        self.output_queue = asyncio.Queue()

    async def _recv_loop(self, q):
        while True:
            avid, tag, dispersal_msg_list = await q.get()
            self.tasks.append(
                asyncio.create_task(avid.disperse(tag, self.my_id, dispersal_msg_list))
            )

    def __enter__(self):
        self.avid_recv_task = asyncio.create_task(self._recv_loop(self.avid_msg_queue))
        return self

    def __exit__(self, typ, value, traceback):
        self.subscribe_recv_task.cancel()
        self.avid_recv_task.cancel()
        for task in self.tasks:
            task.cancel()

    async def _handle_implication(
        self, avid, tag, ephemeral_public_key, commitments, j, j_pk, j_k
    ):
        """
        Handle the implication of AVSS.
        Return True if the implication is valid, False otherwise.
        """
        # discard if PKj ! = g^SKj
        if self.public_keys[j] != pow(self.g, j_pk):
            return False
        # decrypt and verify
        implicate_msg = await avid.retrieve(tag, j)
        j_shared_key = pow(ephemeral_public_key, j_pk)
        try:
            j_share, j_aux, j_witnesses = SymmetricCrypto.decrypt(
                str(j_shared_key).encode(), implicate_msg
            )[j_k]
        except Exception as e:  # TODO specific exception
            logger.warn("Implicate confirmed, bad encryption:", e)
            return True
        return not self.poly_commit.verify_eval(
            commitments[j_k], j + 1, j_share, j_aux, j_witnesses
        )

    async def _process_avss_msg(self, avss_id, dealer_id, rbc_msg, avid):
        tag = f"{dealer_id}-{avss_id}-B-AVSS"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        def multicast(msg):
            for i in range(self.n):
                send(i, msg)

        # get phi and public key from reliable broadcast msg
        commitments, ephemeral_public_key = loads(rbc_msg)
        # retrieve the z
        dispersal_msg = await avid.retrieve(tag, self.my_id)

        secret_count = len(commitments)

        # all_encrypted_witnesses: n
        shared_key = pow(ephemeral_public_key, self.private_key)

        shares = [None] * secret_count
        auxes = [None] * secret_count
        witnesses = [None] * secret_count
        # Decrypt
        all_shares_valid = True
        try:
            all_wits = SymmetricCrypto.decrypt(str(shared_key).encode(), dispersal_msg)
            for k in range(secret_count):
                shares[k], auxes[k], witnesses[k] = all_wits[k]
        except ValueError as e:  # TODO: more specific exception
            logger.warn(f"Implicate due to failure in decrypting: {e}")
            all_shares_valid = False
            multicast((HbAVSSMessageType.IMPLICATE, self.private_key, 0))

        # call if decryption was successful
        if all_shares_valid:
            if not self.poly_commit.batch_verify_eval(
                commitments, self.my_id + 1, shares, auxes, witnesses
            ):
                all_shares_valid = False
                # Find which share was invalid and implicate
                for k in range(secret_count):
                    if not self.poly_commit.verify_eval(
                        commitments[k],
                        self.my_id + 1,
                        shares[k],
                        auxes[k],
                        witnesses[k],
                    ):  # (# noqa: E501)
                        multicast((HbAVSSMessageType.IMPLICATE, self.private_key, k))
                        break
        if all_shares_valid:
            logger.info(f"OK_timestamp: {time.time()}")
            multicast((HbAVSSMessageType.OK, ""))

        ok_set = set()
        implicate_set = set()
        r1_set = set()
        r2_set = set()
        r1_sent = r2_sent = False
        r1_phi = [None] * self.n
        r2_phi = [None] * self.n
        output = False

        while True:
            # main recv loop for Bracha-style agreement and implicate handling
            sender, avss_msg = await recv()
            # OK
            if avss_msg[0] == HbAVSSMessageType.OK and sender not in ok_set:
                ok_set.add(sender)
            # IMPLICATE
            if (
                avss_msg[0] == HbAVSSMessageType.IMPLICATE
                and sender not in implicate_set
            ):
                implicate_set.add(sender)
            if avss_msg[0] == HbAVSSMessageType.IMPLICATE and not r1_sent:
                # validate the implicate
                if not await self._handle_implication(
                    avid,
                    tag,
                    ephemeral_public_key,
                    commitments,
                    sender,
                    avss_msg[1],
                    avss_msg[2],
                ):
                    continue
                # proceed to share recovery
                logger.debug("[%d] Share recovery activated by %d", self.my_id, sender)
                # setup the coordinates for interpolation
                c_coords = [None] * secret_count
                phi_coords = [None] * secret_count
                aux_coords = [None] * secret_count
                w_coords = [None] * secret_count
                for i in range(secret_count):
                    c_coords[i] = (i, commitments[i])
                    phi_coords[i] = (i, shares[i])
                    aux_coords[i] = (i, auxes[i])
                    w_coords[i] = (i, witnesses[i])
                # interpolate commitments
                interpolated_c = [None] * self.n
                for i in range(self.n):
                    interpolated_c[i] = interpolate_g1_at_x(c_coords, i)
                # if my shares are valid
                if not r1_sent and all_shares_valid:
                    r1_sent = True
                    phi_i = self.poly.interpolate(phi_coords)
                    aux_i = self.poly.interpolate(aux_coords)
                    for j in range(self.n):
                        phi_i_j = phi_i(j)
                        aux_i_j = aux_i(j)
                        w_i_j = interpolate_g1_at_x(w_coords, j)
                        send(j, (HbAVSSMessageType.RECOVERY1, phi_i_j, aux_i_j, w_i_j))
            # R1
            if avss_msg[0] == HbAVSSMessageType.RECOVERY1:
                _, phi_k_i, aux_k_i, w_k_i = avss_msg
                if self.poly_commit.verify_eval(
                    interpolated_c[self.my_id], sender + 1, phi_k_i, aux_k_i, w_k_i
                ):
                    r1_set.add(sender)
                    r1_phi[sender] = phi_k_i
            # R2
            if avss_msg[0] == HbAVSSMessageType.RECOVERY2:
                r2_set.add(sender)
                r2_phi[sender] = avss_msg[1]

            # enough R1 received -> proceed to R2
            if not r2_sent and len(r1_set) >= self.t + 1:
                r2_sent = True
                r1_phi_coords = [
                    (i, r1_phi[i]) for i in range(self.n) if r1_phi[i] is not None
                ]
                phi_i = self.poly.interpolate(r1_phi_coords)
                for j in range(self.n):
                    phi_j_i = phi_i(j)
                    send(j, (HbAVSSMessageType.RECOVERY2, phi_j_i))

            # enough R2 received -> output result
            if len(r2_set) >= 2 * self.t + 1 and not all_shares_valid:
                r2_phi_coords = [
                    (i, r2_phi[i]) for i in range(self.n) if r2_phi[i] is not None
                ]
                r2_phi_poly = self.poly.interpolate(r2_phi_coords)
                for k in range(secret_count):
                    shares[k] = r2_phi_poly(k)
                int_shares = [int(share) for share in shares]
                self.output_queue.put_nowait((dealer_id, avss_id, int_shares))
                output = True
                all_shares_valid = True
                multicast((HbAVSSMessageType.OK, ""))

            # if 2t+1 okay -> output shares
            if len(ok_set) >= 2 * self.t + 1:
                # output result by setting the future value
                if all_shares_valid and not output:
                    int_shares = [int(shares[i]) for i in range(len(shares))]
                    self.output_queue.put_nowait((dealer_id, avss_id, int_shares))
                    output = True

            # Conditions where we can terminate
            if (
                len(ok_set) == self.n
                or len(implicate_set) >= 2 * self.t
                or (len(ok_set) >= 2 * self.t + 1 and r2_sent and output)
            ):
                break

    def _get_dealer_msg(self, values, n):
        # Sample a random degree-(t,t) bivariate polynomial φ(·,·)
        # such that each φ(0,k) = sk and φ(i,k) is Pi’s share of sk
        while len(values) % (self.t + 1) != 0:
            values.append(0)
        secret_count = len(values)
        # batch_count = secret_count/(self.t + 1)
        phi = [None] * secret_count
        commitments = [None] * secret_count
        aux_poly = [None] * secret_count
        # for k ∈ [t+1]
        #   Ck, auxk <- PolyCommit(SP,φ(·,k))
        for k in range(secret_count):
            phi[k] = self.poly.random(self.t, values[k])
            commitments[k], aux_poly[k] = self.poly_commit.commit(phi[k])

        ephemeral_secret_key = self.field.random()
        ephemeral_public_key = pow(self.g, ephemeral_secret_key)
        # for each party Pi and each k ∈ [t+1]
        #   1. w[i][k] <- CreateWitnesss(Ck,auxk,i)
        #   2. z[i][k] <- EncPKi(φ(i,k), w[i][k])
        dispersal_msg_list = [None] * n
        for i in range(n):
            shared_key = pow(self.public_keys[i], ephemeral_secret_key)
            z = [None] * secret_count
            for k in range(secret_count):
                witness = self.poly_commit.create_witness(phi[k], aux_poly[k], i + 1)
                z[k] = (int(phi[k](i + 1)), int(aux_poly[k](i + 1)), witness)
            zz = SymmetricCrypto.encrypt(str(shared_key).encode(), z)
            dispersal_msg_list[i] = zz

        return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    async def avss(self, avss_id, values=None, dealer_id=None, client_mode=False):
        """
        A batched version of avss with share recovery
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

        logger.debug(
            "[%d] Starting Batch AVSS. Id: %s, Dealer Id: %d, Client Mode: %s",
            self.my_id,
            avss_id,
            dealer_id,
            client_mode,
        )

        # In the client_mode, the dealer is the last node
        n = self.n if not client_mode else self.n + 1
        broadcast_msg = None
        dispersal_msg_list = None
        if self.my_id == dealer_id:
            # broadcast_msg: phi & public key for reliable broadcast
            # dispersal_msg_list: the list of payload z
            broadcast_msg, dispersal_msg_list = self._get_dealer_msg(values, n)

        tag = f"{dealer_id}-{avss_id}-B-RBC"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        logger.debug("[%d] Starting reliable broadcast", self.my_id)
        rbc_msg = await reliablebroadcast(
            tag,
            self.my_id,
            n,
            self.t,
            dealer_id,
            broadcast_msg,
            recv,
            send,
            client_mode=client_mode,
        )  # (# noqa: E501)

        tag = f"{dealer_id}-{avss_id}-B-AVID"
        send, recv = self.get_send(tag), self.subscribe_recv(tag)

        logger.debug("[%d] Starting AVID disperse", self.my_id)
        avid = AVID(n, self.t, dealer_id, recv, send, n)

        if client_mode and self.my_id == dealer_id:
            # In client_mode, the dealer is not supposed to do
            # anything after sending the initial value.
            await avid.disperse(tag, self.my_id, dispersal_msg_list, client_mode=True)
            self.shares_future.set_result(True)
            return

        # start disperse in the background
        self.avid_msg_queue.put_nowait((avid, tag, dispersal_msg_list))

        # avss processing
        await self._process_avss_msg(avss_id, dealer_id, rbc_msg, avid)


def get_avss_params(n, t):
    g, h = G1.rand(), G1.rand()
    public_keys, private_keys = [None] * n, [None] * n
    for i in range(n):
        private_keys[i] = ZR.random(0)
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys
