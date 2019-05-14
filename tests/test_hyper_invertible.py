import asyncio
from pytest import mark
from honeybadgermpc.polynomial import EvalPoint
from honeybadgermpc.hyper_invertible import generate_double_shares
from honeybadgermpc.reed_solomon import Algorithm, DecoderFactory


@mark.asyncio
@mark.parametrize("n", [4, 7])
@mark.parametrize("k", [1, 10])
async def test_generate_double_shares(test_router, polynomial, galois_field, n, k):
    t = (n-1)//3
    sends, receives, _ = test_router(n)
    shares_per_party = await asyncio.gather(*[generate_double_shares(
        n, t, k, i, sends[i], receives[i], galois_field) for i in range(n)])
    assert len(shares_per_party) == n
    assert all(len(random_shares) == (n-2*t)*k for random_shares in shares_per_party)
    random_values = []
    eval_point = EvalPoint(galois_field, n, use_fft=True)
    decoder = DecoderFactory.get(eval_point, Algorithm.FFT)
    for i, shares in enumerate(zip(*shares_per_party)):
        shares_t, shares_2t = zip(*shares)
        r_t = polynomial(decoder.decode(list(range(n)), shares_t))(0)
        r_2t = polynomial(decoder.decode(list(range(n)), shares_2t))(0)
        assert r_t == r_2t
        random_values.append(r_t)
    assert len(set(random_values)) == (n-2*t) * k
