"""An implementation of (unique) threshold signatures based on
Gap-Diffie-Hellman Boldyreva, 2002 https://eprint.iacr.org/2002/118.pdf

Dependencies:
    Charm, http://jhuisi.github.io/charm/ a wrapper for PBC (Pairing
    based crypto)

"""
from charm.toolbox.pairinggroup import PairingGroup, ZR, G1, G2, pair
from base64 import encodebytes, decodebytes
from operator import mul
from functools import reduce

# group = PairingGroup('SS512')
# group = PairingGroup('MNT159')
group = PairingGroup("MNT224")


def serialize(g):
    """ """
    # Only work in G1 here
    return decodebytes(group.serialize(g)[2:])


def deserialize0(g):
    """ """
    # Only work in G1 here
    return group.deserialize(b"0:" + encodebytes(g))


def deserialize1(g):
    """ """
    # Only work in G1 here
    return group.deserialize(b"1:" + encodebytes(g))


def deserialize2(g):
    """ """
    # Only work in G1 here
    return group.deserialize(b"2:" + encodebytes(g))


g1 = group.hash("geng1", G1)
g1.initPP()
# g2 = g1
g2 = group.hash("geng2", G2)
g2.initPP()
ZERO = group.random(ZR, seed=59) * 0
ONE = group.random(ZR, seed=60) * 0 + 1


def polynom_eval(x, coefficients):
    """Polynomial evaluation."""
    y = ZERO
    xx = ONE
    for coeff in coefficients:
        y += coeff * xx
        xx *= x
    return y


class TBLSPublicKey(object):
    """ """

    def __init__(self, l, k, vk, vks):
        """ """
        self.l = l  # noqa: E741
        self.k = k
        self.VK = vk
        self.VKs = vks

    def __getstate__(self):
        """ """
        d = dict(self.__dict__)
        d["VK"] = serialize(self.VK)
        d["VKs"] = list(map(serialize, self.VKs))
        return d

    def __setstate__(self, d):
        """ """
        self.__dict__ = d
        self.VK = deserialize2(self.VK)
        self.VKs = list(map(deserialize2, self.VKs))

    def __eq__(self, other):
        return (
            self.l == other.l  # noqa: E741
            and self.k == other.k  # noqa: E741
            and self.VK == other.VK
            and self.VKs == other.VKs
        )

    def lagrange(self, s, j):
        """ """
        # Assert S is a subset of range(0,self.l)
        assert len(s) == self.k
        assert type(s) is set
        assert s.issubset(range(0, self.l))
        s = sorted(s)

        assert j in s
        assert 0 <= j < self.l
        num = reduce(mul, [0 - jj - 1 for jj in s if jj != j], ONE)
        den = reduce(mul, [j - jj for jj in s if jj != j], ONE)  # noqa: E272
        # assert num % den == 0
        return num / den

    def hash_message(self, m):
        """ """
        return group.hash(m, G1)

    def verify_share(self, sig, i, h):
        """ """
        assert 0 <= i < self.l
        b = self.VKs[i]
        assert pair(sig, g2) == pair(h, b)
        return True

    def verify_signature(self, sig, h):
        """ """
        assert pair(sig, g2) == pair(h, self.VK)
        return True

    def combine_shares(self, sigs):
        """ """
        # sigs: a mapping from idx -> sig
        s = set(sigs.keys())
        assert s.issubset(range(self.l))

        res = reduce(mul, [sig ** self.lagrange(s, j) for j, sig in sigs.items()], 1)
        return res


class TBLSPrivateKey(TBLSPublicKey):
    """ """

    def __init__(self, l, k, vk, vks, sk, i):
        """ """
        super(TBLSPrivateKey, self).__init__(l, k, vk, vks)
        assert 0 <= i < self.l
        self.i = i
        self.SK = sk

    def __eq__(self, other):
        return (
            super(TBLSPrivateKey, self).__eq__(other)
            and self.i == other.i
            and self.SK == other.SK
        )

    def sign(self, h):
        """ """
        return h ** self.SK

    def __getstate__(self):
        """ """
        d = dict(self.__dict__)
        d["VK"] = serialize(self.VK)
        d["VKs"] = list(map(serialize, self.VKs))
        d["i"] = self.i
        d["SK"] = serialize(self.SK)
        return d

    def __setstate__(self, d):
        """ """
        self.__dict__ = d
        self.VK = deserialize2(self.VK)
        self.VKs = list(map(deserialize2, self.VKs))
        self.SK = deserialize0(self.SK)


def dealer(players=10, k=5, seed=None):
    """ """
    # Random polynomial coefficients
    if seed is not None:
        a = [group.random(ZR, seed=seed + i) for i in range(k)]
    else:
        a = group.random(ZR, count=k)
    assert len(a) == k
    secret = a[0]

    # Shares of master secret key
    sks = [polynom_eval(i, a) for i in range(1, players + 1)]
    assert polynom_eval(0, a) == secret

    # Verification keys
    vk = g2 ** secret
    vks = [g2 ** xx for xx in sks]

    public_key = TBLSPublicKey(players, k, vk, vks)
    private_keys = [
        TBLSPrivateKey(players, k, vk, vks, sk, i) for i, sk in enumerate(sks)
    ]

    # Check reconstruction of 0
    s = set(range(0, k))
    lhs = polynom_eval(0, a)
    rhs = sum(public_key.lagrange(s, j) * polynom_eval(j + 1, a) for j in s)
    assert lhs == rhs
    # print i, 'ok'

    return public_key, private_keys


def generate_serialized_keys(n=4, f=1):
    import base64
    from pickle import dumps

    pbk, pvks = dealer(n, f + 1)
    print(base64.b64encode(dumps(pbk)))
    print()
    for pvk in pvks:
        print(base64.b64encode(dumps(pvk)))
        print()


if __name__ == "__main__":
    generate_serialized_keys()
