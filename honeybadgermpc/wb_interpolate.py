"""
input: points in form (x,y)
output: coefficients of interpolated polynomial
"""

# hardcode the input


# an encoder and decoder for Reed-Solomon codes with coefficients in Z/p for a prime p
# decoder uses the Berlekamp-Welch algorithm

# for solving a linear system
from honeybadgermpc.linearsolver import someSolution

from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import polynomialsOver

# n is the total number of messages send out == total number of nodes
# k is the total number of code symbols, k = t + 1 with degree t polynomial
# maxE is the max errors the decoding function can handle


def makeEncoderDecoder(n, k, p):
    if not k <= n <= p:
        raise Exception(
            "Must have k <= n <= p but instead had (n,k,p) == (%r, %r, %r)" % (n, k, p))

    Fp = GF(p)
    Poly = polynomialsOver(Fp)
    # maximum allowed number of errors

    # message is a list of integers at most p
    def encode(message):
        if not all(x < p for x in message):
            raise Exception(
                "Message is improperly encoded as integers < p. It was:\n%r" % message)

        thePoly = Poly(message)
        return [[Fp(i), thePoly(Fp(i))] for i in range(n)]

    def solveSystem(encodedMessage, debug=False):
        maxE = ((n - k) // 2)
        print("MaxE is", maxE, "hahahha")
        if maxE > 0:
            for e in range(maxE, 0, -1):
                print("\ne is %r" % e)
                ENumVars = e + 1
                QNumVars = e + k

                def row(i, a, b):
                    # the "extended" part of the linear system
                    return ([
                        b * a**j for j in range(ENumVars)] +
                        [-1 * a**j for j in range(QNumVars)] + [0])

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
                print(remainder.coeffs)
                if remainder.isZero():
                    return Q, E
                raise Exception("found no divisors!")
        else:
            ENumVars = maxE + 1
            QNumVars = maxE + k

            def row(i, a, b):
                # the "extended" part of the linear system
                return ([
                    b * a**j for j in range(ENumVars)] +
                    [-1 * a**j for j in range(QNumVars)] + [0])

            system = (
                [row(i, a, b) for (i, (a, b)) in enumerate(encodedMessage)] +
                [[0] * (ENumVars - 1) + [1] + [0] * (QNumVars) + [1]]
            )  # ensure coefficient of x^e in E(x) is 1

            if debug:
                print("\nmaxE is %r" % maxE)
                print("\nsystem is:\n\n")
                for row in system:
                    print("\t%r" % (row,))

            solution = someSolution(system, freeVariableValue=1)
            E = Poly([solution[j] for j in range(maxE + 1)])
            Q = Poly([solution[j] for j in range(maxE + 1, len(solution))])

            if debug:
                print("\nreduced system is:\n\n")
                for row in system:
                    print("\t%r" % (row,))

                print("solution is %r" % (solution,))
                print("Q is %r" % (Q,))
                print("E is %r" % (E,))

            P, remainder = Q.__divmod__(E)
            print(remainder.coeffs)
            if remainder.isZero():
                return Q, E
            raise Exception("found no divisors!")

    def decode(encodedMessage, maxE, debug):
        Q, E = solveSystem(encodedMessage, maxE, debug)

        P, remainder = Q.__divmod__(E)
        if remainder != 0:
            raise Exception("Q is not divisibly by E!")

        return P.coefficients

    return encode, decode, solveSystem


"""
f: erasure
"""


def decoding_message_with_none_elements(f, encodedmsg, p):
    # number of non-none elements in the message
    nnone = 0
    encodedmsg_drop_none = []
    for i in encodedmsg:
        if i[0] is not None and i[1] is not None:
            nnone += 1
            encodedmsg_drop_none.append(i)
    assert(2*f + 1 <= nnone), "erasure too large, 2f + 1 > number of non-none elements!"

    _, _, solveSystem = makeEncoderDecoder(nnone, f+1, p)
    Q, E = solveSystem(encodedmsg_drop_none, True)
    P, remainder = (Q.__divmod__(E))
    print("P(x) = %r" % P)
    print("r(x) = %r" % remainder)

    num_matching = 0
    for i in range(len(encodedmsg)):
        if encodedmsg[i][1] == P(encodedmsg[i][0]):
            num_matching += 1
            if num_matching == (2*f + 1):
                break

    # assert(num_matching >= (2*f + 1)), "The decoded polynomial is not correct!"
    if num_matching < (2*f + 1):
        return False, None
    else:
        return True, P
