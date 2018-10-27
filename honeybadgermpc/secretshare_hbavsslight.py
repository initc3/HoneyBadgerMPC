from Crypto.Cipher import AES
import random
import hashlib
import os
import pickle
import asyncio
import random
import hashlib
import collections
import json
import ast

# secretshare uses reliable broadcast as a sub protocol
from honeybadgermpc.reliablebroadcast import *

# This is necessary to specialize the library to BLS12-381
# TODO: the `betterpairing` interface is a work in progress.
# For now we rely on the `pypairing` interface anyway.
# When `pypairing` is improved we'll use that.
from honeybadgermpc.betterpairing import *

from Crypto.Cipher import AES
from base64 import encodestring, decodestring
from asyncio import Queue



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
    #myzero will be appropriate whether we are in ZR or G
    #myzero = poly1[0] - poly1[0]
    product = [None] * len(poly1)
    for i in range(len(product)):
        product[i] = poly1[i] * c
    return product

def polynomial_multiply(poly1, poly2):
    myzero = ZR(0)
    product = [myzero] * (len(poly1) + len(poly2) -1)
    for i in range(len(poly1)):
        temp = polynomial_multiply_constant(poly2, poly1[i])
        while i > 0:
            temp.insert(0,myzero)
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
    
def interpolate_at_x(coords, x, order=-1):
    ONE = ZR(1)
    if order == -1:
        order = len(coords)
    xs = []
    sortedcoords = sorted(coords, key=lambda x: x[0])
    for coord in sortedcoords:
        xs.append(coord[0])
    S = set(xs[0:order])
    #The following line makes it so this code works for both members of G and ZR
    out = coords[0][1] - coords[0][1]
    for i in range(order):
        out = out + (lagrange_at_x(S,xs[i],x) * sortedcoords[i][1])
    return out

def lagrange_at_x(S,j,x):
    ONE = ZR(1)
    S = sorted(S)
    assert j in S
    l1 = [x - jj  for jj in S if jj != j]
    l2 = [j - jj  for jj in S if jj != j]
    (num,den) = (ZR(1), ZR(1))
    for item in l1:
        num *= item
    for item in l2:
        den *= item
    return num / den

def interpolate_poly(coords):
    myone = ZR(1)
    myzero = ZR(0)
    #print "Before: " + str(coords[0][1]) + " After: " + str(myzero + coords[0][1])
    poly = [myzero] * len(coords)
    for i in range(len(coords)):
        temp = [myone]
        for j in range(len(coords)):
            if i == j:
                continue
            temp = polynomial_multiply(temp, [ -1 * (coords[j][0] * myone), myone])
            temp = polynomial_divide(temp, [myone * coords[i][0] - myone * coords[j][0]])
        poly = polynomial_add(poly, polynomial_multiply_constant(temp,coords[i][1]))
    return poly


#####################################
# Symmetric encryption
#####################################

## Symmetric cryptography.
## Uses AES with a 32-byte key
## Semantic security (iv is randomized)

## Copied from honeybadgerbft 

BS = 16
pad = lambda s: s + (BS - len(s) % BS) * bytes([BS - len(s) % BS])
unpad = lambda s : s[:-ord(s[len(s)-1:])]


def encrypt( key, raw ):
    """ """
    from Crypto import Random
    key = hashlib.sha256(key).digest() # hash the key
    assert len(key) == 32
    raw = pad(pickle.dumps(raw))
    iv = Random.new().read( AES.block_size )
    cipher = AES.new( key, AES.MODE_CBC, iv )
    return ( iv + cipher.encrypt( raw ) )


def decrypt( key, enc ):
    """ """
    key = hashlib.sha256(key).digest() # hash the key
    assert len(key) == 32
    enc = (enc)
    iv = enc[:16]
    cipher = AES.new( key, AES.MODE_CBC, iv )
    return pickle.loads(unpad(cipher.decrypt( enc[16:] )))


########################
# Polynomial commitments
########################

class PolyCommitNP:
    def __init__ (self, t, pk):
        """
        """
        self.g = pk[0].duplicate()
        self.h = pk[1].duplicate()
        self.t = t

    def commit (self, poly, secretpoly):
        #initPP?
        cs = []
        for i in range(self.t+1):
            c = (self.g**poly[i])*(self.h**secretpoly[i])
            cs.append(c)
        return cs

    def verify_eval(self, c, i, polyeval, secretpolyeval, witness=None):
        lhs = G1.one()
        for j in range(len(c)):
            lhs = lhs * c[j]**(i**j)
        rhs = (self.g**polyeval)*(self.h**secretpolyeval)
        return  lhs == rhs



##########################################
# Dealer part of the hbavss-light protocol
##########################################

