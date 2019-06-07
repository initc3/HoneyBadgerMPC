from pytest import mark
from honeybadgermpc.preprocessing import PreProcessedElements


@mark.parametrize("n,t,k", [
    (4, 1, 2**i) for i in range(3, 11)]
    + [(7, 2, 2**i) for i in range(3, 11)]
)
def test_benchmark_batch_opening(benchmark_runner, n, t, k):
    pp_elements = PreProcessedElements()

    num_rands = sum([2**i for i in range(3, 11)])*n

    async def _prog(context):
        await context.ShareArray(
            [pp_elements.get_rand(context) for _ in range(k)]).open()

    benchmark_runner(_prog, n, t, ['rands'], num_rands)
