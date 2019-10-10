from honeybadgermpc.polynomial import EvalPoint
from honeybadgermpc.reed_solomon import EncoderFactory


def refine_randoms(n, t, field, random_shares_int):
    assert 3 * t + 1 <= n

    # Number of nodes which have contributed values to this batch
    k = len(random_shares_int)
    assert k >= n - t and k <= n

    encoder = EncoderFactory.get(EvalPoint(field, n, use_omega_powers=True))

    # Assume these shares to be the coefficients of a random polynomial. The
    # refined shares are evaluations of this polynomial at powers of omega.
    output_shares_int = encoder.encode(random_shares_int)

    # Remove `t` shares since they might have been contributed by corrupt parties.
    return output_shares_int[: k - t]
