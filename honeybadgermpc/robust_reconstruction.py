import asyncio
import logging
from honeybadgermpc.wb_interpolate import makeEncoderDecoder
from honeybadgermpc.polynomial import polynomialsOver


async def waitFor(aws, to_wait):
    done, pending = set(), set(aws)
    while len(done) < to_wait:
        _d, pending = await asyncio.wait(pending,
                                         return_when=asyncio.FIRST_COMPLETED)
        done |= _d
    return done, pending


def attempt_reconstruct(encoded, field, n, t, point):
    # Attempt to reconstruct with a mixture of erasures or errors
    assert len(encoded) == n
    assert sum(f is not None for f in encoded) >= 2*t + 1

    # raise ValueError("Sentinel bug")

    # interpolate with error correction to get f(j,y)
    _, decode, _ = makeEncoderDecoder(n, t+1, field.modulus)

    P = polynomialsOver(field)(decode(encoded))
    if P.degree() > t:
        raise ValueError("Wrong degree")

    # check for errors
    coincides = 0
    failures_detected = set()
    for j in range(n):
        if encoded[j] is None:
            continue
        if P(point(j)) == encoded[j]:
            coincides += 1
        else:
            failures_detected.add(j)

    if coincides >= 2 * t + 1:
        return P, failures_detected
    else:
        raise ValueError("Did not coincide")


async def robust_reconstruct(field_futures, field, n, t, point):
    # Wait for between 2t+1 values and N values,
    # trying to reconstruct each time
    assert 2*t < n, "Robust reconstruct waits for at least n=2t+1 values"
    for nAvailable in range(2*t + 1, n+1):
        try:
            await waitFor(field_futures, nAvailable)
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
