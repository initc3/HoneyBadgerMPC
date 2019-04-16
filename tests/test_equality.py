from pytest import mark


@mark.asyncio
async def test_equality(test_preprocessing, galois_field):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mixins import BeaverTriple, MixinOpName
    from honeybadgermpc.equality import equality

    n, t = 3, 1
    to_generate = ['zeros', 'rands', 'triples', 'bits']
    for x in to_generate:
        test_preprocessing.generate(x, n, t, k=2000)

    async def _prog(context):
        share0 = test_preprocessing.elements.get_zero(context)
        share1 = test_preprocessing.elements.get_rand(context)
        share1_ = share0 + share1
        share2 = test_preprocessing.elements.get_rand(context)

        assert await (await equality(context, share1, share1_)).open()
        assert not await (await equality(context, share1, share2)).open()

    program_runner = TaskProgramRunner(n, t, {
        MixinOpName.MultiplyShare: BeaverTriple.multiply_shares,
        MixinOpName.MultiplyShareArray: BeaverTriple.multiply_share_arrays
    })
    program_runner.add(_prog)
    await program_runner.join()
