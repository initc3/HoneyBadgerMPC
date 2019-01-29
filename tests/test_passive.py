from pytest import mark


@mark.asyncio
async def test_open_shares():
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.preprocessing import PreProcessedElements

    N, t = 3, 1
    number_of_secrets = 100
    pp_elements = PreProcessedElements()
    pp_elements.generate_zeros(100, N, t)

    async def _prog(context):
        secrets = []
        for _ in range(number_of_secrets):
            s = await pp_elements.get_zero(context).open()
            assert s == 0
            secrets.append(s)
        print('[%d] Finished' % (context.myid,))
        return secrets

    programRunner = TaskProgramRunner(N, t)
    programRunner.add(_prog)
    results = await programRunner.join()
    assert len(results) == N
    assert all(len(secrets) == number_of_secrets for secrets in results)
    assert all(secret == 0 for secrets in results for secret in secrets)


@mark.asyncio
async def test_beaver_mul_with_zeros():
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mpc import PreProcessedElements

    N, t = 3, 1
    x_secret, y_secret = 10, 15
    pp_elements = PreProcessedElements()
    pp_elements.generate_zeros(2, N, t)
    pp_elements.generate_triples(1, N, t)

    async def _prog(context):
        # Example of Beaver multiplication
        x = pp_elements.get_zero(context) + context.Share(x_secret)
        y = pp_elements.get_zero(context) + context.Share(y_secret)

        a, b, ab = pp_elements.get_triple(context)
        assert await a.open() * await b.open() == await ab.open()

        D = (x - a).open()
        E = (y - b).open()

        # This is a random share of x*y
        xy = D*E + D*b + E*a + ab

        X, Y, XY = await x.open(), await y.open(), await xy.open()
        assert X * Y == XY

        print("[%d] Finished" % (context.myid,), X, Y, XY)
        return XY

    programRunner = TaskProgramRunner(N, t)
    programRunner.add(_prog)
    results = await programRunner.join()
    assert len(results) == N
    assert all(res == x_secret * y_secret for res in results)


@mark.asyncio
async def test_beaver_mul():
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.preprocessing import PreProcessedElements

    N, t = 3, 1
    pp_elements = PreProcessedElements()
    pp_elements.generate_rands(2, N, t)
    pp_elements.generate_triples(1, N, t)

    async def _prog(context):
        # Example of Beaver multiplication
        x, y = pp_elements.get_rand(context), pp_elements.get_rand(context)

        a, b, ab = pp_elements.get_triple(context)
        assert await a.open() * await b.open() == await ab.open()

        D = (x - a).open()
        E = (y - b).open()

        # This is a random share of x*y
        xy = D*E + D*b + E*a + ab

        X, Y, XY = await x.open(), await y.open(), await xy.open()
        assert X * Y == XY

        print("[%d] Finished" % (context.myid,), X, Y, XY)
        return XY

    programRunner = TaskProgramRunner(N, t)
    programRunner.add(_prog)
    results = await programRunner.join()
    assert len(results) == N
