import random
import re
import struct
from hashlib import sha256

from pypairing import PyFq, PyFq12, PyFq2, PyFqRepr, PyFr, PyG1, PyG2

# Order of BLS group
bls12_381_r = 52435875175126190479447740508185965837690552500527637822603658699938581184513  # (# noqa: E501)


def pair(g1, g2):
    assert type(g1) is G1 and type(g2) is G2
    fq12 = PyFq12()
    g1.pyg1.py_pairing_with(g2.pyg2, fq12)
    return GT(fq12)


def dupe_pyg1(pyg1):
    out = PyG1()
    out.copy(pyg1)
    return out


def dupe_pyg2(pyg2):
    out = PyG2()
    out.copy(pyg2)
    return out


def dupe_pyfr(pyfr):
    out = PyFr(0, 0, 0, 0)
    out.copy(pyfr)
    return out


def dupe_pyfq12(pyfq12):
    out = PyFq12("1")
    out.copy(pyfq12)
    return out


class G1:
    def __init__(self, other=None):
        if other is None:
            self.pyg1 = PyG1()
        elif type(other) is list:
            assert len(other) == 2
            assert len(other[0]) == 6
            x = PyFqRepr(
                other[0][0],
                other[0][1],
                other[0][2],
                other[0][3],
                other[0][4],
                other[0][5],
            )
            y = PyFqRepr(
                other[1][0],
                other[1][1],
                other[1][2],
                other[1][3],
                other[1][4],
                other[1][5],
            )
            xq = PyFq()
            yq = PyFq()
            xq.from_repr(x)
            yq.from_repr(y)
            self.pyg1 = PyG1()
            self.pyg1.load_fq_affine(xq, yq)
        elif type(other) is PyG1:
            self.pyg1 = other
        else:
            raise TypeError(str(type(other)))

    def __str__(self):
        x = int(self.pyg1.__str__()[4:102], 0)
        y = int(self.pyg1.__str__()[108:206], 0)
        return "(" + str(x) + ", " + str(y) + ")"

    def __repr__(self):
        return str(self)

    def __mul__(self, other):
        if type(other) is G1:
            out = dupe_pyg1(self.pyg1)
            out.add_assign(other.pyg1)
            return G1(out)
        else:
            raise TypeError(
                "Invalid multiplication param. Expected G1. Got " + str(type(other))
            )

    def __imul__(self, other):
        if type(other) is G1:
            self.pyg1.add_assign(other.pyg1)
            return self
        raise TypeError(
            "Invalid multiplication param. Expected G1. Got " + str(type(other))
        )

    def __truediv__(self, other):
        if type(other) is G1:
            out = dupe_pyg1(self.pyg1)
            out.sub_assign(other.pyg1)
            return G1(out)
        else:
            raise TypeError(
                "Invalid division param. Expected G1. Got " + str(type(other))
            )

    def __idiv__(self, other):
        if type(other) is G1:
            self.pyg1.sub_assign(other.pyg1)
            return self
        raise TypeError("Invalid division param. Expected G1. Got " + str(type(other)))

    def __pow__(self, other):
        if type(other) is ZR:
            exponend = other
        else:
            try:
                intother = int(other)
                exponend = ZR(intother)
            except ValueError:
                raise TypeError(
                    "Invalid exponentiation param. Expected ZR or int. Got "
                    + str(type(other))
                )
        out = G1.one()
        self.pyg1.ppmul(exponend.val, out.pyg1)
        return out

    def __ipow__(self, other):
        if type(other) is int:
            self.pyg1.mul_assign(ZR(other).val)
            return self
        elif type(other) is ZR:
            self.pyg1.mul_assign(other.val)
            return self
        else:
            raise TypeError(
                "Invalid exponentiation param. Expected ZR or int. Got "
                + str(type(other))
            )

    def __rmul__(self, other):
        return self.__mul__(other)

    def __rtruediv__(self, other):
        return self.__truediv__(other)

    def __rpow__(self, other):
        return self.__pow__(other)

    def __eq__(self, other):
        if type(other) is not G1:
            return False
        return self.pyg1.equals(other.pyg1)

    def __getstate__(self):
        coords = self.pyg1.__str__()
        x = coords[6:102]
        y = coords[110:206]
        xlist = [x[80:96], x[64:80], x[48:64], x[32:48], x[16:32], x[0:16]]
        ylist = [y[80:96], y[64:80], y[48:64], y[32:48], y[16:32], y[0:16]]
        for i in range(6):
            xlist[i] = int(xlist[i], 16)
            ylist[i] = int(ylist[i], 16)
        return struct.pack("QQQQQQQQQQQQ", *(xlist + ylist))

    def __setstate__(self, d):
        xylist = struct.unpack("QQQQQQQQQQQQ", d)
        self.__init__([xylist[:6], xylist[6:]])

    def preprocess(self, level=4):
        assert type(level) is int
        self.pyg1.preprocess(level)

    def invert(self):
        negone = PyFr(str(1))
        negone.negate()
        self.pyg1.mul_assign(negone)

    def duplicate(self):
        return G1(dupe_pyg1(self.pyg1))

    def projective(self):
        return self.pyg1.projective()

    def pair_with(self, other):
        fq12 = PyFq12()
        self.pyg1.py_pairing_with(other.pyg2, fq12)
        return GT(fq12)

    @staticmethod
    def one():
        one = G1()
        one.pyg1.zero()
        return one

    @staticmethod
    def rand(seed=None):
        out = PyG1()
        if seed is None:
            seed = []
            for _ in range(8):
                seed.append(random.SystemRandom().randint(0, 4294967295))
            out.rand(seed)
        else:
            assert type(seed) is list
            assert len(seed) <= 8
            out.rand(seed)
        return G1(out)

    # length determines how many G1 values to return
    @staticmethod
    def hash(bytestr, length=1):
        assert type(bytestr) is bytes
        hashout = sha256(bytestr).hexdigest()
        seed = [int(hashout[i : i + 8], 16) for i in range(0, 64, 8)]
        if length == 1:
            return G1.rand(seed)
        out = [G1.rand(seed)]
        for j in range(0, length - 1):
            bytestr += b"x42"
            out.append(G1.hash(bytestr))
        return out


