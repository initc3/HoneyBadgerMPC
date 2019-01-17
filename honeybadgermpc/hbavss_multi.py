from Crypto.Cipher import AES
from Crypto import Random
import hashlib
import os
import pickle
import asyncio
from asyncio import Queue
import logging
import concurrent.futures
import psutil
import sys
from .exceptions import ConfigurationError
from .config import load_config
from .ipc import NodeDetails, ProcessProgramRunner

# secretshare uses reliable broadcast as a sub protocol
from honeybadgermpc.reliablebroadcast import reliablebroadcast

# This is necessary to specialize the library to BLS12-381
# TODO: the `betterpairing` interface is a work in progress.
# For now we rely on the `pypairing` interface anyway.
# When `pypairing` is improved we'll use that.
from honeybadgermpc.betterpairing import G1, ZR
total_time = 0.0


# Run in an executor!
async def _run_in_thread(func, *args):
    global _HBAVSS_Executor
    if '_HBAVSS_Executor' not in globals():
        logging.info('Initializing executor')
        cpus = psutil.cpu_count(logical=False)
        _HBAVSS_Executor = concurrent.futures.ThreadPoolExecutor(max_workers=cpus)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_HBAVSS_Executor, func, *args)


######################
# Polynomial functions
######################

# TODO: These should be incorporated into polynomial.py
# polynomial.py is already inspired by j2kun, and the
# j2kun library already includes this functionality.

def polynomial_divide(numerator, denominator):
    temp = list(numerator)
    factors = []
    while len(temp) >= len(denominator):
        diff = len(temp) - len(denominator)
        factor = temp[len(temp) - 1] / denominator[len(denominator) - 1]
        factors.insert(0, factor)
        for i in range(len(denominator)):
            temp[i+diff] = temp[i+diff] - (factor * denominator[i])
        temp = temp[:len(temp)-1]
    return factors


def polynomial_multiply_constant(poly1, c):
    product = [None] * len(poly1)
    for i in range(len(product)):
        product[i] = poly1[i] * c
    return product


def polynomial_multiply(poly1, poly2):
    myzero = ZR(0)
    product = [myzero] * (len(poly1) + len(poly2) - 1)
    for i in range(len(poly1)):
        temp = polynomial_multiply_constant(poly2, poly1[i])
        while i > 0:
            temp.insert(0, myzero)
            i -= 1
        product = polynomial_add(product, temp)
    return product


def polynomial_add(poly1, poly2):
    if len(poly1) >= len(poly2):
        bigger = poly1
        smaller = poly2
    else:
        bigger = poly2
        smaller = poly1
    polysum = [None] * len(bigger)
    for i in range(len(bigger)):
        polysum[i] = bigger[i]
        if i < len(smaller):
            polysum[i] = polysum[i] + smaller[i]
    return polysum


def polynomial_subtract(poly1, poly2):
    negpoly2 = polynomial_multiply_constant(poly2, -1)
    return polynomial_add(poly1, negpoly2)


# Polynomial evaluation

def f(poly, x):
    assert type(poly) is list
    y = ZR(0)
    xx = ZR(1)
    for coeff in poly:
        y += coeff * xx
        xx *= x
    return y


def f_horner(poly, x):
    assert type(poly) is list
    k = len(poly) - 1
    b = ZR(0)
    for (i, coeff) in enumerate(poly):
        b *= x
        b += poly[k-i]
    return b


# Polynomial interpolation

def interpolate_at_x(coords, x, order=-1):
    if order == -1:
        order = len(coords)
    xs = []
    sortedcoords = sorted(coords, key=lambda x: x[0])
    for coord in sortedcoords:
        xs.append(coord[0])
    S = set(xs[0:order])
    # The following line makes it so this code works for both members of G and ZR
    out = coords[0][1] - coords[0][1]
    for i in range(order):
        out += (lagrange_at_x(S, xs[i], x) * sortedcoords[i][1])
    return out


