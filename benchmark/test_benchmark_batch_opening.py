from asyncio import get_event_loop
from pytest import mark
from honeybadgermpc.mpc import TaskProgramRunner


@mark.parametrize("n,t,k", [
        (4, 1, 2**i) for i in range(3, 11)]
        + [(7, 2, 2**i) for i in range(3, 11)]
    )
def test_benchmark_batch_opening(benchmark, test_preprocessing, n, t, k):
    num_rands = sum([2**i for i in range(3, 11)])*n
    test_preprocessing.generate("rands", n, t, k=num_rands)

    async def _prog(context):
        await context.ShareArray(
            [test_preprocessing.elements.get_rand(context) for _ in range(k)]).open()

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    loop = get_event_loop()

    def _work():
        loop.run_until_complete(program_runner.join())

    benchmark(_work)