class G2:
    def __init__(self, other=None):
        if other is None:
            self.pyg2 = PyG2()
        if type(other) is list:
            assert len(other) == 4
            assert len(other[0]) == 6
            x1 = PyFqRepr(
                other[0][0],
                other[0][1],
                other[0][2],
                other[0][3],
                other[0][4],
                other[0][5],
            )
            x2 = PyFqRepr(
                other[1][0],
                other[1][1],
                other[1][2],
                other[1][3],
                other[1][4],
                other[1][5],
            )
            y1 = PyFqRepr(
                other[2][0],
                other[2][1],
                other[2][2],
                other[2][3],
                other[2][4],
                other[2][5],
            )
            y2 = PyFqRepr(
                other[3][0],
                other[3][1],
                other[3][2],
                other[3][3],
                other[3][4],
                other[3][5],
            )
            xq = PyFq2()
            yq = PyFq2()
            xq.from_repr(x1, x2)
            yq.from_repr(y1, y2)
            self.pyg2 = PyG2()
            self.pyg2.load_fq_affine(xq, yq)
        elif type(other) is PyG2:
            self.pyg2 = other

    def __str__(self):
        out = self.pyg2.__str__()
        x1 = int(out[8:106], 0)
        x2 = int(out[113:211], 0)
        y1 = int(out[226:324], 0)
        y2 = int(out[331:429], 0)
        return (
            "(" + str(x1) + " + " + str(x2) + "u, " + str(y1) + " + " + str(y2) + "u)"
        )

    def __repr__(self):
        return str(self)

    def __mul__(self, other):
        if type(other) is G2:
            out = dupe_pyg2(self.pyg2)
            out.add_assign(other.pyg2)
            return G2(out)

    def __imul__(self, other):
        if type(other) is G2:
            self.pyg2.add_assign(other.pyg2)
            return self

    def __truediv__(self, other):
        if type(other) is G2:
            out = dupe_pyg2(self.pyg2)
            out.sub_assign(other.pyg2)
            return G2(out)
        else:
            raise TypeError(
                "Invalid division param. Expected G2. Got " + str(type(other))
            )

    def __idiv__(self, other):
        if type(other) is G2:
            self.pyg2.sub_assign(other.pyg2)
            return self

    def __pow__(self, other):
        if type(other) is int:
            exponend = ZR(other)
        elif type(other) is ZR:
            exponend = other
        else:
            raise TypeError(
                "Invalid exponentiation param. Expected ZR or int. Got "
                + str(type(other))
            )
        out = G2(dupe_pyg2(self.pyg2))
        self.pyg2.ppmul(exponend.val, out.pyg2)
        return out

    def __ipow__(self, other):
        if type(other) is int:
            if other == 0:
                self.pyg2.zero()
                return self
            if other < 0:
                self.invert()
                other *= -1
            self.pyg2.mul_assign(ZR(other).val)
            return self
        elif type(other) is ZR:
            self.pyg2.mul_assign(other.val)
            return self
        else:
            raise TypeError(
                "Invalid exponentiation param. Expected ZR or int. Got "
                + str(type(other))
            )

    def __rmul__(self, other):
        return self.__mul__(other)

    def __rtruediv__(self, other):
        return self.__truediv__(other)

    def __rpow__(self, other):
        return self.__pow__(other)

    def __eq__(self, other):
        if type(other) is not G2:
            return False
        return self.pyg2.equals(other.pyg2)

    def __getstate__(self):
        coords = self.pyg2.__str__()
        x1 = coords[10:106]
        x2 = coords[115:211]
        y1 = coords[228:324]
        y2 = coords[333:429]
        x1list = [x1[80:96], x1[64:80], x1[48:64], x1[32:48], x1[16:32], x1[0:16]]
        x2list = [x2[80:96], x2[64:80], x2[48:64], x2[32:48], x2[16:32], x2[0:16]]
        y1list = [y1[80:96], y1[64:80], y1[48:64], y1[32:48], y1[16:32], y1[0:16]]
        y2list = [y2[80:96], y2[64:80], y2[48:64], y2[32:48], y2[16:32], y2[0:16]]
        for i in range(6):
            x1list[i] = int(x1list[i], 16)
            x2list[i] = int(x2list[i], 16)
            y1list[i] = int(y1list[i], 16)
            y2list[i] = int(y2list[i], 16)
        return [x1list, x2list, y1list, y2list]

    def __setstate__(self, d):
        self.__init__(d)

    def preprocess(self, level=4):
        assert type(level) is int
        self.pyg2.preprocess(level)

    def invert(self):
        negone = PyFr(str(1))
        negone.negate()
        self.pyg2.mul_assign(negone)

    def duplicate(self):
        return G2(dupe_pyg2(self.pyg2))

    def projective(self):
        return self.pyg2.projective()

    @staticmethod
    def one():
        one = G2()
        one.pyg2.zero()
        return one

    @staticmethod
    def rand(seed=None):
        out = PyG2()
        if seed is None:
            seed = []
            for _ in range(8):
                seed.append(random.SystemRandom().randint(0, 4294967295))
            out.rand(seed)
        else:
            assert type(seed) is list
            assert len(seed) <= 8
            out.rand(seed)
        return G2(out)

    # length determines how many G2 values to return
    @staticmethod
    def hash(bytestr, length=1):
        assert type(bytestr) is bytes
        hashout = sha256(bytestr).hexdigest()
        seed = [int(hashout[i : i + 8], 16) for i in range(0, 64, 8)]
        if length == 1:
            return G2.rand(seed)
        out = [G2.rand(seed)]
        for j in range(0, length - 1):
            bytestr += b"x42"
            out.append(G2.hash(bytestr))
        return out


