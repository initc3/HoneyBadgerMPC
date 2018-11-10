from pytest import mark


@mark.asyncio
@mark.usefixtures('zeros_shares_files')
async def test_open_shares(zeros_files_prefix):
    from honeybadgermpc.mpc import TaskProgramRunner
    N, t = 3, 1
    number_of_secrets = 100

    async def _prog(context):
        filename = f'{zeros_files_prefix}-{context.myid}.share'
        shares = context.read_shares(open(filename))

        print('[%d] read %d shares' % (context.myid, len(shares)))

        secrets = []
        for share in shares[:number_of_secrets]:
            s = await share.open()
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
@mark.usefixtures('zeros_shares_files', 'triples_shares_files')
async def test_beaver_mul_with_zeros(zeros_files_prefix, triples_files_prefix):
    from honeybadgermpc.mpc import TaskProgramRunner
    N, t = 3, 1
    x_secret, y_secret = 10, 15

    async def _prog(context):
        filename = f'{zeros_files_prefix}-{context.myid}.share'
        zeros = context.read_shares(open(filename))
        filename = f'{triples_files_prefix}-{context.myid}.share'
        triples = context.read_shares(open(filename))

        # Example of Beaver multiplication
        x = zeros[0] + context.Share(x_secret)
        y = zeros[1] + context.Share(y_secret)

        a, b, ab = triples[:3]
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
@mark.usefixtures('random_shares_files', 'triples_shares_files')
async def test_beaver_mul(random_polys, random_files_prefix, triples_files_prefix):
    from honeybadgermpc.mpc import TaskProgramRunner
    N, t = 3, 1
    f, g = random_polys[:2]
    x_secret, y_secret = f(0), g(0)

    async def _prog(context):
        filename = f'{random_files_prefix}-{context.myid}.share'
        randoms = context.read_shares(open(filename))
        filename = f'{triples_files_prefix}-{context.myid}.share'
        triples = context.read_shares(open(filename))

        # Example of Beaver multiplication
        x, y = randoms[:2]

        a, b, ab = triples[:3]
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
