from pytest import mark
from honeybadgermpc.progs.random_refinement import refine_randoms


@mark.parametrize("n", [4, 10, 16, 50, 100])
def test_benchmark_random_refinement(benchmark, n, galois_field):
    t = (n - 1) // 3
    random_shares_int = [galois_field.random().value for _ in range(n)]
    benchmark(refine_randoms, n, t, galois_field, random_shares_int)
