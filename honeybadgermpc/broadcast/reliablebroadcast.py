# coding=utf-8
from collections import defaultdict
import zfec
import logging
import hashlib
import math


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
# logger.setLevel(logging.NOTSET)


#####################
#    zfec encode    #
#####################
def encode(k, n, m):
    """Erasure encodes string ``m`` into ``n`` blocks, such that any ``k``
    can reconstruct.
    :param int k: k
    :param int n: number of blocks to encode string ``m`` into.
    :param bytes m: bytestring to encode.
    :return list: Erasure codes resulting from encoding ``m`` into
        ``n`` blocks using ``zfec`` lib.
    """
    try:
        m = m.encode()
    except AttributeError:
        pass
    encoder = zfec.Encoder(k, n)
    assert k <= 256  # TODO: Record this assumption!
    # pad m to a multiple of K bytes
    padlen = k - (len(m) % k)
    m += padlen * chr(k - padlen).encode()
    step = len(m) // k
    blocks = [m[i * step : (i + 1) * step] for i in range(k)]
    stripes = encoder.encode(blocks)
    return stripes


def decode(k, n, stripes):
    """Decodes an erasure-encoded string from a subset of stripes
    :param list stripes: a container of :math:`n` elements,
        each of which is either a string or ``None``
        at least :math:`k` elements are strings
        all string elements are the same length
    """
    assert len(stripes) == n
    blocks = []
    blocknums = []
    for i, block in enumerate(stripes):
        if block is None:
            continue
        blocks.append(block)
        blocknums.append(i)
        if len(blocks) == k:
            break
    else:
        raise ValueError("Too few to recover")
    decoder = zfec.Decoder(k, n)
    rec = decoder.decode(blocks, blocknums)
    m = b"".join(rec)
    padlen = k - m[-1]
    m = m[:-padlen]
    return m


#####################
#    Merkle tree    #
#####################
def hash(x):
    assert isinstance(x, (str, bytes))
    try:
        x = x.encode()
    except AttributeError:
        pass
    return hashlib.sha256(x).digest()


def ceil(x):
    return int(math.ceil(x))


def merkle_tree(str_list):
    """Builds a merkle tree from a list of :math:`n` strings (:math:`n`
    at least 1)
    :return list: Merkle tree, a list of ``2*ceil(n)`` strings. The root
         digest is at ``tree[1]``, ``tree[0]`` is blank.
    """
    n = len(str_list)
    assert n >= 1
    bottomrow = 2 ** ceil(math.log(n, 2))
    mt = [b""] * (2 * bottomrow)
    for i in range(n):
        mt[bottomrow + i] = hash(str_list[i])
    for i in range(bottomrow - 1, 0, -1):
        mt[i] = hash(mt[i * 2] + mt[i * 2 + 1])
    return mt


def get_merkle_branch(index, mt):
    """Computes a merkle tree from a list of leaves.
    """
    res = []
    t = index + (len(mt) >> 1)
    while t > 1:
        res.append(mt[t ^ 1])  # we are picking up the sibling
        t //= 2
    return res


def merkle_verify(n, val, root_hash, branch, index):
    """Verify a merkle tree branch proof
    """
    assert 0 <= index < n
    # XXX Python 3 related issue, for now let's tolerate both bytes and
    # strings
    assert isinstance(val, (str, bytes))
    assert len(branch) == ceil(math.log(n, 2))
    # Index has information on whether we are facing a left sibling or a right sibling
    tmp = hash(val)
    tindex = index
    for br in branch:
        tmp = hash((tindex & 1) and br + tmp or tmp + br)
        tindex >>= 1
    if tmp != root_hash:
        logger.info(
            f"Verification failed with {hash(val)} {root_hash} \
        {branch} {tmp == root_hash}"
        )
        return False
    return True