def lagrange_at_x(S, j, x):
    S = sorted(S)
    assert j in S
    l1 = [x - jj for jj in S if jj != j]
    l2 = [j - jj for jj in S if jj != j]
    (num, den) = (ZR(1), ZR(1))
    for item in l1:
        num *= item
    for item in l2:
        den *= item
    return num / den


def interpolate_poly(coords):
    myone = ZR(1)
    myzero = ZR(0)
    logging.debug(
        "Before: " + str(coords[0][1]) + " After: " + str(myzero + coords[0][1]))
    poly = [myzero] * len(coords)
    for i in range(len(coords)):
        temp = [myone]
        for j in range(len(coords)):
            if i == j:
                continue
            temp = polynomial_multiply(
                temp, [-1 * (coords[j][0] * myone), myone])
            temp = polynomial_divide(
                temp, [myone * coords[i][0] - myone * coords[j][0]])
        poly = polynomial_add(
            poly, polynomial_multiply_constant(temp, coords[i][1]))
    return poly


#####################################
# Symmetric encryption
#####################################

# Symmetric cryptography.
# Uses AES with a 32-byte key
# Semantic security (iv is randomized)

# Copied from honeybadgerbft

BS = 16


def pad(s): return s + (BS - len(s) % BS) * bytes([BS - len(s) % BS])


def unpad(s): return s[:-ord(s[len(s)-1:])]


def encrypt(key, raw):
    """ """
    key = hashlib.sha256(key).digest()  # hash the key
    assert len(key) == 32
    raw = pad(pickle.dumps(raw))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    enc = (iv + cipher.encrypt(raw))
    return enc


