from Crypto.Cipher import AES
from base64 import encodestring, decodestring
from asyncio import Queue
import random
import hashlib
import collections
import json
import ast
import asyncio
import pickle
from PolyCommitNP import *
from helperfunctions import *
from betterpairing import *
from reliablebroadcast import *


#Class representing a participant in the scheme. t is the threshold and k is the number of participants
class HbAvssRecipient:
    #def __init__ (self, k, t, pid, sk, pk, participantids, participantkeys, send, recv, write_function, sid=1, reconstruction=True):
    def __init__ (self, publicparams, privateparams, send, recv, reconstruction=True):
        
        (self.send, self.recv) = (send, recv)
        #self.write = write_function
        (self.t, self.n, crs, self.participantids, self.participantkeys, self.sid) = publicparams
        self.reconstruction = reconstruction
        (self.pid, self.sk) = privateparams
        self.dealerid = 0
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
            self.sharedkey = pk_d**self.sk
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
        share = decrypt(key, self.encshares[implicatorid])
        witness = decrypt(key, self.encwitnesses[implicatorid])
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