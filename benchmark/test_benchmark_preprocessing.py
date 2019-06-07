from pytest import mark
from honeybadgermpc.preprocessing import PreProcessedElements


@mark.parametrize("n,t,k", [(4, 1, 1024), (16, 5, 512), (50, 15, 256)])
def test_benchmark_generate_rands(benchmark, n, t, k):
    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()
    benchmark(pp_elements.generate_rands, k, n, t)


@mark.parametrize("n,t,k,z", [(4, 1, 64, 64), (16, 5, 32, 32), (61, 20, 32, 32)])
def test_benchmark_generate_powers(benchmark, n, t, k, z):
    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()
    benchmark(pp_elements.generate_powers, k, n, t, z)