class GT:
    def __init__(self, other=None):
        if other is None:
            self.pyfq12 = PyFq12()
            self.pyfq12.rand(1, 0, 0, 0)
        elif type(other) is PyFq12:
            self.pyfq12 = other
        elif type(other) is list:
            assert len(other) == 12
            self.pyfq12 = PyFq12()
            self.pyfq12.from_strs(*other)
        elif type(other) is int:
            self.pyfq12 = PyFq12()
            self.pyfq12.from_strs(str(other), *["0"] * 11)
        elif type(other) is str:
            lst = [x.strip() for x in other.split(",")]
            assert len(lst) == 12
            if lst[0][1] == "x":
                for i in range(len(lst)):
                    lst[i] = str(int(lst[i], 0))
            self.pyfq12 = PyFq12()
            self.pyfq12.from_strs(*lst)

    def __str__(self):
        out = self.pyfq12.__str__()
        return out

    def __repr__(self):
        return str(self)

    def oldpow(self, other):
        if type(other) is int:
            out = GT(dupe_pyfq12(self.pyfq12))
            out.pyfq12.pow_assign(ZR(other).val)
            return out
        elif type(other) is ZR:
            out = GT(dupe_pyfq12(self.pyfq12))
            out.pyfq12.pow_assign(other.val)
            return out
        else:
            raise TypeError(
                "Invalid exponentiation param. Expected ZR or int. Got "
                + str(type(other))
            )

    def __pow__(self, other):
        if type(other) is int:
            exponend = ZR(other)
        elif type(other) is ZR:
            exponend = other
        else:
            raise TypeError(
                "Invalid exponentiation param. Expected ZR or int. Got "
                + str(type(other))
            )
        outfq12 = PyFq12()
        self.pyfq12.pppow(exponend.val, outfq12)
        return GT(outfq12)

    def __mul__(self, other):
        if type(other) is GT:
            out = dupe_pyfq12(self.pyfq12)
            out.mul_assign(other.pyfq12)
            return GT(out)
        else:
            raise TypeError(
                "Invalid multiplication param. Expected GT. Got " + str(type(other))
            )

    def __truediv__(self, other):
        if type(other) is GT:
            out = dupe_pyfq12(self.pyfq12)
            divend = dupe_pyfq12(other.pyfq12)
            divend.inverse()
            out.mul_assign(divend)
            return GT(out)
        else:
            raise TypeError(
                "Invalid division param. Expected GT. Got " + str(type(other))
            )

    def __radd__(self, other):
        return self.__add__(other)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __rtruediv__(self, other):
        return self.__truediv__(other)

    def __rpow__(self, other):
        return self.__pow__(other)

    def __eq__(self, other):
        if type(other) is not GT:
            return False
        return self.pyfq12.equals(other.pyfq12)

    def __getstate__(self):
        s = self.pyfq12.__str__()
        s = s.replace("Fq6", "")
        s = s.replace("Fq2", "")
        s = s.replace("Fq", "")
        s = s.replace(" ", "")
        s = s.replace("*", "")
        s = s.replace("u", "")
        s = s.replace("v^2", "")
        s = s.replace("v", "")
        s = s.replace("w", "")
        s = s.replace("(", "")
        s = s.replace(")", "")
        s = s.replace("+", ",")
        return re.sub("0x0*", "0x0", s)

    def __setstate__(self, d):
        self.__init__(d)

    def preprocess(self, level=4):
        assert type(level) is int
        self.pyfq12.preprocess(level)

    @staticmethod
    # Generating a random fq12 in rust doesn't guarantee you get something in GT
    # Instead, exponentiate something that is with a random exponent
    def rand(seed=None):
        r = bls12_381_r
        if seed is None:
            r = random.SystemRandom().randint(0, r - 1)
        else:
            # Generate pseudorandomly based on seed
            r = random.Random(seed).randint(0, r - 1)
        exp = ZR(str(r))
        out = GT(
            "0x0158e1808f680056282c178bcba60c5acba8f0475a3c41a71d81f868772583714dc4b3eb5ca8c5d5061996e5c5ef24bcc,0x0b9df4a93419648e1d43121721548f16ed690a5f12c73ce16eba5969fe05995534cb764a7de2439edaa94924a939984d,0x0ad9d36bdee6b0d48b80a486461ec570e7f15393f721aa7631c5b685bb5b1e7b008f25437692e561083cac10c0a0aab0,0x0fb4a6fd9c72613c58e85dee45f293c9ac3df84243b775a80ca855e690f438b6361f82ed31c202709c16f75dd431e962,0x03b22c64e0522668d304ed847a33e02930cdb42f79ffab3aa2c54a7718283cf52fd7532d96e14f749c3e09ce4beabe49,0x01b597b86cbce4fc08a09487ec6d7141e3f4b6e02ec56fa57453b03ee0f2f535f3b2414d7b8366f45687a65475160ed0,0x0989f5f2a47ae4f5095ba9323b07330617f214f3972dc34be643e8ec361e3f04b260b845c46505429c6be9d441e721d1,0x01893a49f8840733e25c408a9fe57f15047da20a0fd498ea168b99977b99da42a32430a4934fd0acb7bc61b5abfb391a,0x0155d79b2f854e71ec012d26bdc0e05e0ffd4f002bfb4139b9e779f9e5fce72f0770f66d4cd475bfa4a6e769210a4e97a,0x016659bfd6c7b703935fd139f5c73653d1dd470435f05e73d2711bd5be4dd36c337a736f242f9c41d1674e18063f0548d,0x03cfeca937de62d23620a0de8d9e04b6318100480e8b10c30c16e33684629c34337ff25742986b90cfcf325fbae99564,0x0cb863283c7d744ddbb00c427295d45aaa3bd7be6181a5369b3bdbb89ffe3179dc58fd2aeca27bf19bf25b99af0cbd23"
        )  # (# noqa: E501)
        out **= exp
        return out


