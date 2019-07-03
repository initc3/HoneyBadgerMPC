from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.polynomial import polynomials_over


class PolyCommitLin(object):
    def __init__(self, crs, field=ZR):
        assert len(crs) == 2
        self.g = crs[0]
        self.h = crs[1]
        self.field = field

    def commit(self, phi):
        degree = len(phi.coeffs) - 1
        phi_hat = polynomials_over(self.field).random(degree)
        cs = [
            pow(self.g, phi.coeffs[i]) * pow(self.h, phi_hat.coeffs[i])
            for i in range(degree + 1)
        ]
        return cs, phi_hat

    def create_witness(self, aux, i):
        return aux(i)

    def verify_eval(self, cs, i, phi_at_i, witness):
        lhs = G1.one()
        for j in range(len(cs)):
            lhs *= pow(cs[j], pow(i, j))
        rhs = pow(self.g, phi_at_i) * pow(self.h, witness)
        return lhs == rhs

    # TODO: Explore ways to do this faster
    def batch_verify_eval(self, commits, i, shares, witnesses):
        assert len(commits) == len(shares) and len(commits) == len(witnesses)
        for j in range(len(commits)):
            if not self.verify_eval(commits[j], i, shares[j], witnesses[j]):
                return False
        return True

    def preprocess(self, level=4):
        self.g.preprocess(level)
        self.h.preprocess(level)
