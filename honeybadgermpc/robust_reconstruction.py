import asyncio
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.reed_solomon import get_rs_encoder, get_rs_robust_decoder, \
    get_rs_decoder, IncrementalDecoder


async def fetch_one(aws):
    aws_to_idx = {aws[i]: i for i in range(len(aws))}
    pending = set(aws)
    while len(pending) > 0:
        done, pending = await asyncio.wait(pending,
                                           return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            yield (aws_to_idx[d], await d)


async def robust_reconstruct(field_futures, field, n, t, point):
    use_fft = point.use_fft
    enc = get_rs_encoder(point, 'fft' if use_fft else 'vandermonde')
    dec = get_rs_decoder(point, 'fft' if use_fft else 'vandermonde')
    robust_dec = get_rs_robust_decoder(t, point)
    online_decoder = IncrementalDecoder(enc, dec, robust_dec, t, 1, t)

    async for (idx, d) in fetch_one(field_futures):
        online_decoder.add(idx, [d.value])
        if online_decoder.done():
            polys, errors = online_decoder.get_results()
            return polynomials_over(field)(polys[0]), errors
    return None, None
