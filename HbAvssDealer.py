from Crypto.Cipher import AES
import random
import hashlib
from PolyCommitNP import *
from helperfunctions import *
import os
import pickle
import asyncio
from reliablebroadcast import *

#Class representing a the dealer in the scheme. t is the threshold and k is the number of participants
class HbAvssDealer:
    #def __init__ (self, k, t, pk, secret, participantids, participantkeys, group, symflag, recv_function, send_function, sid=1, seed=None):
    def __init__ (self, publicparams, privateparams, send, recv):    
        # Random polynomial coefficients constructed in the form
        #[c       x        x^2        ...  x^t]
        # This is structured so that t+1 points are needed to reconstruct the polynomial
        time2 = os.times()
        ONE = ZR(1)
        (t, n, crs, participantids, participantkeys, sid) = publicparams
        (secret, pid) = privateparams
        (poly, polyhat, sharedkeys, shares, encryptedshares, witnesses, encryptedwitnesses) = ([], [], {}, {}, {}, {}, {})
        for i in range(t+1):
            poly.append(ZR.rand())
            polyhat.append(ZR.rand())
        sk = ZR.rand()
        for j in participantids:
            sharedkeys[j] = participantkeys[j] ** sk
        pc = PolyCommitNP(t=t, pk=crs)
        c = pc.commit(poly, polyhat)
        for j in participantids:
            shares[j] = f(poly, j)
            encryptedshares[j] = encrypt(sharedkeys[j], shares[j])
            witnesses[j] = f(polyhat, j)
            encryptedwitnesses[j] = encrypt(sharedkeys[j], witnesses[j])
        message = pickle.dumps((c, encryptedwitnesses, encryptedshares, crs[0] ** sk))
        print ("sent as...")
        print (message)
        print ("Dealer Time: " + str(os.times()[4] - time2[4]))
        loop = asyncio.get_event_loop()
        loop.create_task(reliablebroadcast(sid, pid=pid, N=n+1, f=t, leader=pid, input=str(message), receive=recv, send=send))


#wrapper for encryption that nicely converts crypto-things to something you can encrypt
def encrypt(key, plaintext):
    key_bytes = hashlib.sha256(pickle.dumps(key)).digest()
    encryptor = AES.new(key_bytes[:32], AES.MODE_CBC, 'This is an IV456')
    plaintext_bytes = pickle.dumps(plaintext)
    #seriously, why do I have to do the padding...
    while len(plaintext_bytes) %16 != 0:
        plaintext_bytes = plaintext_bytes + b'\x00'
    return encryptor.encrypt(plaintext_bytes)
    