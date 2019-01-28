from pytest import mark
import asyncio
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup

security_parameter = 32
Field = GF.get(Subgroup.BLS12_381)

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


@mark.haha
@mark.asyncio
@mark.usefixtures('zeros_shares_files', 'random_shares_files', 'bits_shares_files', 'triples_shares_files')
async def test_equality(zeros_files_prefix, random_files_prefix, bits_files_prefix, triples_files_prefix):
    from honeybadgermpc.mpc import TaskProgramRunner
    N, t = 3, 1
    p_secret, q_secret = 2333, 2333

    def legendre_mod_p(a):
        """Return the legendre symbol ``legendre(a, p)`` where *p* is the
        order of the field of *a*.
        """

        assert a.modulus % 2 == 1
        b = (a ** ((a.modulus - 1)//2))
        if b == 1:
            return 1
        elif b == a.modulus-1:
            return -1
        return 0

    async def beaver_mul(context, x, y):
        filename = f'{triples_files_prefix}-{context.myid}.share'
        triples = context.read_shares(open(filename))

        a, b, ab = triples[:3]

        # 1 round version instead of 2
        _D = (x - a).open()
        _E = (y - b).open()
        D, E = await asyncio.gather(_D, _E)

        # This is a random share of x*y
        # xy = context.Share(D*E) + D*b + E*a + ab ?
        xy = D*E + D*b + E*a + ab

        return xy

    async def _prog(context):
        filename = f'{zeros_files_prefix}-{context.myid}.share'
        zeros = context.read_shares(open(filename))
        filename = f'{random_files_prefix}-{context.myid}.share'
        randoms = context.read_shares(open(filename))
        filename = f'{bits_files_prefix}-{context.myid}.share'
        bits = context.read_shares(open(filename))
        
        p = zeros[0] + context.Share(p_secret)
        q = zeros[1] + context.Share(q_secret)
        diff_a = p - q
        k = security_parameter

        async def _gen_test_bit():

            # b \in {0, 1}
            # _b \in {5, 1}, for p = 1 mod 8, s.t. (5/p) = -1
            # so _b = -4 * b + 5
            _b = (-4) * bits[0] + context.Share(5)
            _r, _rp = randoms[:2]

            # c = a * r + b * rp * rp
            # If b_i == 1 c_i will always be a square modulo p if a is
            # zero and with probability 1/2 otherwise (except if rp == 0).
            # If b_i == -1 it will be non-square.
            # TODO
            _c = await beaver_mul(context, diff_a, _r) + await beaver_mul(context, _b, await beaver_mul(context, _rp, _rp))
            c = await _c.open()

            return c, _b

        async def gen_test_bit():
            cj, bj = await _gen_test_bit()
            while cj == 0:
                cj, bj = await _gen_test_bit()
            # bj.open() \in {5, 1}

            legendre = legendre_mod_p(cj)

            if legendre == 1:
                xj = (1 / Field(2)) * (bj + context.Share(1))
            elif legendre == -1:
                xj = (-1) * (1 / Field(2)) * (bj - context.Share(1))
            else:
                gen_test_bit()

            return xj

        # gather --> constant round
        x = [await gen_test_bit() for _ in range(k)]

        # Take the product (this is here the same as the "and") of all
        # the x'es
        while len(x) > 1:
            x.append(await beaver_mul(context, x.pop(0), x.pop(0)))

        return await x[0].open()


    programRunner = TaskProgramRunner(N, t)
    programRunner.add(_prog)
    results = await programRunner.join()
    assert len(results) == N
    # print(results)
    for res in results:
        if res == 0:
            print("The two numbers are different! (with high probability)")
        else:
            print("The two numbers are equal!")
        



