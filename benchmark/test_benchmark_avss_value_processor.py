from pytest import mark, fixture
from pickle import dumps
from honeybadgermpc.avss_value_processor import AvssValueProcessor


@mark.parametrize("k", [2 ** i for i in range(5, 15, 3)])
@mark.parametrize("n", [2 ** i for i in range(2, 7, 1)])
@mark.asyncio
async def test_benchmark_process_outputs(benchmark, n, k):
    t = (n-1)//3
    processor = AvssValueProcessor(None, None, n, t, 0, None, None, None)
    acs_outputs = [[list() for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            acs_outputs[i][j] = k + 10*j
        acs_outputs[i] = dumps(acs_outputs[i])
    benchmark(processor._process_acs_output, acs_outputs)
