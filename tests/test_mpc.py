import asyncio
from pytest import mark, raises
from honeybadgermpc.mpc import TaskProgramRunner


@mark.asyncio
async def test_open_shares(test_preprocessing):
    t = 1
    n = 3*t+1
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
async def test_wait_for_all(test_preprocessing):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        if context.myid != 0:
            # This should fail because we want to wait
            # for all and 0th node did not send any value.
            with raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    test_preprocessing.elements.get_zero(context).open(
                        wait_for_all=True), 0.5)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_wait_for_all_share_array(test_preprocessing):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        if context.myid != 0:
            # This should fail because we want to wait
            # for all and 0th node did not send any value.
            with raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    context.ShareArray([test_preprocessing.elements.get_zero(
                        context).v for i in range(10)]).open(
                        wait_for_all=True), 0.5)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_t_faults(test_preprocessing, galois_field):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        if context.myid != 0:
            share = await test_preprocessing.elements.get_zero(context).open()
        else:
            # 0th node sends a faulty value.
            share = await context.Share(galois_field.random()).open()
        return share

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
    assert len(set(results)) == 1
    assert results[0] == 0


@mark.asyncio
async def test_t_faults_share_array(test_preprocessing, galois_field):
    t = 1
    n = 3*t+1
    k = 10
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        if context.myid != 0:
            shares = await context.ShareArray([test_preprocessing.elements.get_zero(
                context).v for i in range(10)]).open()
        else:
            # 0th node sends a faulty value.
            shares = await context.ShareArray(
                [galois_field.random() for _ in range(k)]).open()
        return shares

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    secrets = await program_runner.join()
    assert len(secrets) == n
    assert all(len(secrets) == k for secrets in secrets)
    assert all(secret == 0 for secrets in secrets for secret in secrets)


@mark.asyncio
async def test_more_than_t_faults_fail_with_timeout(test_preprocessing, galois_field):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        # This fails because we have more than `t` faults.
        with raises(asyncio.TimeoutError):
            if context.myid in [0, 1]:
                await asyncio.wait_for(
                    test_preprocessing.elements.get_zero(context).open(), 0.5)
            else:
                await asyncio.wait_for(context.Share(galois_field.random()).open(), 0.5)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_more_than_t_faults_fail_with_timeout_share_array(
        test_preprocessing, galois_field):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        # This fails because we have more than `t` faults.
        if context.myid in [0, 1]:
            shares = await asyncio.wait_for(context.ShareArray(
                [galois_field.random() for i in range(10)]).open(), 0.5)
        else:
            shares = await asyncio.wait_for(
                context.ShareArray([test_preprocessing.elements.get_zero(
                    context).v for i in range(10)]).open(), 0.5)
        assert shares is None

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_double_share(test_preprocessing):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("rands", n, 2*t)

    async def _prog(context):
        # 0th node does not send a value so this should hang.
        if context.myid != 0:
            with raises(asyncio.TimeoutError):
                share = await asyncio.wait_for(
                    test_preprocessing.elements.get_rand(context, 2*t).open(), 0.5)
                return share

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_double_share_array(test_preprocessing):
    t = 1
    n = 3*t+1
    test_preprocessing.generate("rands", n, 2*t)

    async def _prog(context):
        # 0th node does not send a value so this should hang.
        if context.myid != 0:
            with raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    context.ShareArray([test_preprocessing.elements.get_rand(
                        context, 2*t).v for i in range(10)], 2*t).open(), 0.5)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
