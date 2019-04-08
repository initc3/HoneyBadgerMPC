from pytest import mark

@mark.asyncio
async def test_equality(test_preprocessing, galois_field):
    import asyncio
    import random
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.equality import equality

    n, t = 4, 1
    num_rands = 10
    test_preprocessing.generate("zeros", n, t)
    test_preprocessing.generate("rands", n, t)
    test_preprocessing.generate("bits", n, t)

    async def _prog(context):
        shares0 = [test_preprocessing.elements.get_zero(context) for _ in range(num_rands)]
        nums1 = [random.randint(0, galois_field.modulus) for _ in range(num_rands)]
        nums2 = [random.randint(0, galois_field.modulus) for _ in range(num_rands)]

        shares1 = [context.Share(x) for x in nums1]
        shares1_ = [shares0[i] + shares1[i] for i in range(num_rands)]
        shares2 = [context.Share(x) for x in nums2]

        for i in range(num_rands):
            if await equality(context, shares1[i], shares1_[i]):
                pass
            # assert not await equality(context, shares1[i], shares2[i])
            

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
    