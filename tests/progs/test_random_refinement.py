from progs.random_refinement import refine_randoms
from honeybadgermpc.polynomial import get_omega
from pytest import mark


@mark.parametrize("n, t, k", [(4, 1, 3), (4, 1, 4), (7, 2, 5)])
def test_random_refinement(n, t, k, galois_field, test_preprocessing, polynomial):
    random_shares_gf = [galois_field.random() for _ in range(k)]
    random_shares_int = [int(i) for i in random_shares_gf]
    d = 2**(k-1).bit_length()
    omega = get_omega(galois_field, 2*d, seed=0)
    xs = [pow(omega, 2*i) for i in range(d)]
    poly = polynomial.interpolate(zip(xs, random_shares_gf))
    refined_share_gfs = refine_randoms(n, t, galois_field, random_shares_int)
    assert len(refined_share_gfs) == k-t
    for i, share in enumerate(refined_share_gfs):
        assert isinstance(share, int)
        poly(pow(omega, 2*i+1)) == share
