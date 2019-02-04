from pytest import mark


@mark.asyncio
@mark.usefixtures('test_preprocessing')
async def test_open_shares(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t = 3, 1
    number_of_secrets = 100
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        secrets = []
        for _ in range(number_of_secrets):
            s = await test_preprocessing.elements.get_zero(context).open()
            assert s == 0
            secrets.append(s)
        print('[%d] Finished' % (context.myid,))
        return secrets

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
    assert all(len(secrets) == number_of_secrets for secrets in results)
    assert all(secret == 0 for secrets in results for secret in secrets)


@mark.asyncio
@mark.usefixtures('test_preprocessing')
async def test_beaver_mul_with_zeros(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t = 3, 1
    x_secret, y_secret = 10, 15
    test_preprocessing.generate("zeros", n, t)
    test_preprocessing.generate("triples", n, t)

    async def _prog(context):
        # Example of Beaver multiplication
        x = test_preprocessing.elements.get_zero(context) + context.Share(x_secret)
        y = test_preprocessing.elements.get_zero(context) + context.Share(y_secret)

        a, b, ab = test_preprocessing.elements.get_triple(context)
        assert await a.open() * await b.open() == await ab.open()

        d = (x - a).open()
        e = (y - b).open()

        # This is a random share of x*y
        xy = d*e + d*b + e*a + ab

        x_, y_, xy_ = await x.open(), await y.open(), await xy.open()
        assert x_ * y_ == xy_

        print("[%d] Finished" % (context.myid,), x_, y_, xy_)
        return xy_

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
    assert all(res == x_secret * y_secret for res in results)


@mark.asyncio
@mark.usefixtures('test_preprocessing')
async def test_beaver_mul(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t = 3, 1
    test_preprocessing.generate("triples", n, t)
    test_preprocessing.generate("rands", n, t)

    async def _prog(context):
        # Example of Beaver multiplication
        x = test_preprocessing.elements.get_rand(context)
        y = test_preprocessing.elements.get_rand(context)

        a, b, ab = test_preprocessing.elements.get_triple(context)
        assert await a.open() * await b.open() == await ab.open()

        d = (x - a).open()
        e = (y - b).open()

        # This is a random share of x*y
        xy = d*e + d*b + e*a + ab

        x_, y_, xy_ = await x.open(), await y.open(), await xy.open()
        assert x_ * y_ == xy_

        print("[%d] Finished" % (context.myid,), x_, y_, xy_)
        return xy_

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
