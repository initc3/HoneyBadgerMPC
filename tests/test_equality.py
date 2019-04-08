from pytest import mark


@mark.asyncio
async def test_equality(test_preprocessing, galois_field):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mixins import BeaverTriple, MixinOpName
    from honeybadgermpc.equality import equality

    n, t = 3, 1
    test_preprocessing.generate("zeros", n, t)
    test_preprocessing.generate("rands", n, t)
    test_preprocessing.generate("bits", n, t)
    test_preprocessing.generate("triples", n, t)

    async def _prog(context):
        share0 = test_preprocessing.elements.get_zero(context)
        share1 = test_preprocessing.elements.get_rand(context)
        share1_ = share0 + share1
        share2 = test_preprocessing.elements.get_rand(context)

        assert await equality(context, share1, share1_)
        assert not await equality(context, share1, share2)

    program_runner = TaskProgramRunner(n, t, {
        MixinOpName.MultiplyShare: BeaverTriple.multiply_shares,
    })
    program_runner.add(_prog)
    await program_runner.join()
