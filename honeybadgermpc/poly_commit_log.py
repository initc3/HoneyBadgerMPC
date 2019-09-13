from honeybadgermpc.betterpairing import ZR, G1
from honeybadgermpc.proofs import prove_inner_product_one_known, \
    verify_inner_product_one_known, prove_batch_inner_product_one_known, \
    verify_batch_inner_product_one_known, MerkleTree
import pickle


class PolyCommitLog:
    def __init__(self, crs=None, degree_max=33):
        if crs is None:
            n = degree_max + 1
            self.gs = G1.hash(b"honeybadgerg", length=n)
            self.h = G1.hash(b"honeybadgerh")
            self.u = G1.hash(b"honeybadgeru")
        else:
            assert len(crs) == 3
            [self.gs, self.hs, self.u] = crs
        self.y_vecs = []

    def commit(self, phi, r):
        c = G1.one()
        for i in range(len(phi.coeffs)):
            c *= self.gs[i] ** phi.coeffs[i]
        c *= self.h ** r
        return c

    def create_witness(self, phi, r, i):
        t = len(phi.coeffs) - 1
        y_vec = [ZR(i) ** j for j in range(t+1)]
        s_vec = [ZR.random() for _ in range(t+1)]
        sy_prod = ZR(0)
        S = G1.one()
        for j in range(t+1):
            S *= self.gs[j] ** s_vec[j]
            sy_prod += s_vec[j] * y_vec[j]
        T = self.gs[0] ** sy_prod
        rho = ZR.random()
        S *= self.h ** rho
        # Fiat Shamir
        challenge = ZR.hash(pickle.dumps([self.gs, self.h, self.u, S, T]))
        d_vec = [phi.coeffs[j] + s_vec[j] * challenge for j in range(t+1)]
        D = G1.one()
        for j in range(t+1):
            D *= self.gs[j] ** d_vec[j]
        mu = r + rho*challenge
        comm, t_hat, iproof = prove_inner_product_one_known(
                d_vec, y_vec, crs=[self.gs, self.u])
        return [S, T, D, mu, t_hat, iproof]

    # Create witnesses for points 1 to n. n defaults to 3*degree+1 if unset.
    def batch_create_witness(self, phi, r, n=None):
        t = len(phi.coeffs) - 1
        if n is None:
            n = 3*t + 1
        if len(self.y_vecs) < n:
            i = len(self.y_vecs)
            while(i < n):
                self.y_vecs.append([ZR(i+1) ** j for j in range(t+1)])
                i += 1
        s_vec = [ZR.random() for _ in range(t+1)]
        sy_prods = [ZR(0) for _ in range(n)]
        S = G1.one()
        T_vec = [None] * n
        witnesses = [[] for _ in range(n)]
        for i in range(t+1):
            S *= self.gs[i] ** s_vec[i]
        for j in range(n):
            for i in range(t+1):
                sy_prods[j] += s_vec[i] * self.y_vecs[j][i]
            T_vec[j] = self.gs[0] ** sy_prods[j]
        rho = ZR.random()
        S *= self.h ** rho
        # Fiat Shamir
        tree = MerkleTree()
        for j in range(n):
            tree.append(pickle.dumps(T_vec[j]))
        roothash = tree.get_root_hash()
        for j in range(n):
            branch = tree.get_branch(j)
            witnesses[j].append(roothash)
            witnesses[j].append(branch)
        challenge = ZR.hash(pickle.dumps([roothash, self.gs, self.h, self.u, S]))
        d_vec = [phi.coeffs[j] + s_vec[j] * challenge for j in range(t+1)]
        D = G1.one()
        for j in range(t+1):
            D *= self.gs[j] ** d_vec[j]
        mu = r + rho*challenge
        comm, t_hats, iproofs = prove_batch_inner_product_one_known(
                d_vec, self.y_vecs, crs=[self.gs, self.u])
        for j in range(len(witnesses)):
            witnesses[j] += [S, T_vec[j], D, mu, t_hats[j], iproofs[j]]
        return witnesses

    def verify_eval(self, c, i, phi_at_i, witness):
        t = witness[-1][0] - 1
        y_vec = [ZR(i) ** j for j in range(t+1)]
        if len(witness) == 6:
            [S, T, D, mu, t_hat, iproof] = witness
            challenge = ZR.hash(pickle.dumps([self.gs, self.h, self.u, S, T]))
        else:
            [roothash, branch, S, T, D, mu, t_hat, iproof] = witness
            print(branch)
            if not MerkleTree.verify_membership(pickle.dumps(T), branch, roothash):
                return False
            challenge = ZR.hash(pickle.dumps([roothash, self.gs, self.h, self.u, S]))
        ret = self.gs[0]**t_hat == self.gs[0]**phi_at_i * T ** challenge
        print(ret)
        ret &= D * self.h**mu == S**challenge * c
        print(ret)
        if len(iproof[-1]) > 3:
            ret &= verify_batch_inner_product_one_known(
                    D, t_hat, y_vec, iproof, crs=[self.gs, self.u])
        else:
            ret &= verify_inner_product_one_known(
                    D, t_hat, y_vec, iproof, crs=[self.gs, self.u])
        return ret

    def preprocess_prover(self, level=10):
        self.u.preprocess(level)
        for i in range(len(self.gs)-1):
            self.y_vecs.append([ZR(i+1) ** j for j in range(len(self.gs))])
