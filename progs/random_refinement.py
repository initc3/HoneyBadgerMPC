from honeybadgermpc.polynomial import EvalPoint
from honeybadgermpc.reed_solomon import EncoderFactory


def refine_randoms(n, t, k, field, random_share_batches):
    assert 3*t + 1 <= n

    # Number of nodes which have contributed values to these batches
    assert k >= n-t and k <= n
    assert all(len(batch) == k for batch in random_share_batches)

    encoder = EncoderFactory.get(EvalPoint(field, n, use_fft=True))

    # Assume these shares to be the coefficients of a random polynomial. The
    # refined shares are evaluations of this polynomial at powers of omega.
    output_batches = encoder.encode(random_share_batches)

    # Remove `t` shares since they might have been contributed by corrupt parties.
    refined_shares = [batch[:k-t] for batch in output_batches]

    return refined_shares
