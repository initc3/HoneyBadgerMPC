import asyncio
from pytest import mark
from honeybadgermpc.polynomial import EvalPoint
from honeybadgermpc.offline_randousha import randousha, generate_triples, generate_bits
from honeybadgermpc.reed_solomon import Algorithm, DecoderFactory


@mark.asyncio
@mark.parametrize("n", [4, 7])
@mark.parametrize("k", [1, 10])
async def test_randousha(test_router, polynomial, galois_field, n, k):
    t = (n - 1) // 3
    sends, receives, _ = test_router(n)
    shares_per_party = await asyncio.gather(
        *[randousha(n, t, k, i, sends[i], receives[i], galois_field) for i in range(n)]
    )
    assert len(shares_per_party) == n
    assert all(
        len(random_shares) == (n - 2 * t) * k for random_shares in shares_per_party
    )
    random_values = []
    eval_point = EvalPoint(galois_field, n, use_omega_powers=False)
    decoder = DecoderFactory.get(eval_point, Algorithm.VANDERMONDE)
    for i, shares in enumerate(zip(*shares_per_party)):
        shares_t, shares_2t = zip(*shares)
        poly_t = polynomial(decoder.decode(list(range(n)), shares_t))
        poly_2t = polynomial(decoder.decode(list(range(n)), shares_2t))
        r_t = poly_t(0)
        r_2t = poly_2t(0)
        assert len(poly_t.coeffs) == t + 1
        assert len(poly_2t.coeffs) == 2 * t + 1
        assert r_t == r_2t
        random_values.append(r_t)
    assert len(set(random_values)) == (n - 2 * t) * k


@mark.asyncio
@mark.parametrize("n", [4])
@mark.parametrize("k", [1])
async def test_double_decode(n, k, polynomial, galois_field, test_router, test_runner):
    t = (n - 1) // 3
    sends, receives, _ = test_router(n)
    shares_per_party = await asyncio.gather(
        *[randousha(n, t, k, i, sends[i], receives[i], galois_field) for i in range(n)]
    )
    assert len(shares_per_party) == n

    async def _prog(context):
        # Every party needs its share of all the `N` triples' shares
        shares = shares_per_party[context.myid]
        shares_t, shares_2t = list(zip(*shares))
        assert len(shares_t) == (n - 2 * t) * k
        assert len(shares_2t) == (n - 2 * t) * k
        rs_t = await context.ShareArray(shares_t).open()
        rs_2t = await context.ShareArray(shares_2t, 2 * t).open()
        assert rs_t == rs_2t

    await test_runner(_prog, n, t)


@mark.asyncio
@mark.parametrize("n", [4])
@mark.parametrize("k", [1])
async def test_triples(n, k, polynomial, galois_field, test_router, test_runner):
    t = (n - 1) // 3
    sends, receives, _ = test_router(n)
    triples_per_party = await asyncio.gather(
        *[
            generate_triples(n, t, k, i, sends[i], receives[i], galois_field)
            for i in range(n)
        ]
    )
    assert len(triples_per_party) == n

    async def _prog(context):
        # Every party needs its share of all the `N` triples' shares
        triples = triples_per_party[context.myid]
        a, b, ab = list(zip(*triples))
        assert len(a) == k
        as_t = await context.ShareArray(a).open()
        bs_t = await context.ShareArray(b).open()
        abs_t = await context.ShareArray(ab).open()
        abs_expected = [a_ * b_ for a_, b_ in zip(as_t, bs_t)]
        assert abs_expected == abs_t

    await test_runner(_prog, n, t)


@mark.asyncio
@mark.parametrize("n", [4])
@mark.parametrize("k", [10])
async def test_bits(n, k, polynomial, galois_field, test_router, test_runner):
    t = (n - 1) // 3
    sends, receives, _ = test_router(n)
    bits_per_party = await asyncio.gather(
        *[
            generate_bits(n, t, k, i, sends[i], receives[i], galois_field)
            for i in range(n)
        ]
    )
    assert len(bits_per_party) == n

    async def _prog(context):
        bits_t = bits_per_party[context.myid]
        assert len(bits_t) == k
        bits = await context.ShareArray(bits_t).open()
        for bit in bits:
            assert bit in (galois_field(-1), galois_field(1))

    await test_runner(_prog, n, t)