def decrypt(key, enc):
    """ """
    key = hashlib.sha256(key).digest()  # hash the key
    assert len(key) == 32
    enc = (enc)
    iv = enc[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return pickle.loads(unpad(cipher.decrypt(enc[16:])))


########################
# Polynomial commitments
########################

class PolyCommitNP:
    def __init__(self, t, pk):
        self.g = pk[0].duplicate()
        self.h = pk[1].duplicate()
        self.t = t

    def commit(self, poly, secretpoly):
        # initPP?
        cs = []
        for i in range(self.t+1):
            c = (self.g**poly[i])*(self.h**secretpoly[i])
            cs.append(c)
        return cs

    def verify_eval(self, c, i, polyeval, secretpolyeval, witness=None):
        lhs = G1.one()
        for j in range(len(c)):
            lhs *= c[j]**(i**j)
        rhs = (self.g**polyeval)*(self.h**secretpolyeval)
        return lhs == rhs


##########################################
# Dealer part of the hbavss-light protocol
##########################################

# Class representing a the dealer in the scheme.
# t is the threshold and k is the number of participants
class HbAvssDealer:
    def __init__(self, publicparams, privateparams, send, recv):
        # Random polynomial coefficients constructed in the form
        # [c       x        x^2        ...  x^t]
        # This is structured so that t+1 points are needed to reconstruct the polynomial
        time2 = os.times()
        nodeid = os.environ.get('HBMPC_NODE_ID')
        self.benchmarkLogger = logging.LoggerAdapter(
            logging.getLogger("benchmark_logger"), {"node_id": nodeid})
        (t, n, crs, participantids, participantkeys, dealerid, sid) = publicparams
        (secret, pid) = privateparams
        assert dealerid == pid, "HbAvssDealer called, but wrong pid"
        (poly, polyhat, sharedkeys, shares, encryptedshares,
         witnesses, encryptedwitnesses) = ([], [], {}, {}, {}, {}, {})
        for i in range(t+1):
            poly.append(ZR.rand())
            polyhat.append(ZR.rand())
        poly[0] = ZR(secret)
        sk = ZR.rand()
        for j in participantids:
            sharedkeys[j] = participantkeys[j] ** sk
        pc = PolyCommitNP(t=t, pk=crs)
        c = pc.commit(poly, polyhat)
        for j in participantids:
            shares[j] = f_horner(poly, j+1)  # TODO: make this omega^j
            encryptedshares[j] = encrypt(
                str(sharedkeys[j]).encode('utf-8'), shares[j])
            witnesses[j] = f_horner(polyhat, j+1)
            encryptedwitnesses[j] = encrypt(
                str(sharedkeys[j]).encode('utf-8'), witnesses[j])
        message = pickle.dumps(
            (c, encryptedwitnesses, encryptedshares, crs[0] ** sk))

        dealer_time = str(os.times()[4] - time2[4])
        logging.info("Dealer Time: " + dealer_time)
        # benchmarking: time taken by dealer
        self.benchmarkLogger.info("AVSS dealer time:  " + dealer_time)

        self._task = reliablebroadcast(
            sid, pid=pid, N=n+1, f=t, leader=pid, input=message, receive=recv, send=send)

    async def run(self):
        return await self._task


#################################################
# The recipient part of the hbavss-light protocol
#################################################

# Class representing a participant in the scheme.
# t is the threshold and k is the number of participants
class HbAvssRecipient:
    def __init__(self, publicparams, privateparams, send, recv, reconstruction=False):

        (self.send, self.recv) = (send, recv)
        # self.write = write_function
        (self.t, self.n, crs, self.participantids,
         self.participantkeys, self.dealerid, self.sid) = publicparams
        logging.info('[CTR] sid is ' + str(self.sid))
        self.reconstruction = reconstruction
        nodeid = os.environ.get('HBMPC_NODE_ID')
        self.benchmarkLogger = logging.LoggerAdapter(
            logging.getLogger("benchmark_logger"), {"node_id": nodeid})
        (self.pid, self.sk) = privateparams
        assert self.pid != self.dealerid, "HbAvssRecipient, but pid is dealerid"
        (self.sharedkey, self.rbfinished, self.finished, self.sendrecs,
         self.sharevalid) = (None, False, False, False, False)
        (self.okcount, self.implicatecount,
         self.output, self.secret) = (0, 0, None, None)
        self.pc = PolyCommitNP(t=self.t, pk=crs)
        (self.shares, self.queues, self.recvs) = ({}, {}, {})
        msgtypes = ["rb", "hbavss"]
        for msgtype in msgtypes:
            self.queues[msgtype] = Queue()
            self.recvs[msgtype] = self.makeRecv(msgtype)
        self.time2 = os.times()
        loop = asyncio.get_event_loop()
        loop.create_task(rbc_and_send(self.sid, self.pid, self.n+1,
                                      self.t, self.dealerid, None,
                                      self.recvs["rb"], send))
        # rb_thread = Greenlet(rbc_and_send, sid, pid, k+1,
        #   f=t, leader=k, input=None, receive=self.recvs["rb"], send)
        # rb_thread.start()
        # send(pid, ["send", reliablebroadcast(sid, pid, k+1,
        #   f=t, leader=k, input=None, receive=self.recvs["rb"], send=send)])
        # loop.create_task(self.run())

    async def run(self):
        logging.info('[{}] RUN STARTED'.format(self.sid))
        while not self.finished:
            logging.debug('recvd message ')
            sender, msg = await self.recv()
            await self.receive_msg(sender, msg)

    async def receive_msg(self, sender, msg):
        start_time = os.times()
        if msg[1] in ["READY", "ECHO", "VAL"]:
            self.queues["rb"].put_nowait((sender, msg))
        if msg[1] == "send":
            self.rbfinished = True
            decrypt_start_time = os.times()
            self.benchmarkLogger.info("Begin Decryption")
            logging.info("[{}]Begin Decryption".format(self.sid))
            message = pickle.loads(msg[2])
            logging.info(" Pickle time " + str(os.times()[4] - decrypt_start_time[4]))
            (self.commit, self.encwitnesses, self.encshares, pk_d) = message

            # self.sharedkey = str(pk_d**self.sk).encode('utf-8')
            self.sharedkey = await _run_in_thread(lambda: str(pk_d**self.sk)
                                                  .encode('utf-8'))

            self.share = decrypt(self.sharedkey, self.encshares[self.pid])
            self.witness = decrypt(self.sharedkey, self.encwitnesses[self.pid])
            # if self.pc.verify_eval(self.commit, self.pid+1, self.share, self.witness):
            if await _run_in_thread(self.pc.verify_eval, self.commit,
                                    self.pid+1, self.share, self.witness):
                decryption_time = (os.times()[4] - decrypt_start_time[4])
                logging.info(
                    "[{}] decryption time : ".format(self.sid) + str(decryption_time))
                self.benchmarkLogger.info("decryption time :  " + str(decryption_time))
                global total_time
                total_time += decryption_time
                self.send_ok_msgs()
                self.sendrecs = True
            else:
                logging.info("verifyeval failed")
                self.send_implicate_msgs()
            while not self.queues["hbavss"].empty():
                (i, o) = self.queues["hbavss"].get_nowait()
                await self.receive_msg(i, o)
        if not self.rbfinished:
            self.queues["hbavss"].put_nowait((sender, msg))
        elif msg[1] == "ok":
            # TODO: Enforce one OK message per participant
            logging.debug(str(self.pid) + " got an ok from " + str(sender))
            self.okcount += 1
            del self.encshares[sender]
            del self.encwitnesses[sender]
            if not self.sharevalid and self.okcount >= 2*self.t + 1:
                self.sharevalid = True
                self.output = self.share

                logging.info('[{}] Output available'.format(self.sid), self.output)
                recipient_time = str(os.times()[4] - self.time2[4])
                logging.info("[{}] Recipient Time: ".format(self.sid) + recipient_time)
                service_time = str(os.times()[4] - start_time[4])
                logging.info("[{}] Total service Time: ".format(self.sid) + service_time)

                # benchmarking: time taken by dealer
                self.benchmarkLogger.info(
                    "AVSS recipient time:  " + recipient_time)

                if self.reconstruction and self.sendrecs:
                    self.send_rec_msgs()
                    self.sendrecs = False
            # TODO: Fix this part so it's fault tolerant
            if self.okcount == self.n and not self.reconstruction:
                self.finished = True
        elif msg[1] == 'implicate':
            if self.check_implication(int(sender), msg[2], msg[3]):
                self.implicatecount += 1
                if self.implicatecount == 2*self.t+1:
                    logging.info("Output: None")
                    self.share = None
                    self.finished = True
                if self.sendrecs:
                    self.reconstruction = True
                    self.send_rec_msgs()
                    self.sentdrecs = False
            else:
                logging.debug("Bad implicate!")
                self.okcount += 1
                del self.encshares[sender]
                del self.encwitnesses[sender]
        elif msg[1] == 'rec':
            if self.pc.verify_eval(self.commit, sender+1, msg[2], msg[3]):
                self.shares[sender] = msg[2]
            if len(self.shares) == self.t + 1:
                coords = []
                for key, value in self.shares.items():
                    coords.append([key + 1, value])
                self.secret = interpolate_at_x(coords, 0)
                logging.info(f"self.secret: {self.secret}")
                self.finished = True

    # checks if an implicate message is valid
    def check_implication(self, implicatorid, key, proof):
        # First check if they key that was sent is valid
        raise NotImplementedError
        # if not check_same_exponent_proof(proof, self.pk[0],
        #         self.participantkeys[self.dealerid],
        #         self.participantkeys[implicatorid], key):
        #    #logging.debug("Bad Key!")
        #     return False
        # share = decrypt(str(key), self.encshares[implicatorid])
        # witness = decrypt(str(key), self.encwitnesses[implicatorid])
        # return not self.pc.verify_eval(self.commit, implicatorid, share, witness)

    def send_ok_msgs(self):
        msg = []
        msg.append(self.sid)
        msg.append("ok")
        for j in self.participantids:
            self.send(j, msg)

    def send_implicate_msgs(self):
        raise NotImplementedError
        # msg = []
        # msg.append(self.sid)
        # msg.append("implicate")
        # msg.append(self.sharedkey)
        # msg.append(prove_same_exponent(
        #     self.pk[0], self.participantkeys[self.dealerid], self.sk))
        # for j in self.participantids:
        #     self.send(j, msg)

    def send_rec_msgs(self):
        msg = []
        msg.append(self.sid)
        msg.append("rec")
        msg.append(self.share)
        msg.append(self.witness)
        for j in self.participantids:
            self.send(j, msg)

    def makeRecv(self, msgtype):
        async def _recv():
            (i, o) = await self.queues[msgtype].get()
            return (i, o)
        return _recv


async def rbc_and_send(sid, pid, n, t, k, ignoreme, receive, send):
    msg = await reliablebroadcast(sid, pid, n, f=t, leader=k,
                                  input=None, receive=receive, send=send)
    send(pid, [sid, "send", msg])


################
# Driver script
################

# Run as either node or dealer, depending on command line arguments
# Uses the same configuration format as hbmpc

async def runHBAVSSLightMulti(config, N, t, id, k):
    programRunner = ProcessProgramRunner(config, N+1, t, id)
    sender, listener = programRunner.senders, programRunner.listener
    # Need to give time to the listener coroutine to start
    #  or else the sender will get a connection refused.
    logging.info(f"{N} {t} {k}")
    # XXX HACK! Increase wait time. Must find better way if possible -- e.g:
    # try/except retry logic ...
    await asyncio.sleep(2)
    await sender.connect()
    await asyncio.sleep(1)

    # Generate the CRS deterministically
    crs = [G1.rand(seed=[0, 0, 0, 1]), G1.rand(seed=[0, 0, 0, 2])]

    # Load private parameters / secret keys
    (participantpubkeys, participantprivkeys) = ({}, {})
    participantids = list(range(N))
    for i in participantids:
        # These can also be determined pseudorandomly
        sk = ZR.rand(seed=17+i)
        participantprivkeys[i] = sk
        participantpubkeys[i] = crs[0] ** sk

    # Form public parameters
    dealerid = N
    tasks = []
    sends = []
    recvs = []
    for i in range(k):
        send, recv = programRunner.getSendAndRecv(i)
        sends.append(send)
        recvs.append(recv)
    # Launch the protocol
    if id == dealerid:
        for i in range(k):
            pubparams = (t, N, crs, participantids, participantpubkeys, dealerid, str(i))
            # send, recv = programRunner.getSendAndRecv(i)
            thread = HbAvssDealer(pubparams, (42, id), sends[i], recvs[i])
            tasks.append(thread)
    else:
        myPrivateKey = participantprivkeys[id]
        for i in range(k):
            pubparams = (t, N, crs, participantids, participantpubkeys, dealerid, str(i))
            # send, recv = programRunner.getSendAndRecv(i)
            thread = HbAvssRecipient(pubparams, (id, myPrivateKey),
                                     sends[i], recvs[i], reconstruction=False)
            tasks.append(thread)
    # Wait for results and clean up
    await asyncio.gather(*[task.run() for task in tasks])
    await asyncio.sleep(2)
    await sender.close()
    await listener.close()
    await asyncio.sleep(1)
    logging.info('Total decrypt time ' + str(total_time))
    nodeid = os.environ.get('HBMPC_NODE_ID')
    benchmarkLogger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": nodeid})
    benchmarkLogger.info('Total decrypt time ' + str(total_time))

############################
#  Configuration for hbavss
###########################


def make_localhost_config(n, t, base_port):
    from configparser import ConfigParser
    config = ConfigParser()

    # General
    config['general']['N'] = n
    config['general']['t'] = t
    config['general']['skipPreProcessing'] = True

    # Peers
    for i in range(n+1):  # n participants, 1 client
        config['peers'][i] = "%s:%d" % ('localhost', base_port + i)

    # Keys
    # Keys are omitted for now

    # Write file
    with open('conf/hbavss.ini', 'w') as configfile:
        config.write(configfile)


def main():
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
                                 ' or a config file must be given as first argument.')

    config_dict = load_config(configfile)
    N = config_dict['N']
    t = config_dict['t']
    k = config_dict['k']
    nodeid = int(nodeid)
    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        (loop.run_until_complete(runHBAVSSLightMulti(network_info, N, t, nodeid, k)))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
