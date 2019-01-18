from pypairing import PyFq, PyFq2, PyFqRepr, PyG1, PyG2, PyFr
import random

# Order of BLS group
bls12_381_r = 52435875175126190479447740508185965837690552500527637822603658699938581184513  # (# noqa: E501)


def dupe_pyg1(pyg1):
    out = PyG1()
    out.copy(pyg1)
    return out


def dupe_pyg2(pyg2):
    out = PyG2()
    out.copy(pyg2)
    return out


def dupe_pyfr(pyfr):
    out = PyFr("1")
    out.copy(pyfr)
    return out


class G1:
    def __init__(self, other=None):
        if other is None:
            self.pyg1 = PyG1()
        if type(other) is list:
            assert len(other) == 2
            assert len(other[0]) == 6
            x = PyFqRepr(other[0][0], other[0][1], other[0]
                         [2], other[0][3], other[0][4], other[0][5])
            y = PyFqRepr(other[1][0], other[1][1], other[1]
                         [2], other[1][3], other[1][4], other[1][5])
            xq = PyFq(0, 0, 0, 1)
            yq = PyFq(0, 0, 0, 1)
            xq.from_repr(x)
            yq.from_repr(y)
            self.pyg1 = PyG1()
            self.pyg1.load_fq_affine(xq, yq)
        elif type(other) is PyG1:
            self.pyg1 = other

    def __str__(self):
        x = int(self.pyg1.__str__()[4:102], 0)
        y = int(self.pyg1.__str__()[108:206], 0)
        return "(" + str(x) + ", " + str(y) + ")"

    def __mul__(self, other):
        if type(other) is G1:
            out = dupe_pyg1(self.pyg1)
            out.add_assign(other.pyg1)
            return G1(out)
        else:
            raise TypeError

    def __imul__(self, other):
        if type(other) is G1:
            self.pyg1.add_assign(other.pyg1)
            return self

    def __truediv__(self, other):
        if type(other) is G1:
            out = dupe_pyg1(self.pyg1)
            out.sub_assign(other.pyg1)
            return G1(out)
        else:
            raise TypeError

    def __idiv__(self, other):
        if type(other) is G1:
            self.pyg1.sub_assign(other.pyg1)
            return self

    def __pow__(self, other):
        if type(other) is int:
            out = G1(dupe_pyg1(self.pyg1))
            if other == 0:
                out.pyg1.zero()
                return out
            if other < 0:
                # out.invert()
                out.pyg1.negate()
                other = -1 * other
            prodend = ZR(other)
            out.pyg1.mul_assign(prodend.val)
            return out
        elif type(other) is ZR:
            out = G1(dupe_pyg1(self.pyg1))
            out.pyg1.mul_assign(other.val)
            return out
        else:
            raise TypeError(
                'Invalid exponentiation param. Expected ZR or int. Got '
                + str(type(other)))

    def __ipow__(self, other):
        if type(other) is int:
            if other == 0:
                self.pyg1.zero()
                return self
            if other < 0:
                self.invert()
                other = other * -1
            self.pyg1.mul_assign(ZR(other).val)
            return self
        elif type(other) is ZR:
            self.pyg1.mul_assign(other)
            return self
        else:
            raise TypeError(
                'Invalid exponentiation param. Expected ZR or int. Got '
                + str(type(other)))

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
        return [xlist, ylist]

    def __setstate__(self, d):
        self.__init__(d)

    def invert(self):
        negone = PyFr(str(1))
        negone.negate()
        self.pyg1.mul_assign(negone)

    def duplicate(self):
        return G1(dupe_pyg1(self.pyg1))

    def projective(self):
        return self.pyg1.projective()

    @staticmethod
    def one():
        out = PyG1()
        out.zero()
        return G1(out)

    @staticmethod
    def rand(seed=None):
        out = PyG1()
        if seed is None:
            seed = []
            for i in range(4):
                seed.append(random.SystemRandom().randint(0, 4294967295))
            out.rand(seed[0], seed[1], seed[2], seed[3])
        else:
            assert type(seed) is list
            assert len(seed) == 4
            out.rand(seed[0], seed[1], seed[2], seed[3])
        return G1(out)


