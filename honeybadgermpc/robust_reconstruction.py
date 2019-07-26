from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.reed_solomon import (
    Algorithm,
    EncoderFactory,
    DecoderFactory,
    RobustDecoderFactory,
)
from honeybadgermpc.reed_solomon import IncrementalDecoder

# TODO: Abstract this to a separate file instead of importing it from here.
from honeybadgermpc.batch_reconstruction import fetch_one
from honeybadgermpc.ntl import OpaqueZZp_to_py, py_to_OpaqueZZp


async def robust_reconstruct(field_futures, field, n, t, point, degree):
    use_omega_powers = point.use_omega_powers
    enc = EncoderFactory.get(
        point, Algorithm.FFT if use_omega_powers else Algorithm.VANDERMONDE
    )
    dec = DecoderFactory.get(
        point, Algorithm.FFT if use_omega_powers else Algorithm.VANDERMONDE
    )
    robust_dec = RobustDecoderFactory.get(t, point, algorithm=Algorithm.GAO)
    incremental_decoder = IncrementalDecoder(enc, dec, robust_dec, degree, 1, t)

    async for (idx, d) in fetch_one(field_futures):
        data = py_to_OpaqueZZp([d.value], d.modulus)
        incremental_decoder.add(idx, data)
        if incremental_decoder.done():
            polys, errors = incremental_decoder.get_results()
            polys = OpaqueZZp_to_py(polys)
            return polynomials_over(field)(polys[0]), errors
    return None, None
