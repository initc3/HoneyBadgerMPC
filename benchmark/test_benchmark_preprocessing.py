from pytest import mark, param

from honeybadgermpc.preprocessing import PreProcessedElements


@mark.parametrize(
    "n,t,k", [param(4, 1, 1024, marks=mark.skip_bench), (16, 5, 512), (50, 15, 256)]
)
def test_benchmark_generate_rands(benchmark, n, t, k):
    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()
    benchmark(pp_elements.generate_rands, k, n, t)


@mark.parametrize(
    "n,t,k,z",
    [param(4, 1, 64, 64, marks=mark.skip_bench), (16, 5, 32, 32), (61, 20, 32, 32)],
)
def test_benchmark_generate_powers(benchmark, n, t, k, z):
    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()
    benchmark(pp_elements.generate_powers, k, n, t, z)