#Class representing a the dealer in the scheme. t is the threshold and k is the number of participants
class HbAvssDealer:
    #def __init__ (self, k, t, pk, secret, participantids, participantkeys, group, symflag, recv_function, send_function, sid=1, seed=None):
    def __init__ (self, publicparams, privateparams, send, recv):    
        # Random polynomial coefficients constructed in the form
        #[c       x        x^2        ...  x^t]
        # This is structured so that t+1 points are needed to reconstruct the polynomial
        time2 = os.times()
        ONE = ZR(1)
        (t, n, crs, participantids, participantkeys, dealerid, sid) = publicparams
        (secret, pid) = privateparams
        assert dealerid == pid, "HbAvssDealer called, but wrong pid"
        (poly, polyhat, sharedkeys, shares, encryptedshares, witnesses, encryptedwitnesses) = ([], [], {}, {}, {}, {}, {})
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
            shares[j] = f(poly, j)
            encryptedshares[j] = encrypt(str(sharedkeys[j]).encode('utf-8'), shares[j])
            witnesses[j] = f(polyhat, j)
            encryptedwitnesses[j] = encrypt(str(sharedkeys[j]).encode('utf-8'), witnesses[j])
        message = pickle.dumps((c, encryptedwitnesses, encryptedshares, crs[0] ** sk))
        print ("Dealer Time: " + str(os.times()[4] - time2[4]))
        self._task = reliablebroadcast(sid, pid=pid, N=n+1, f=t, leader=pid, input=message, receive=recv, send=send)

    async def run(self):
        return await self._task



#################################################
# The recipient part of the hbavss-light protocol
#################################################

#Class representing a participant in the scheme. t is the threshold and k is the number of participants
class HbAvssRecipient:
    #def __init__ (self, k, t, pid, sk, pk, participantids, participantkeys, send, recv, write_function, sid=1, reconstruction=True):
    def __init__ (self, publicparams, privateparams, send, recv, reconstruction=True):
        
        (self.send, self.recv) = (send, recv)
        #self.write = write_function
        (self.t, self.n, crs, self.participantids, self.participantkeys, self.dealerid, self.sid) = publicparams
        self.reconstruction = reconstruction
        (self.pid, self.sk) = privateparams
        assert self.pid != self.dealerid, "HbAvssRecipient, but pid is dealerid"
        (self.sharedkey, self.rbfinished, self.finished, self.sendrecs, self.sharevalid) = (None, False, False, False, False)
        (self.okcount, self.implicatecount, self.output, self.secret) = (0, 0, None, None)
        self.pc = PolyCommitNP(t=self.t, pk=crs)
        (self.shares, self.queues, self.recvs) = ({}, {}, {})
        msgtypes = ["rb", "hbavss"]
        for msgtype in msgtypes:
            self.queues[msgtype] = Queue()
            self.recvs[msgtype] = self.makeRecv(msgtype)
        loop = asyncio.get_event_loop()
        loop.create_task(rbc_and_send(self.sid, self.pid, self.n+1, self.t, self.dealerid, None, self.recvs["rb"], send))
        #rb_thread = Greenlet(rbc_and_send, sid, pid, k+1, t, k, None, self.recvs["rb"], send)
        #rb_thread.start()
        #send(pid, ["send", reliablebroadcast(sid, pid, k+1, f=t, leader=k, input=None, receive=self.recvs["rb"], send=send)])
        #loop.create_task(self.run())
    async def run(self):    
        while not self.finished:
            sender, msg = await self.recv()
            self.receive_msg(sender,msg)
        
    def receive_msg(self, sender, msg):
        #print(msg)
        if msg[0] in ["READY", "ECHO", "VAL"]:
            self.queues["rb"].put_nowait((sender, msg))
            if msg[1] == "VAL":
                print (str(self.pid) + ": " + str(msg[3]) + "\n")
        if msg[1] == "send":
            self.rbfinished = True
            #print(msg)
            
            message = pickle.loads(msg[2])
            (self.commit, self.encwitnesses, self.encshares, pk_d) = message
            self.sharedkey = str(pk_d**self.sk).encode('utf-8')
            self.share = decrypt(self.sharedkey, self.encshares[self.pid])
            self.witness = decrypt(self.sharedkey, self.encwitnesses[self.pid])
            if self.pc.verify_eval(self.commit, self.pid, self.share, self.witness):
                self.send_ok_msgs()
                self.sendrecs = True
            else:
                print("verifyeval failed")
                self.send_implicate_msgs()
            while not self.queues["hbavss"].empty():
                (i,o) = self.queues["hbavss"].get_nowait()
                self.receive_msg(i,o)
        if not self.rbfinished:
            self.queues["hbavss"].put_nowait((sender,msg))
        elif msg[1] == "ok":
            #TODO: Enforce one OK message per participant
            #print str(self.pid) + " got an ok from " + str(sender)
            self.okcount += 1
            del self.encshares[sender]
            del self.encwitnesses[sender]
            if not self.sharevalid and self.okcount >= 2*self.t + 1:
                self.sharevalid = True
                self.output = self.share
                #print "WTF!"
                #print "./shares/"+str(self.pid)+"/"+str(self.sid)
                #f_raw = open( "./shares/"+str(self.pid)+"/"+str(self.sid), "w+" )
                #f = open( "./deletme", "a+" )
                #f = FileObjectThread(f_raw, 'a+')
                #f = open('shares/'+str(self.pid)+"/"+str(self.sid), 'w+')
                
                #self.write(str(self.share))
                
                #f.close()
                #except Exception as e:
                #    print type(e)
                #    print str(e)
                #print self.share
                if self.reconstruction and self.sendrecs:
                    self.send_rec_msgs()
                    self.sendrecs = False
            #TODO: Fix this part so it's fault tolerant
            if self.okcount == self.n and not self.reconstruction:
                self.finished = True
        elif msg[1] == 'implicate':
            if self.check_implication(int(sender), msg[2], msg[3]):
                self.implicatecount += 1
                if self.implicatecount == 2*self.t+1:
                    print ("Output: None")
                    self.share = None
                    self.finished = True
                if self.sendrecs:
                    self.reconstruction = True
                    self.send_rec_msgs()
                    self.sentdrecs = False
            else:
                #print "Bad implicate!"
                self.okcount += 1 
                del self.encshares[sender]
                del self.encwitnesses[sender]
        elif msg[1] == 'rec':
            if self.pc.verify_eval(self.commit, sender, msg[2], msg[3]):
                self.shares[sender] = msg[2]
            if len(self.shares) == self.t + 1:
                coords = []
                for key, value in self.shares.items():
                    coords.append([key, value])
                self.secret = interpolate_at_x(coords, 0)
                print (self.secret)
                self.finished = True

    #checks if an implicate message is valid
    def check_implication(self, implicatorid, key, proof):
        #First check if they key that was sent is valid
        if not check_same_exponent_proof(proof, self.pk[0],self.participantkeys[self.dealerid], self.participantkeys[implicatorid], key):
            #print "Bad Key!"
            return False
        share = decrypt(str(key), self.encshares[implicatorid])
        witness = decrypt(str(key), self.encwitnesses[implicatorid])
        return not self.pc.verify_eval(self.commit, implicatorid, share, witness)
        
    def send_ok_msgs(self):
        msg = []
        msg.append(self.sid)
        msg.append("ok")
        for j in self.participantids:
            self.send(j, msg)

    def send_implicate_msgs(self):
        msg = []
        msg.append(self.sid)
        msg.append("implicate")
        msg.append(self.sharedkey)
        msg.append(prove_same_exponent(self.pk[0], self.participantkeys[self.dealerid],self.sk))
        for j in self.participantids:
            self.send(j, msg)

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
            (i,o) = await self.queues[msgtype].get()
            return (i,o)
        return _recv

