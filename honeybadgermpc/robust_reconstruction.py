import asyncio
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.reed_solomon import Algorithm, EncoderFactory, DecoderFactory, \
    RobustDecoderFactory
from honeybadgermpc.reed_solomon import IncrementalDecoder


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
    enc = EncoderFactory.get(point, Algorithm.FFT if use_fft else Algorithm.VANDERMONDE)
    dec = DecoderFactory.get(point, Algorithm.FFT if use_fft else Algorithm.VANDERMONDE)
    robust_dec = RobustDecoderFactory.get(t, point, algorithm=Algorithm.GAO)
    incremental_decoder = IncrementalDecoder(enc, dec, robust_dec, t, 1, t)

    async for (idx, d) in fetch_one(field_futures):
        incremental_decoder.add(idx, [d.value])
        if incremental_decoder.done():
            polys, errors = incremental_decoder.get_results()
            return polynomials_over(field)(polys[0]), errors
    return None, None
