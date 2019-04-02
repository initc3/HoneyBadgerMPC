from pytest import mark, fixture
from pickle import dumps
from random import shuffle
from honeybadgermpc.avss_value_processor import AvssValueProcessor


@mark.parametrize("k", [2 ** i for i in range(4, 11, 2)])
@mark.parametrize("n", [2 ** i for i in range(2, 8, 1)])
@mark.asyncio
async def test_benchmark_process_outputs(benchmark, n, k):
    t = (n-1)//3
    processor = AvssValueProcessor(None, None, n, t, 0, None, None, None)
    acs_outputs = [[list() for _ in range(n)] for _ in range(n)]
    steps = list(range(0, -(n//2), -1)) + list(range(0, (n//2), 1))
    assert len(steps) == n
    for i in range(n):
        for j in range(n):
            acs_outputs[i][j] = k + steps[j]
    for i in range(n):
        z = 0
        acs_outputs[i].sort()
        arr = acs_outputs[i]
        while arr[z] < 0:
            s = arr[z]+arr[-z-1]
            if s % 2 == 0:
                arr[z] = s//2-1
                arr[-z-1] = s//2+1
            else:
                arr[z] = s//2
                arr[-z-1] = s//2+1
            z += 1
        assert all(u >= 0 for u in acs_outputs[i])
        assert sum(acs_outputs[i]) == k*n
        # All this is to exercise the sorting component and keep
        # the average number of values across all nodes as k.
        shuffle(acs_outputs[i])
        acs_outputs[i] = dumps(acs_outputs[i])
    benchmark(processor._process_acs_output, acs_outputs)
