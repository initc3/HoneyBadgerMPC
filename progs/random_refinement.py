from honeybadgermpc.polynomial import get_omega, polynomials_over
import cProfile, pstats, io

def refine_randoms(n, t, field, random_shares_int):
    assert 3*t + 1 <= n

    # Number of nodes which have contributed values to this batch
    k = len(random_shares_int)
    assert k >= n-t and k <= n

    d = 2**(k-1).bit_length()  # Get the nearest power of 2
    omega = get_omega(field, 2*d, seed=0)
    random_shares_int += [0]*(d-k)
    output_shares_int = polynomials_over(field).interp_extrap_cpp(
        random_shares_int, omega)

    # Output only values at the odd indices
    return output_shares_int[1:2*(k-t):2]


if __name__ == "__main__":
    from honeybadgermpc.field import GF
    from honeybadgermpc.elliptic_curve import Subgroup
    field = GF.get(Subgroup.BLS12_381)
    n = pow(2, 15)
    t = (n-1)//3
    random_shares_int = [field.random().value for _ in range(n)]
    pr = cProfile.Profile()
    pr.enable()
    refine_randoms(n, t, field, random_shares_int)
    pr.disable()
    s = io.StringIO()
    sortby = 'time'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats()
    print(s.getvalue())