async def rbc_and_send(sid, pid, n, t, k, ignoreme, receive, send):
    msg = await reliablebroadcast(sid, pid, n, f=t, leader=k, input=None, receive=receive, send=send)
    send(pid, [sid, "send", msg])


################
# Driver script
################

# Run as either node or dealer, depending on command line arguments
# Uses the same configuration format as hbmpc

async def runHBAVSSLight(config, N, t, id):
    send, recv, sender, listener = setup_sockets(config, N+1, id)
    # Need to give time to the listener coroutine to start
    #  or else the sender will get a connection refused.

    # XXX HACK! Increase wait time. Must find better way if possible -- e.g:
    # try/except retry logic ...
    await asyncio.sleep(2)
    await sender.connect()
    await asyncio.sleep(1)

    # Generate the CRS deterministically
    crs = [G1.rand(seed=[0,0,0,1]), G1.rand(seed=[0,0,0,2])]

    # Load private parameters / secret keys
    (participantpubkeys, participantprivkeys) = ({}, {})
    participantids = list(range(N))
    for i in participantids:
        # These can also be determined pseudorandomly
        sk = ZR.rand(seed=17+i)
        participantprivkeys[i] = sk
        participantpubkeys[i] = crs[0] ** sk
    # Load public parameters
    pubparams = (t, N, crs, participantids, participantpubkeys, 'sid')

    # Launch the protocol
    if id == N:
        # The N+1'th party is the dealer
        thread = HbAvssDealer(pubparams, (42, id), send, recv)
    else:
        # Parties 0 through N-1 are recipients
        myPrivateKey = participantprivkeys[i]
        thread = HbAvssRecipient(pubparams, (id, myPrivateKey), send, recv)

    # Wait for results and clean up
    results = await thread.run()
    await asyncio.sleep(1)
    await sender.close()
    await listener.close()
    await asyncio.sleep(1)
    return results


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

if __name__ == "__main__":
    import sys
    from .exceptions import ConfigurationError
    from .config import load_config
    from .ipc import setup_sockets, NodeDetails

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
    nodeid = int(nodeid)
    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }
    print('network_info:', network_info)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(runHBAVSSLight(network_info, N, t, nodeid))
    finally:
        loop.close()
