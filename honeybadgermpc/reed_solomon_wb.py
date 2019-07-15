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
import logging
from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import polynomials_over, EvalPoint


def make_wb_encoder_decoder(n, k, p, point=None):
    """
    n: number of symbols to encode
    k: number of symbols in the message
        (k=t+1) where t is the degree of the polynomial
    """
    if not k <= n <= p:
        raise Exception(
            "Must have k <= n <= p but instead had (n,k,p) == (%r, %r, %r)" % (n, k, p)
        )
    t = k - 1  # degree of polynomial
    fp = GF(p)
    poly = polynomials_over(fp)

    # the message points correspond to polynomial evaluations
    # at either f(i) for convenience, or
    #    f( omega^i ) where omega. If omega is an n'th root of unity,
    # then we can do efficient FFT-based polynomial interpolations.
    if point is None or type(point) is not EvalPoint:
        point = EvalPoint(fp, n, use_omega_powers=False)

    # message is a list of integers at most p
    def encode(message):
        if not all(x < p for x in message):
            raise Exception(
                "Message is improperly encoded as integers < p. It was:\n%r" % message
            )
        assert len(message) == t + 1

        the_poly = poly(message)
        return [the_poly(point(i)) for i in range(n)]

    def solve_system(encoded_message, max_e, debug=False):
        """
        input: points in form (x,y)
        output: coefficients of interpolated polynomial

        due to Jeremy Kun
        https://jeremykun.com/2015/09/07/welch-berlekamp/
        """
        for e in range(max_e, 0, -1):
            e_num_vars = e + 1
            q_num_vars = e + k

            def row(i, a, b):
                return (
                    [b * a ** j for j in range(e_num_vars)]
                    + [-1 * a ** j for j in range(q_num_vars)]
                    + [0]
                )  # the "extended" part of the linear system

            system = [row(i, a, b) for (i, (a, b)) in enumerate(encoded_message)] + [
                [fp(0)] * (e_num_vars - 1) + [fp(1)] + [fp(0)] * (q_num_vars) + [fp(1)]
            ]  # ensure coefficient of x^e in E(x) is 1

            if debug:
                logging.debug("\ne is %r" % e)
                logging.debug("\nsystem is:\n\n")
                for row in system:
                    logging.debug("\t%r" % (row,))

            solution = some_solution(system, free_variable_value=1)
            e_ = poly([solution[j] for j in range(e + 1)])
            q_ = poly([solution[j] for j in range(e + 1, len(solution))])

            if debug:
                logging.debug("\nreduced system is:\n\n")
                for row in system:
                    logging.debug("\t%r" % (row,))

                logging.debug("solution is %r" % (solution,))
                logging.debug("Q is %r" % (q_,))
                logging.debug("E is %r" % (e_,))

            p_, remainder = q_.__divmod__(e_)
            if debug:
                logging.debug("P(x) = %r" % p_)
                logging.debug("r(x) = %r" % remainder)
            if remainder.is_zero():
                return q_, e_
        raise ValueError("found no divisors!")

    def decode(encoded_msg, debug=True):
        assert len(encoded_msg) == n
        c = sum(m is None for m in encoded_msg)  # number of erasures
        assert 2 * t + 1 + c <= n
        # e = ceil((n - c - t - 1) / 2) = ((n - c - t) // 2)
        e = (n - c - t) // 2
        if debug:
            logging.debug(f"n: {n} k: {k} t: {t} c: {c}")
            logging.debug(f"decoding with e: {e}")
            logging.debug(f"decoding with c: {c}")

        enc_m = [(point(i), m) for i, m in enumerate(encoded_msg) if m is not None]

        if e == 0:
            # decode with no errors
            p_ = poly.interpolate(enc_m)
            return p_.coeffs

        q_, e_ = solve_system(enc_m, max_e=e, debug=debug)
        p_, remainder = q_.__divmod__(e_)
        if not remainder.is_zero():
            raise Exception("Q is not divisibly by E!")
        return p_.coeffs

    return encode, decode, solve_system


# compute the reduced-row echelon form of a matrix in place
def rref(matrix):
    if not matrix:
        return

    num_rows = len(matrix)
    num_cols = len(matrix[0])

    i, j = 0, 0
    while True:
        if i >= num_rows or j >= num_cols:
            break

        if matrix[i][j] == 0:
            non_zero_row = i
            while non_zero_row < num_rows and matrix[non_zero_row][j] == 0:
                non_zero_row += 1

            if non_zero_row == num_rows:
                j += 1
                continue

            temp = matrix[i]
            matrix[i] = matrix[non_zero_row]
            matrix[non_zero_row] = temp

        pivot = matrix[i][j]
        matrix[i] = [x / pivot for x in matrix[i]]

        for other_row in range(0, num_rows):
            if other_row == i:
                continue
            if matrix[other_row][j] != 0:
                matrix[other_row] = [
                    y - matrix[other_row][j] * x
                    for (x, y) in zip(matrix[i], matrix[other_row])
                ]

        i += 1
        j += 1

    return matrix


# check if a row-reduced system has no solution
# if there is no solution, return (True, dont-care)
# if there is a solution, return (False, i) where i is the index of the last nonzero row
def no_solution(a):
    i = -1
    while all(x == 0 for x in a[i]):
        i -= 1

    last_non_zero_row = a[i]
    if all(x == 0 for x in last_non_zero_row[:-1]):
        return True, 0

    return False, i


# determine if the given column is a pivot column (contains all zeros except a single 1)
# and return the row index of the 1 if it exists
def is_pivot_column(a, j):
    i = 0
    while i < len(a) and a[i][j] == 0:
        i += 1

    if i == len(a):
        return (False, i)

    if a[i][j] != 1:
        return (False, i)
    else:
        pivot_row = i

    i += 1
    while i < len(a):
        if a[i][j] != 0:
            return (False, pivot_row)
        i += 1

    return (True, pivot_row)


# return any solution of the system, with free variables set to the given value
def some_solution(system, free_variable_value=1):
    rref(system)

    has_no_solution, _ = no_solution(system)
    if has_no_solution:
        raise Exception("No solution")

    num_vars = len(system[0]) - 1  # last row is constants
    variable_values = [0] * num_vars

    free_vars = set()
    pivot_vars = set()
    row_index_to_pivot_col_idx = dict()
    pivot_row_idx = dict()

    for j in range(num_vars):
        is_pivot, row_of_pivot = is_pivot_column(system, j)
        if is_pivot:
            row_index_to_pivot_col_idx[row_of_pivot] = j
            pivot_row_idx[j] = row_of_pivot
            pivot_vars.add(j)
        else:
            free_vars.add(j)

    for j in free_vars:
        variable_values[j] = free_variable_value

    for j in pivot_vars:
        the_row = pivot_row_idx[j]
        variable_values[j] = system[the_row][-1] - sum(
            system[the_row][i] * variable_values[i] for i in free_vars
        )

    return variable_values