class G2:
    def __init__(self, other=None):
        if other is None:
            self.pyg2 = PyG2()
        if type(other) is list:
            assert len(other) == 4
            assert len(other[0]) == 6
            x1 = PyFqRepr(other[0][0], other[0][1], other[0]
                          [2], other[0][3], other[0][4], other[0][5])
            x2 = PyFqRepr(other[1][0], other[1][1], other[1]
                          [2], other[1][3], other[1][4], other[1][5])
            y1 = PyFqRepr(other[2][0], other[2][1], other[2]
                          [2], other[2][3], other[2][4], other[2][5])
            y2 = PyFqRepr(other[3][0], other[3][1], other[3]
                          [2], other[3][3], other[3][4], other[3][5])
            xq = PyFq2(0, 0, 0, 1)
            yq = PyFq2(0, 0, 0, 1)
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
        return "(" + str(x1) + " + " + str(x2) + "u, " + str(y1) + " + " + str(y2) + "u)"

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
            raise TypeError

    def __idiv__(self, other):
        if type(other) is G2:
            self.pyg2.sub_assign(other.pyg2)
            return self

    def __pow__(self, other):
        if type(other) is int:
            out = G2(dupe_pyg2(self.pyg2))
            if other == 0:
                out.pyg2.zero()
                return out
            if other < 0:
                # out.invert()
                out.pyg2.negate()
                other = -1 * other
            prodend = ZR(other)
            out.pyg2.mul_assign(prodend.val)
            return out
        elif type(other) is ZR:
            out = G2(dupe_pyg2(self.pyg2))
            out.pyg2.mul_assign(other.val)
            return out
        else:
            raise TypeError(
                'Invalid exponentiation param. Expected ZR or int. Got '
                + str(type(other)))

    def __ipow__(self, other):
        if type(other) is int:
            if other == 0:
                self.pyg2.zero()
                return self
            if other < 0:
                self.invert()
                other = other * -1
            self.pyg2.mul_assign(ZR(other).val)
            return self
        elif type(other) is ZR:
            self.pyg2.mul_assign(other)
            return self
        else:
            raise TypeError(
                'Invalid exponentiation param. Expected ZR or int. Got '
                + str(type(other)))

    def __eq__(self, other):
        if type(other) is not G2:
            return False
        return self.pyg2.equals(other.pyg2)

    def __getstate__(self):
        coords = self.pyg2.__str__()
        x = coords[6:102]
        y = coords[110:206]
        xlist = [x[80:96], x[64:80], x[48:64], x[32:48], x[16:32], x[0:16]]
        ylist = [y[80:96], y[64:80], y[48:64], y[32:48], y[16:32], y[0:16]]
        for i in range(6):
            xlist[i] = int(xlist[i], 16)
            ylist[i] = int(ylist[i], 16)
        return [xlist, ylist]

    def __setstate__(self, d):
        self.__init__(d)

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
        out = PyG2()
        out.zero()
        return G2(out)

    @staticmethod
    def rand(seed=None):
        out = PyG2()
        if seed is None:
            seed = []
            for i in range(4):
                seed.append(random.SystemRandom().randint(0, 4294967295))
            out.rand(seed[0], seed[1], seed[2], seed[3])
        else:
            assert seed is list
            assert len(seed) == 4
            out.rand(seed[0], seed[1], seed[2], seed[3])
        return G2(out)