async def reliablebroadcast(
    sid, pid, n, f, leader, input, receive, send, client_mode=False
):  # (# noqa: E501)
    """Reliable broadcast
    :param int pid: ``0 <= pid < N``
    :param int N:  at least 3
    :param int f: fault tolerance, ``N >= 3f + 1``
    :param int leader: ``0 <= leader < N``
    :param input: if ``pid == leader``, then :func:`input()` is called
        to wait for the input value
    :param receive: :func:`receive()` blocks until a message is
        received; message is of the form::
            (i, (tag, ...)) = receive()
        where ``tag`` is one of ``{"VAL", "ECHO", "READY"}``
    :param send: sends (without blocking) a message to a designed
        recipient ``send(i, (tag, ...))``
    :return str: ``m`` after receiving :math:`2f+1` ``READY`` messages
        and :math:`N-2f` ``ECHO`` messages
        .. important:: **Messages**
            ``VAL( roothash, branch[i], stripe[i] )``
                sent from ``leader`` to each other party
            ``ECHO( roothash, branch[i], stripe[i] )``
                sent after receiving ``VAL`` message
            ``READY( roothash )``
                sent after receiving :math:`N-f` ``ECHO`` messages
                or after receiving :math:`f+1` ``READY`` messages
    .. todo::
        **Accountability**
        A large computational expense occurs when attempting to
        decode the value from erasure codes, and recomputing to check it
        is formed correctly. By transmitting a signature along with
        ``VAL`` and ``ECHO``, we can ensure that if the value is decoded
        but not necessarily reconstructed, then evidence incriminates
        the leader.
    """
    assert n >= 3 * f + 1
    assert f >= 0
    assert 0 <= leader < n
    assert 0 <= pid < n

    k = n - 2 * f  # Wait to reconstruct. (# noqa: E221)
    echo_threshold = n - f  # Wait for ECHO to send READY. (# noqa: E221)
    ready_threshold = f + 1  # Wait for READY to amplify. (# noqa: E221)
    output_threshold = 2 * f + 1  # Wait for this many READY to output
    # NOTE: The above thresholds  are chosen to minimize the size
    # of the erasure coding stripes, i.e. to maximize K.
    # The following alternative thresholds are more canonical
    # (e.g., in Bracha '86) and require larger stripes, but must wait
    # for fewer nodes to respond
    #   EchoThreshold = ceil((N + f + 1.)/2)
    #   K = EchoThreshold - f

    def broadcast(o):
        for i in range(n):
            send(i, o)

    if pid == leader:
        # The leader erasure encodes the input, sending one strip to each participant
        m = input  # block until an input is received
        # XXX Python 3 related issue, for now let's tolerate both bytes and
        # strings
        # (with Python 2 it used to be: assert type(m) is str)
        assert isinstance(m, (str, bytes))
        logger.debug("[%d] Input received: %d bytes" % (pid, len(m)))

        stripes = encode(k, n, m)
        mt = merkle_tree(stripes)  # full binary tree
        roothash = mt[1]

        for i in range(n):
            branch = get_merkle_branch(i, mt)
            send(i, (sid, "VAL", roothash, branch, stripes[i]))

        if client_mode:
            return

    # TODO: filter policy: if leader, discard all messages until sending VAL

    from_leader = None
    stripes = defaultdict(lambda: [None for _ in range(n)])
    echo_counter = defaultdict(lambda: 0)
    echo_senders = set()  # Peers that have sent us ECHO messages
    ready = defaultdict(set)
    ready_sent = False
    ready_senders = set()  # Peers that have sent us READY messages

    def decode_output(roothash):
        # Rebuild the merkle tree to guarantee decoding is correct
        m = decode(k, n, stripes[roothash])
        _stripes = encode(k, n, m)
        _mt = merkle_tree(_stripes)
        _roothash = _mt[1]
        # TODO: Accountability: If this fails, incriminate leader
        assert _roothash == roothash
        return m

    while True:  # main receive loop
        sender, msg = await receive()
        if msg[1] == "VAL" and from_leader is None:
            # Validation
            (_, _, roothash, branch, stripe) = msg
            if sender != leader:
                logger.info(f"[{pid}] VAL message from other than leader: {sender}")
                continue
            try:
                assert merkle_verify(n, stripe, roothash, branch, pid)
            except Exception as e:
                logger.info(f"[{pid}]Failed to validate VAL message: {e}")
                continue

            # Update
            from_leader = roothash
            broadcast((sid, "ECHO", roothash, branch, stripe))

        elif msg[1] == "ECHO":
            (_, _, roothash, branch, stripe) = msg
            # Validation
            if (
                roothash in stripes
                and stripes[roothash][sender] is not None
                or sender in echo_senders
            ):
                logger.info("[{pid}] Redundant ECHO")
                continue

            # We can optimistically skip the merkleVerify for "ECHO", because the
            # entire merkle tree is checked later anyway.

            # try:
            #     assert merkleVerify(N, stripe, roothash, branch, sender)
            # except AssertionError as e:
            # logger.debug(f"Failed to validate ECHO message: {e}")
            #     continue

            # Update
            stripes[roothash][sender] = stripe
            echo_senders.add(sender)
            echo_counter[roothash] += 1

            if echo_counter[roothash] >= echo_threshold and not ready_sent:
                ready_sent = True
                broadcast((sid, "READY", roothash))

            if len(ready[roothash]) >= output_threshold and echo_counter[roothash] >= k:
                return decode_output(roothash)

        elif msg[1] == "READY":
            (_, _, roothash) = msg
            # Validation
            if sender in ready[roothash] or sender in ready_senders:
                logger.info("[{pid}] Redundant READY")
                continue

            # Update
            ready[roothash].add(sender)
            ready_senders.add(sender)

            # Amplify ready messages
            if len(ready[roothash]) >= ready_threshold and not ready_sent:
                ready_sent = True
                broadcast((sid, "READY", roothash))

            if len(ready[roothash]) >= output_threshold and echo_counter[roothash] >= k:
                return decode_output(roothash)
