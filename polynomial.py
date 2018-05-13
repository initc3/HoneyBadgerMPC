import operator
import random
from functools import reduce

def strip_trailing_zeros(a):
    for i in range(len(a),0,-1):
        if a[i-1] != 0: break
    return a[:i]

def polynomialsOver(field):
    class Polynomial(object):
        def __init__(self, coeffs):
            self.coeffs = strip_trailing_zeros(coeffs)

        def isZero(self): return self.coeffs == []
        def __repr__(self):
            if self.isZero(): return '0'
            return ' + '.join(['%s x^%d' % (a, i) if i > 0 else '%s'%a
                               for i,a in enumerate(self.coeffs)])

        def __call__(self, x):
            y = 0
            xx = 1
            for coeff in self.coeffs:
                y += coeff * xx
                xx *= x
            return y

        @classmethod
        def interpolate_at(cls, shares, x_recomb=field(0)):
            # shares are in the form (x, y=f(x))
            if type(x_recomb) is int: x_recomb = field(x_recomb)
            assert type(x_recomb) is field
            xs, ys = zip(*shares)
            vector = []
            for i, x_i in enumerate(xs):
                factors = [(x_k - x_recomb) / (x_k - x_i)
                           for k, x_k in enumerate(xs) if k != i]
                vector.append(reduce(operator.mul, factors))
            return sum(map(operator.mul, ys, vector))

        @classmethod
        def random(cls, degree, y0=None):
            coeffs = [field(random.randint(0, field.modulus-1)) for _ in range(degree+1)]
            if y0 is not None: coeffs[0] = y0
            return cls(coeffs)

    return Polynomial