class ZR:
    def __init__(self, val=None):
        if val is None:
            self.val = PyFr(0, 0, 0, 0)
        elif type(val) is int:
            uint = val % (bls12_381_r)
            u1 = uint % 2 ** 64
            u2 = (uint // (2 ** 64)) % 2 ** 64
            u3 = (uint // (2 ** 128)) % 2 ** 64
            u4 = uint // (2 ** 192)
            self.val = PyFr(u1, u2, u3, u4)
        elif type(val) is str:
            if val[0:2] == "0x":
                intval = int(val, 0)
            else:
                intval = int(val)
            uint = intval % (bls12_381_r)
            u1 = uint % 2 ** 64
            u2 = (uint // (2 ** 64)) % 2 ** 64
            u3 = (uint // (2 ** 128)) % 2 ** 64
            u4 = uint // (2 ** 192)
            self.val = PyFr(u1, u2, u3, u4)
        elif type(val) is PyFr:
            self.val = val

    def __str__(self):
        hexstr = self.val.__str__()[3:-1]
        return str(int(hexstr, 0))

    def __repr__(self):
        return str(self)

    def __int__(self):
        hexstr = self.val.__str__()[3:-1]
        return int(hexstr, 0)

    def __add__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.add_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            zrother = ZR(other)
            out.add_assign(zrother.val)
            return ZR(out)
        else:
            raise TypeError(
                "Invalid addition param. Expected ZR or int. Got " + str(type(other))
            )

    def __radd__(self, other):
        assert type(other) is int
        return self.__add__(ZR(other))

    def __iadd__(self, other):
        if type(other) is ZR:
            self.val.add_assign(other.val)
            return self
        elif type(other) is int:
            zrother = ZR(other)
            self.val.add_assign(zrother.val)
            return self
        else:
            raise TypeError(
                "Invalid addition param. Expected ZR or int. Got " + str(type(other))
            )

    def __sub__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.sub_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            zrother = ZR(other)
            out.sub_assign(zrother.val)
            return ZR(out)
        else:
            raise TypeError(
                "Invalid addition param. Expected ZR or int. Got " + str(type(other))
            )

    def __rsub__(self, other):
        assert type(other) is int
        return ZR(other).__sub__(self)

    def __isub__(self, other):
        if type(other) is ZR:
            self.val.sub_assign(other.val)
            return self
        elif type(other) is int:
            zrother = ZR(other)
            self.val.sub_assign(zrother.val)
            return self
        else:
            raise TypeError(
                "Invalid addition param. Expected ZR or int. Got " + str(type(other))
            )

    def __mul__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.mul_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            zrother = ZR(other)
            out.mul_assign(zrother.val)
            return ZR(out)
        else:
            raise TypeError(
                "Invalid multiplication param. Expected ZR or int. Got "
                + str(type(other))
            )

    def __imul__(self, other):
        if type(other) is ZR:
            self.val.mul_assign(other.val)
            return self
        elif type(other) is int:
            zrother = ZR(other)
            self.val.mul_assign(zrother.val)
            return self
        else:
            raise TypeError(
                "Invalid multiplication param. Expected ZR or int. Got "
                + str(type(other))
            )

    def __rmul__(self, other):
        assert type(other) is int
        return self.__mul__(ZR(other))

    def __truediv__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            div = dupe_pyfr(other.val)
            div.inverse()
            out.mul_assign(div)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            zrother = ZR(other)
            zrother.val.inverse()
            out.mul_assign(zrother.val)
            return ZR(out)
        else:
            raise TypeError(
                "Invalid division param. Expected ZR or int. Got " + str(type(other))
            )

    def __rtruediv__(self, other):
        return ZR(other).__truediv__(self)

    def __pow__(self, other):
        if type(other) is int:
            exponend = ZR(other % (bls12_381_r - 1))
            out = dupe_pyfr(self.val)
            out.pow_assign(exponend.val)
            return ZR(out)
        elif type(other) is ZR:
            raise TypeError(
                "Invalid multiplication param. Expected int. Got ZR. This is not a bug"
            )
        else:
            raise TypeError(
                "Invalid multiplication param. Expected int. Got " + str(type(other))
            )

    def __neg__(self):
        out = dupe_pyfr(self.val)
        out.negate()
        return ZR(out)

    def __eq__(self, other):
        if type(other) is int:
            other = ZR(other)
        assert type(other) is ZR
        return self.val.equals(other.val)

    def __getstate__(self):
        return int(self)

    def __setstate__(self, d):
        self.__init__(d)

    @staticmethod
    def random(seed=None):
        r = bls12_381_r
        if seed is None:
            r = random.SystemRandom().randint(0, r - 1)
            return ZR(str(r))
        else:
            # Generate pseudorandomly based on seed
            r = random.Random(seed).randint(0, r - 1)
            return ZR(str(r))

    @staticmethod
    def zero():
        return ZR(0)

    @staticmethod
    def one():
        return ZR(1)

    @staticmethod
    def hash(bytestr):
        assert type(bytestr) is bytes
        return ZR("0x" + sha256(bytestr).hexdigest())


def lagrange_at_x(s, j, x):
    s = sorted(s)
    assert j in s
    l1 = [x - jj for jj in s if jj != j]
    l2 = [j - jj for jj in s if jj != j]
    (num, den) = (ZR(1), ZR(1))
    for item in l1:
        num *= item
    for item in l2:
        den *= item
    return num / den


def interpolate_g1_at_x(coords, x, order=-1):
    if order == -1:
        order = len(coords)
    xs = []
    sortedcoords = sorted(coords, key=lambda x: x[0])
    for coord in sortedcoords:
        xs.append(coord[0])
    s = set(xs[0:order])
    out = G1.one()
    for i in range(order):
        out = out * (sortedcoords[i][1] ** (lagrange_at_x(s, xs[i], x)))
    return out
