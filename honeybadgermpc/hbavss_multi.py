import os
import pickle
import asyncio
from asyncio import Queue
import logging
import concurrent.futures
import psutil
from .config import HbmpcConfig
from .ipc import ProcessProgramRunner

from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit import PolyCommit
from honeybadgermpc.symmetric_crypto import SymmetricCrypto

# secretshare uses reliable broadcast as a sub protocol
from honeybadgermpc.protocols.reliablebroadcast import reliablebroadcast

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
        (sharedkeys, shares, encryptedshares,
         witnesses, encryptedwitnesses) = ({}, {}, {}, {}, {})
        poly = polynomials_over(use_rust=True).random(t, secret)
        sk = ZR.random()
        for j in participantids:
            sharedkeys[j] = participantkeys[j] ** sk
        pc = PolyCommit(crs[0].duplicate(), crs[1].duplicate())
        c, polyhat = pc.commit(poly)
        for j in participantids:
            shares[j] = poly(j+1)  # TODO: make this omega^j
            key = str(sharedkeys[j]).encode('utf-8')
            encryptedshares[j] = SymmetricCrypto.encrypt(key, shares[j])
            witnesses[j] = pc.create_witness(polyhat, j+1)
            encryptedwitnesses[j] = SymmetricCrypto.encrypt(key, witnesses[j])
        message = pickle.dumps(
            (c, encryptedwitnesses, encryptedshares, crs[0] ** sk))

        dealer_time = str(os.times()[4] - time2[4])
        logging.info("Dealer Time: " + dealer_time)
        # benchmarking: time taken by dealer
        self.benchmarkLogger.info("AVSS dealer time:  " + dealer_time)

        self._task = reliablebroadcast(
            sid, pid=pid, n=n+1, f=t, leader=pid, input=message, receive=recv, send=send)

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
        self.pc = PolyCommit(crs[0].duplicate(), crs[1].duplicate())
        (self.shares, self.queues, self.recvs) = ({}, {}, {})
        msgtypes = ["rb", "hbavss"]
        for msgtype in msgtypes:
            self.queues[msgtype] = Queue()
            self.recvs[msgtype] = self.make_recv(msgtype)
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

            self.share = SymmetricCrypto.decrypt(
                self.sharedkey, self.encshares[self.pid])
            self.witness = SymmetricCrypto.decrypt(
                self.sharedkey, self.encwitnesses[self.pid])
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

                logging.info(f'[{self.sid}] Output available: {self.output}')
                recipient_time = str(os.times()[4] - self.time2[4])
                logging.info(f"[{self.sid}] Recipient Time: {recipient_time}")
                service_time = str(os.times()[4] - start_time[4])
                logging.info(f"[{self.sid}] Total service Time: {service_time}")

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
                self.secret = polynomials_over(use_rust=True).interpolate_at(coords, 0)
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

    def make_recv(self, msgtype):
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

async def run_hbavss_light_multi(config, n, t, id, k):
    program_runner = ProcessProgramRunner(config, n+1, t, id)
    # Need to give time to the listener coroutine to start
    #  or else the sender will get a connection refused.
    logging.info(f"{n} {t} {k}")
    await program_runner.start()
    # Generate the CRS deterministically
    crs = [G1.rand(seed=[0, 0, 0, 1]), G1.rand(seed=[0, 0, 0, 2])]

    # Load private parameters / secret keys
    (participantpubkeys, participantprivkeys) = ({}, {})
    participantids = list(range(n))
    for i in participantids:
        # These can also be determined pseudorandomly
        sk = ZR.random(seed=17+i)
        participantprivkeys[i] = sk
        participantpubkeys[i] = crs[0] ** sk

    # Form public parameters
    dealerid = n
    tasks = []
    sends = []
    recvs = []
    for i in range(k):
        send, recv = program_runner.get_send_and_recv(i)
        sends.append(send)
        recvs.append(recv)
    # Launch the protocol
    if id == dealerid:
        for i in range(k):
            pubparams = (t, n, crs, participantids, participantpubkeys, dealerid, str(i))
            # send, recv = programRunner.getSendAndRecv(i)
            thread = HbAvssDealer(pubparams, (42, id), sends[i], recvs[i])
            tasks.append(thread)
    else:
        my_private_key = participantprivkeys[id]
        for i in range(k):
            pubparams = (t, n, crs, participantids, participantpubkeys, dealerid, str(i))
            # send, recv = programRunner.getSendAndRecv(i)
            thread = HbAvssRecipient(pubparams, (id, my_private_key),
                                     sends[i], recvs[i], reconstruction=False)
            tasks.append(thread)
    # Wait for results and clean up
    await asyncio.gather(*[task.run() for task in tasks])
    await program_runner.close()
    logging.info('Total decrypt time ' + str(total_time))
    nodeid = os.environ.get('HBMPC_NODE_ID')
    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": nodeid})
    bench_logger.info('Total decrypt time ' + str(total_time))


def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    k = int(HbmpcConfig.extras["k"])
    try:
        (loop.run_until_complete(run_hbavss_light_multi(
            HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id, k)))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
