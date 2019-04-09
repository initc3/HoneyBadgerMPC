from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.reed_solomon import Algorithm, EncoderFactory, DecoderFactory, \
    RobustDecoderFactory
from honeybadgermpc.reed_solomon import IncrementalDecoder
# TODO: Abstract this to a separate file instead of importing it from here.
from honeybadgermpc.batch_reconstruction import fetch_one


async def robust_reconstruct(field_futures, field, n, t, f, point, wait_for_all=False):
    use_fft = point.use_fft
    enc = EncoderFactory.get(point, Algorithm.FFT if use_fft else Algorithm.VANDERMONDE)
    dec = DecoderFactory.get(point, Algorithm.FFT if use_fft else Algorithm.VANDERMONDE)
    robust_dec = RobustDecoderFactory.get(t, point, algorithm=Algorithm.GAO)
    incremental_decoder = IncrementalDecoder(enc, dec, robust_dec, t, 1, f)
    if wait_for_all:
        incremental_decoder._min_points_required = lambda: n

    async for (idx, d) in fetch_one(field_futures):
        incremental_decoder.add(idx, [d.value])
        if incremental_decoder.done():
            polys, errors = incremental_decoder.get_results()
            return polynomials_over(field)(polys[0]), errors
    return None, None