class ZR:
    def __init__(self, val=None):
        self.pp = []
        if val is None:
            self.val = PyFr(0x5dbe6259, 0x8d313d76, 0x3237db17, 0xe5bc0654)
        elif type(val) is int:
            if val < 0:
                val = val * -1
                self.val = PyFr(str(val))
                self.val.negate()
            else:
                self.val = PyFr(str(val))
        elif type(val) is str:
            if val[1] == 'x':
                self.val = PyFr(val)
            elif int(val) < 0:
                intval = int(val) * -1
                self.val = PyFr(str(intval))
                self.val.negate()
            else:
                self.val = PyFr(val)
        elif type(val) is PyFr:
            self.val = val

    def __str__(self):
        hexstr = self.val.__str__()[3:-1]
        return str(int(hexstr, 0))

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
            if other < 0:
                other *= -1
                addend = PyFr(str(other))
                addend.negate()
            else:
                addend = PyFr(str(other))
            out.add_assign(addend)
            return ZR(out)
        else:
            raise TypeError(
                'Invalid addition param. Expected ZR or int. Got '
                + str(type(other)))

    def __iadd__(self, other):
        if type(other) is ZR:
            self.val.add_assign(other.val)
            return self
        elif type(other) is int:
            if other < 0:
                other *= 1
                addend = PyFr(str(other))
                addend.negate()
            else:
                addend = PyFr(str(other))
            self.val.add_assign(addend)
            self.pp = []
            return self
        else:
            raise TypeError(
                'Invalid addition param. Expected ZR or int. Got '
                + str(type(other)))

    def __sub__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.sub_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            if other < 0:
                other *= -1
                subend = PyFr(str(other))
                subend.negate()
            else:
                subend = PyFr(str(other))
            out.sub_assign(subend)
            return ZR(out)
        else:
            raise TypeError(
                'Invalid addition param. Expected ZR or int. Got '
                + str(type(other)))

    def __isub__(self, other):
        if type(other) is ZR:
            self.val.sub_assign(other.val)
            return self
        elif type(other) is int:
            if other < 0:
                other *= 1
                subend = PyFr(str(other))
                subend.negate()
            else:
                subend = PyFr(str(other))
            self.val.sub_assign(subend)
            self.pp = []
            return self
        else:
            raise TypeError(
                'Invalid addition param. Expected ZR or int. Got '
                + str(type(other)))

    def __mul__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.mul_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            if other < 0:
                other *= -1
                prodend = PyFr(str(other))
                prodend.negate()
            else:
                prodend = PyFr(str(other))
            out.mul_assign(prodend)
            return ZR(out)
        else:
            raise TypeError(
                'Invalid multiplication param. Expected ZR or int. Got '
                + str(type(other)))

    def __imul__(self, other):
        if type(other) is ZR:
            self.val.mul_assign(other.val)
            return self
        elif type(other) is int:
            if other < 0:
                other *= -1
                prodend = PyFr(str(other))
                prodend.negate()
            else:
                prodend = PyFr(str(other))
            self.val.mul_assign(prodend)
            self.pp = []
            return self
        else:
            raise TypeError(
                'Invalid multiplication param. Expected ZR or int. Got '
                + str(type(other)))

    def __truediv__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            div = dupe_pyfr(other.val)
            div.inverse()
            out.mul_assign(div)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            if other < 0:
                other *= -1
                prodend = PyFr(str(other))
                prodend.negate()
            else:
                prodend = PyFr(str(other))
            prodend.inverse()
            out.mul_assign(prodend)
            return ZR(out)
        else:
            raise TypeError(
                'Invalid division param. Expected ZR or int. Got '
                + str(type(other)))

    def __pow__(self, other):
        if type(other) is int:
            if other == 0:
                return ZR(1)
            other = other % (bls12_381_r-1)
            out = dupe_pyfr(self.val)
            if self.pp == []:
                self.init_pp()
            i = 0
            # Hacky solution to my off by one error
            other -= 1
            while other > 0:
                if other % 2 == 1:
                    out.mul_assign(self.pp[i])
                i += 1
                other = other >> 1
            return ZR(out)
        elif type(other) is ZR:
            out = dupe_pyfr(self.val)
            if self.pp == []:
                self.init_pp()
            i = 0
            # Hacky solution to my off by one error
            other = int(other)
            other -= 1
            while other > 0:
                if other % 2 == 1:
                    out.mul_assign(self.pp[i])
                i += 1
                other = other >> 1
            return ZR(out)
        else:
            raise TypeError(
                'Invalid multiplication param. Expected int or ZR. Got '
                + str(type(other)))

    def __eq__(self, other):
        if type(other) is not ZR:
            return False
        return self.pyg1.equals(other.val)

    def __getstate__(self):
        return int(self)

    def __setstate__(self, d):
        self.__init__(d)

    def init_pp(self):
        self.pp.append(dupe_pyfr(self.val))
        for i in range(1, 255):
            power = dupe_pyfr(self.pp[i-1])
            power.square()
            self.pp.append(power)

    @staticmethod
    def rand(seed=None):
        r = bls12_381_r
        if seed is None:
            r = random.SystemRandom().randint(0, r-1)
            return ZR(str(r))
        else:
            # Generate pseudorandomly based on seed
            r = random.Random(seed).randint(0, r-1)
            return ZR(str(r))

    @staticmethod
    def zero():
        out = PyFr("0")
        return ZR(out)

    @staticmethod
    def one():
        out = PyFr("1")
        return ZR(out)
