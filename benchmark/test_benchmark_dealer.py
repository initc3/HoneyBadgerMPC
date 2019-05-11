from pytest import mark
from contextlib import ExitStack
from random import randint
from honeybadgermpc.poly_commit_const import gen_pc_const_crs, PolyCommitConst
from honeybadgermpc.poly_commit_lin import PolyCommitLin
from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.hbavss import HbAvssLight, HbAvssBatch
from honeybadgermpc.symmetric_crypto import SymmetricCrypto
from honeybadgermpc.polynomial import polynomials_over
import asyncio
import cProfile


def get_avss_params(n, t):
    g, h = G1.rand(), G1.rand()
    public_keys, private_keys = [None]*n, [None]*n
    for i in range(n):
        private_keys[i] = ZR.random()
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys

@mark.parametrize("t", [1, 3, 5, 16, 33])
def test_benchmark_hbavss_dealer_crypto(benchmark, t):
    loop = asyncio.get_event_loop()
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n+1, t)
    crs = gen_pc_const_crs(t, g=g, h=h)
    pc = PolyCommitConst(crs)
    pc.preprocess_prover(8)
    params = (t, n, g, h, pks, sks, crs, pc)
    values = [ZR.random() for _ in range(100)]

    benchmark(get_dealer_msg, values, t, pc, g, pks)

def get_dealer_msg(values, t, pc, g, pks):
        # Sample a random degree-(t,t) bivariate polynomial φ(·,·)
        # such that each φ(0,k) = sk and φ(i,k) is Pi’s share of sk
        n = 3*t + 1
        poly = polynomials_over(ZR)
        while len(values) % (t + 1) != 0:
            values.append(0)
        secret_count = len(values)
        # batch_count = secret_count/(self.t + 1)
        phi = [None] * secret_count
        commitments = [None] * secret_count
        aux_poly = [None] * secret_count
        # for k ∈ [t+1]
        #   Ck, auxk <- PolyCommit(SP,φ(·,k))
        for k in range(secret_count):
            phi[k] = poly.random(t, values[k])
            commitments[k], aux_poly[k] = pc.commit(phi[k])

        ephemeral_secret_key = ZR.random()
        ephemeral_public_key = pow(g, ephemeral_secret_key)
        # for each party Pi and each k ∈ [t+1]
        #   1. w[i][k] <- CreateWitnesss(Ck,auxk,i)
        #   2. z[i][k] <- EncPKi(φ(i,k), w[i][k])
        dispersal_msg_list = [None] * n
        for i in range(n):
            shared_key = pow(pks[i], ephemeral_secret_key)
            z = [None] * secret_count
            for k in range(secret_count):
                witness = pc.create_witness(phi[k], aux_poly[k], i+1)
                z[k] = (int(phi[k](i+1)),
                        int(aux_poly[k](i+1)),
                        witness)
            zz = SymmetricCrypto.encrypt(str(shared_key).encode(), z)
            dispersal_msg_list[i] = zz

        return (commitments, ephemeral_public_key), dispersal_msg_list

        
def benchy(t):
    loop = asyncio.get_event_loop()
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n+1, t)
    crs = gen_pc_const_crs(t, g=g, h=h)
    pc = PolyCommitConst(crs)
    pc.preprocess_prover(8)
    params = (t, n, g, h, pks, sks, crs, pc)
    values = [ZR.random() for _ in range(100)]

    get_dealer_msg(values, t, pc, g, pks)

if __name__ == "__main__":
    #debug = True
    cProfile.run("benchy(16)")