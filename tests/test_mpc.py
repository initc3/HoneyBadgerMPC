from pytest import mark


@mark.asyncio
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


async def test_xor(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t = 3, 1
    number_of_secrets = 100

    async def _prog(context):
        x = context.Share(10)
        y = context.Share(5)
        z = context.field(5)

        xor1 = x^y
        xor2 = x^z

        assert xor1 == context.Share(15)
        assert xor2 == context.field(15)


    