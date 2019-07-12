# coding=utf-8
import logging
import math
import asyncio
from honeybadgermpc.exceptions import HoneyBadgerMPCError
from honeybadgermpc.broadcast.reliablebroadcast import (
    encode,
    decode,
    merkle_tree,
    get_merkle_branch,
    merkle_verify,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
# logger.setLevel(logging.NOTSET)


class AVIDMessageType:
    VAL = "VAL"
    ECHO = "ECHO"
    READY = "READY"
    RETRIEVE = "RETRIEVE"
    RESPONSE = "RESPONSE"


class AVID:
    # Class for Asynchronous Verifiable Information Dispersal
    def __init__(self, n, t, leader, recv, send, input_size):
        """ Initialize the class with parameters:
        :param int n:  at least 3
        :param int f: fault tolerance, ``N >= 3f + 1``
        :param int leader: ``0 <= leader < N``
        :param recv: :func:`recv()` blocks until a message is
            recvd; message is of the form::
            (i, (tag, ...)) = recv()
            where ``tag`` is one of ``{"VAL", "ECHO", "READY"}``
        :param send: sends (without blocking) a message to a designated
            recipient ``send(i, (tag, ...))``
        :param input_size: the size of the input messages to be retrieved
        """
        assert n >= 3 * t + 1
        assert t >= 0
        assert 0 <= leader < n

        self._data = [None] * n
        self.n = n
        self.t = t
        self.leader = leader
        self.recv = recv
        self.send = send
        # size of input_list for disperse
        self.input_size = input_size
        # the response for retrieve
        self.retrieval_queue = asyncio.Queue()
        # the future value OK: retrive will be sent until ok is set
        self.ok_future = asyncio.Future()
        # queue of retrieval requests
        self.retrieval_requests = []

    def broadcast(self, o):
        for i in range(self.n):
            self.send(i, o)

    async def retrieve(self, sid, index):
        """ Retrieve individual item
        :param int index:  the index of retrieval
        """
        # we are able to retrieve things from AVID indivdually
        assert 0 <= index < self.input_size

        # send retrieve after ok is set
        await self.ok_future

        # send retrieve to all the parties
        self.broadcast((sid, AVIDMessageType.RETRIEVE, index))

        result = [None] * self.input_size
        response_set = set()

        # response threshold same as k
        response_threshold = self.t + 1

        while True:  # recv loop for retrieve
            sender, msg = await self.retrieval_queue.get()
            if msg[1] == AVIDMessageType.RESPONSE:
                (_, _, response_index, roothash, data) = msg
                # only retrieve the index we are currently retrieving
                if response_index != index:
                    continue

                if sender in response_set:
                    logger.warning("Redundant RESPONSE from %s", sender)
                    continue

                if not data:
                    logger.warning("Received invalid RESPONSE from %s", sender)
                    continue

                result[sender] = data
                response_set.add(sender)

                if len(response_set) >= response_threshold:
                    # decode the msg on enough response
                    decoded_output = ""
                    try:
                        decoded_output = decode(response_threshold, self.n, result)
                        # Rebuild the merkle tree to guarantee decoding is correct
                        _stripes = encode(response_threshold, self.n, decoded_output)
                        _mt = merkle_tree(_stripes)
                        _roothash = _mt[1]
                        if _roothash != roothash:
                            raise HoneyBadgerMPCError("Failed to verify merkle tree")
                    except Exception as e:
                        logger.error("Failed to decode message: %s", e)

                    logger.info("RETRIEVE complete.")

                    return decoded_output

    async def disperse(self, sid, pid, input_list, client_mode=False):
        """ Main information dispersal handling
        :param int sid: e.x. tag to be used
        :param int pid: current member id
        :param int input_list: the list of message
            for each party from 1 to n from the dealer
        """
        # setup some parameters
        k = self.t + 1  # Wait to reconstruct.
        echo_threshold = math.ceil((self.n + self.t + 1) / 2)  # number of ECHOs needed
        ready_threshold = self.t + 1  # number of READYs needed for READY
        output_threshold = 2 * self.t + 1  # number of READYs needed for future OK

        # leader handling
        if pid == self.leader:
            # The leader erasure encodes the input, sending one strip to each participant
            assert len(input_list) == self.input_size

            # construct the stripe list which contains the stripes for party 1 to party n
            stripes_list = [None] * self.input_size
            mt_list = [None] * self.input_size
            roothash_list = [None] * self.input_size
            for i, m in enumerate(input_list):
                stripes_list[i] = encode(k, self.n, m)
                mt_list[i] = merkle_tree(stripes_list[i])
                roothash_list[i] = mt_list[i][1]

            # transpose for sending
            stripes_list_per_party = [list(i) for i in zip(*stripes_list)]
            for i in range(self.n):
                branch_list = [None] * self.input_size
                for j in range(self.input_size):
                    branch_list[j] = get_merkle_branch(i, mt_list[j])
                # send each person the column of stripes
                self.send(
                    i,
                    (
                        sid,
                        AVIDMessageType.VAL,
                        roothash_list,
                        branch_list,
                        stripes_list_per_party[i],
                    ),
                )
            if client_mode:
                return

        # counters and variables for msg
        echo_set = set()
        ready_set = set()
        ready_sent = False
        from_leader = None
        # internal storage
        my_stripes = None
        my_roothash_list = None

        while True:  # main recv loop
            sender, msg = await self.recv()
            if msg[1] == AVIDMessageType.VAL and from_leader is None:
                # Validation
                (_, _, roothash_list, branch_list, stripes_for_each) = msg
                if sender != self.leader:
                    logger.warning(
                        "[%d] VAL message from other than leader: %d", pid, sender
                    )
                    continue

                # merkle tree verification
                validation_fail_flag = False
                for i in range(len(stripes_for_each)):
                    # verify each entry in the stripes
                    if not merkle_verify(
                        self.n,
                        stripes_for_each[i],
                        roothash_list[i],
                        branch_list[i],
                        pid,
                    ):
                        logger.error("[%d]Failed to validate VAL message", pid)
                        validation_fail_flag = True
                        break
                if validation_fail_flag:
                    continue

                # Update and store the stripes & roothashes for retrieve
                from_leader = pid
                my_stripes = stripes_for_each
                my_roothash_list = roothash_list

                # echo others
                self.broadcast((sid, AVIDMessageType.ECHO))

            elif msg[1] == AVIDMessageType.ECHO:
                # Validation
                if sender in echo_set:
                    logger.warning("[%d] Redundant ECHO", pid)
                    continue
                # Update
                echo_set.add(sender)

            elif msg[1] == AVIDMessageType.READY:
                # Validation
                if sender in ready_set:
                    logger.warning("[%d] Redundant READY", pid)
                    continue
                # Update
                ready_set.add(sender)

            elif msg[1] == AVIDMessageType.RETRIEVE:
                _, _, index = msg
                # send the response sender requested
                if not self.ok_future.done() and my_stripes is not None:
                    # enqueue a retrieve request
                    self.retrieval_requests.append((sender, index))
                else:
                    self.send(
                        sender,
                        (
                            sid,
                            AVIDMessageType.RESPONSE,
                            index,
                            my_roothash_list[index],
                            my_stripes[index],
                        ),
                    )

            elif msg[1] == AVIDMessageType.RESPONSE:
                # put in the queue for retrieve
                self.retrieval_queue.put_nowait((sender, msg))

            if len(echo_set) >= echo_threshold and not ready_sent:
                ready_sent = True
                self.broadcast((sid, AVIDMessageType.READY))

            # Amplify ready messages
            if len(ready_set) >= ready_threshold and not ready_sent:
                ready_sent = True
                self.broadcast((sid, AVIDMessageType.READY))

            if len(ready_set) >= output_threshold and len(echo_set) >= k:
                # update ok future indicating ready for retrieve
                if not self.ok_future.done():
                    self.ok_future.set_result(True)

            # Handle deferred requests
            if self.ok_future.done() and my_stripes is not None:
                for (sender, index) in self.retrieval_requests:
                    logging.info(
                        "Sending deferred response sender:%s index:%s", sender, index
                    )
                    self.send(
                        sender,
                        (
                            sid,
                            AVIDMessageType.RESPONSE,
                            index,
                            my_roothash_list[index],
                            my_stripes[index],
                        ),
                    )
                self.retrieval_requests.clear()
