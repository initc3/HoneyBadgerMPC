import asyncio
import logging
from honeybadgermpc.wb_interpolate import make_encoder_decoder
from honeybadgermpc.polynomial import polynomials_over


async def wait_for(aws, to_wait):
    done, pending = set(), set(aws)
    while len(done) < to_wait:
        _d, pending = await asyncio.wait(pending,
                                         return_when=asyncio.FIRST_COMPLETED)
        done |= _d
    return done, pending


def attempt_reconstruct(encoded, field, n, t, point, precomputed_data=None):
    # Attempt to reconstruct with a mixture of erasures or errors
    assert len(encoded) == n
    assert sum(f is not None for f in encoded) >= 2*t + 1

    # raise ValueError("Sentinel bug")

    # interpolate with error correction to get f(j,y)
    _, decode, _ = make_encoder_decoder(n, t+1, field.modulus, point)

    p = polynomials_over(field)(decode(encoded, precomputed_data=precomputed_data))
    if p.degree() > t:
        raise ValueError("Wrong degree")

    # check for errors
    coincides = 0
    failures_detected = set()
    for j in range(n):
        if encoded[j] is None:
            continue
        if p(point(j)) == encoded[j]:
            coincides += 1
        else:
            failures_detected.add(j)

    if coincides >= 2 * t + 1:
        return p, failures_detected
    else:
        raise ValueError("Did not coincide")


async def robust_reconstruct(field_futures, field, n, t, point):
    # Wait for between 2t+1 values and N values,
    # trying to reconstruct each time
    assert 2*t < n, "Robust reconstruct waits for at least n=2t+1 values"
    for nAvailable in range(2*t + 1, n+1):
        try:
            await wait_for(field_futures, nAvailable)
            elems = [f.result() if f.done() else None for f in field_futures]
            P, failures = attempt_reconstruct(elems, field, n, t, point)
            return P, failures
        except ValueError as e:
            logging.debug(f'ValueError: {e}')
            if str(e) in ("Wrong degree", "no divisors found"):
                continue
            else:
                raise e
    assert False, "shouldn't reach the end here"
