from pytest import mark
from progs.random_refinement import refine_randoms


@mark.parametrize("n", [4, 10, 16, 50, 100])
def test_benchmark_random_refinement(benchmark, n, galois_field):
    t = (n-1)//3
    num_batches = max(n, 62000//n)
    random_share_batches = [[galois_field.random().value for _ in range(n)]
                            for _ in range(num_batches)]
    benchmark(refine_randoms, n, t, n, galois_field, random_share_batches)
