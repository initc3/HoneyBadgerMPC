# an encoder and decoder for Reed-Solomon codes with coefficients in Z/p for a prime p
# decoder uses the Berlekamp-Welch algorithm
#
# Code mostly due to Jeremy Kun
#   https://jeremykun.com/2015/09/07/welch-berlekamp/
#
# Encoding:
#  k=t+1 is the number of code symbols in the original message.
#  We encode these as n evaluations of a degree-t polynomial, where the
#  original t+1 symbols are treated as coefficients of the polynomial.
#  n is the total number of messages sent out == total number of nodes
#
#  Input:
#   k=3, n=4,  message=[k0, k1, k2]
#
#    the degree-t=2 polynomial is  f = k2 x^2 + k1 x + k0
#
#  Output: [ m0=f(w^0),
#            m1=f(w^1),
#            m2=f(w^2),
#            m3=f(w^3) ]
#
# Decoding:
#  Given t+1 correct points, we could correctly decode the degree-t poylomial
#  using ordinary interpolation. Using the B-W algorithm, given t+1+e correct
#  correct points we can identify and remove up to e errors.
#
#  The inputs are passed as list of n points, where at most t+1 points are non-none.
#  None values are treated as erasures.
#  Example:
#  [m0, m1, None, m3]
#
#  Since we have at most n message symbols, the most errors we hope to tolerate
#  is when n=t+1+2e, so e <= maxE = (n-1-t)//2.
#
#  We can also correct a mixture of c erasures and e errors, as long as
#  n=t+1+c+2e.
#

# for solving a linear system
from honeybadgermpc.linearsolver import someSolution

from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import polynomialsOver


def makeEncoderDecoder(n, k, p, omega=None):
    """
    n: number of symbols to encode
    k: number of symbols in the message
        (k=t+1) where t is the degree of the polynomial
    """
    if not k <= n <= p:
        raise Exception(
            "Must have k <= n <= p but instead had (n,k,p) == (%r, %r, %r)" % (n, k, p))
    t = k - 1  # degree of polynomial
    Fp = GF.get(p)
    Poly = polynomialsOver(Fp)

    # the message points correspond to polynomial evaluations
    # at either f(i) for convenience, or
    #    f( omega^i ) where omega. If omega is an n'th root of unity,
    # then we can do efficient FFT-based polynomial interpolations.
    if omega is None:
        def point(i): return Fp(1+i)
    else:
        def point(i): return Fp(omega)**i

    # message is a list of integers at most p
    def encode(message):
        if not all(x < p for x in message):
            raise Exception(
                "Message is improperly encoded as integers < p. It was:\n%r" % message)
        assert len(message) == t + 1

        thePoly = Poly(message)
        return [thePoly(point(i)) for i in range(n)]

    def solveSystem(encodedMessage, maxE, debug=False):
        """
        input: points in form (x,y)
        output: coefficients of interpolated polynomial

        due to Jeremy Kun
        https://jeremykun.com/2015/09/07/welch-berlekamp/
        """
        for e in range(maxE, 0, -1):
            ENumVars = e + 1
            QNumVars = e + k

            def row(i, a, b):
                return (
                    [b * a**j for j in range(ENumVars)] +
                    [-1 * a**j for j in range(QNumVars)] + [0]
                )  # the "extended" part of the linear system

            system = (
                [row(i, a, b) for (i, (a, b)) in enumerate(encodedMessage)] +
                [[0] * (ENumVars - 1) + [1] + [0] * (QNumVars) + [1]]
            )  # ensure coefficient of x^e in E(x) is 1

            if debug:
                print("\ne is %r" % e)
                print("\nsystem is:\n\n")
                for row in system:
                    print("\t%r" % (row,))

            solution = someSolution(system, freeVariableValue=1)
            E = Poly([solution[j] for j in range(e + 1)])
            Q = Poly([solution[j] for j in range(e + 1, len(solution))])

            if debug:
                print("\nreduced system is:\n\n")
                for row in system:
                    print("\t%r" % (row,))

                print("solution is %r" % (solution,))
                print("Q is %r" % (Q,))
                print("E is %r" % (E,))

            P, remainder = Q.__divmod__(E)
            if debug:
                print("P(x) = %r" % P)
                print("r(x) = %r" % remainder)
            if remainder.isZero():
                return Q, E
        raise ValueError("found no divisors!")

    def decode(encodedMessage, debug=False):
        assert(len(encodedMessage) == n)
        c = sum(m is None for m in encodedMessage)  # number of erasures
        assert(t + 1 + c <= n)
        e = (n - c - t - 1) // 2  # number of errors to correct

        if debug:
            print('n:', n, 'k:', k, 't:', t)
            print('decoding with e:', e)
            print('decoding with c:', c)

        encM = [(point(i), m)
                for i, m in enumerate(encodedMessage) if m is not None]

        if e == 0:
            # decode with no errors
            P = Poly.interpolate(encM)
            return P.coeffs

        Q, E = solveSystem(encM, maxE=e, debug=debug)
        P, remainder = Q.__divmod__(E)
        if not remainder.isZero():
            raise Exception("Q is not divisibly by E!")
        return P.coeffs

    return encode, decode, solveSystem
