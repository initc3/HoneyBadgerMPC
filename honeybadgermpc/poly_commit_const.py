from honeybadgermpc.betterpairing import ZR, G1, G2, pair
from honeybadgermpc.polynomial import polynomials_over


class PolyCommitConst:
    def __init__(self, pk, field=ZR):
        assert len(pk) == 3
        (self.gs, self.ghats, self.hs) = pk
        assert len(self.gs) == len(self.hs)
        self.t = len(self.gs) - 1
        self.gg = self.gs[0].pair_with(self.ghats[0])
        self.gh = self.hs[0].pair_with(self.ghats[0])
        self.field = field

    def commit(self, phi):
        c = G1.one()
        phi_hat = polynomials_over(self.field).random(self.t)
        i = 0
        for item in self.gs:
            c *= item ** phi.coeffs[i]
            i += 1
        i = 0
        for item in self.hs:
            c *= item ** phi_hat.coeffs[i]
            i += 1
        # c should equal g **(phi(alpha)) h **(phi_hat(alpha))
        return c, phi_hat

    def create_witness(self, phi, phi_hat, i):
        poly = polynomials_over(self.field)
        div = poly([-1 * i, 1])
        psi = (phi - poly([phi(i)])) / div
        psi_hat = (phi_hat - poly([phi_hat(i)])) / div
        witness = G1.one()
        j = 0
        for item in self.gs[:-1]:
            witness *= item ** psi.coeffs[j]
            j += 1
        j = 0
        for item in self.hs[:-1]:
            witness *= item ** psi_hat.coeffs[j]
            j += 1
        return witness

    # If reusing the same commitment, the lhs of the comparison will be the same.
    # Take advantage of this to save pairings
    def verify_eval(self, c, i, phi_at_i, phi_hat_at_i, witness):
        lhs = c.pair_with(self.ghats[0])
        rhs = (
            witness.pair_with(self.ghats[1] / (self.ghats[0] ** i))
            * self.gg ** phi_at_i
            * self.gh ** phi_hat_at_i
        )
        return lhs == rhs

    def batch_verify_eval(self, commits, i, shares, auxes, witnesses):
        assert (
            len(commits) == len(shares)
            and len(commits) == len(witnesses)
            and len(commits) == len(auxes)
        )
        commitprod = G1.one()
        witnessprod = G1.one()
        sharesum = ZR(0)
        auxsum = ZR(0)
        for j in range(len(commits)):
            commitprod *= commits[j]
            witnessprod *= witnesses[j]
            sharesum += shares[j]
            auxsum += auxes[j]
        lhs = pair(commitprod, self.ghats[0])
        rhs = (
            pair(witnessprod, self.ghats[1] * self.ghats[0] ** (-i))
            * (self.gg ** sharesum)
            * (self.gh ** auxsum)
        )
        return lhs == rhs

    def preprocess_verifier(self, level=4):
        self.gg.preprocess(level)
        self.gh.preprocess(level)

    def preprocess_prover(self, level=4):
        for item in self.gs:
            item.preprocess(level)
        for item in self.hs:
            item.preprocess(level)


def gen_pc_const_crs(t, alpha=None, g=None, h=None, ghat=None):
    nonetype = type(None)
    assert type(t) is int
    assert type(alpha) in (ZR, int, nonetype)
    assert type(g) in (G1, nonetype)
    assert type(h) in (G1, nonetype)
    assert type(ghat) in (G2, nonetype)
    if alpha is None:
        alpha = ZR.random(0)
    if g is None:
        g = G1.rand([0, 0, 0, 1])
    if h is None:
        h = G1.rand([0, 0, 0, 1])
    if ghat is None:
        ghat = G2.rand([0, 0, 0, 1])
    (gs, ghats, hs) = ([], [], [])
    for i in range(t + 1):
        gs.append(g ** (alpha ** i))
    for i in range(2):
        ghats.append(ghat ** (alpha ** i))
    for i in range(t + 1):
        hs.append(h ** (alpha ** i))
    crs = [gs, ghats, hs]
    return crs
