from pytest import mark
import pytest
import asyncio
from honeybadgermpc.batch_reconstruction import batch_reconstruct
from honeybadgermpc.field import GFElement
from honeybadgermpc.polynomial import EvalPoint


@pytest.fixture
def reconstruction_input(galois_field):
    n = 4
    t = 1
    fp = galois_field
    p = fp.modulus
    # x + 2, 3x + 4, 2x + 2
    secret_shares = [(3, 7, 4), (4, 10, 6), (5, 13, 8), (6, 16, 10)]
    expected = [2, 4, 2]

    return n, t, fp, p, secret_shares, expected


@pytest.fixture
def fft_reconstruction_input(galois_field):
    n = 4
    t = 1
    fp = galois_field
    p = fp.modulus
    point = EvalPoint(fp, n, use_omega_powers=True)
    omega = point.omega.value
    # x + 2, 3x + 4
    secret_shares = [
        (omega ** 0 + 2, 3 * omega ** 0 + 4),
        (omega ** 1 + 2, 3 * omega ** 1 + 4),
        (omega ** 2 + 2, 3 * omega ** 2 + 4),
        (omega ** 3 + 2, 3 * omega ** 3 + 4),
    ]
    secrets = [2, 4]
    return n, t, fp, p, omega, secret_shares, secrets


async def _get_reconstruction(
    test_router,
    secret_shares,
    n,
    t,
    fp,
    p,
    use_omega_powers,
    skip_list=(),
    error_list=(),
):
    """
    :param skip_list: Nodes to skip in reconstruction (Dont send/receive shares)
    :param error_list: Nodes to insert errors in
    :return: reconstructed shares
    """
    sends, recvs, _ = test_router(n)
    towait = []
    for i in range(n):
        if i in skip_list:
            continue
        if i in error_list:
            ss = [fp(0) for _ in secret_shares[i]]
        else:
            ss = tuple(map(fp, secret_shares[i]))
        towait.append(
            batch_reconstruct(
                ss, p, t, n, i, sends[i], recvs[i], use_omega_powers=use_omega_powers
            )
        )
    results = await asyncio.gather(*towait)
    return results


@mark.asyncio
async def test_reconstruction_no_errors(
    test_router, galois_field, reconstruction_input
):
    # Given
    n, t, fp, p, shared_secrets, secrets = reconstruction_input

    # When
    results = await _get_reconstruction(test_router, shared_secrets, n, t, fp, p, False)

    # Then
    for r in results:
        for elem in r:
            assert type(elem) is GFElement
        assert r == secrets


@mark.asyncio
async def test_reconstruction_with_errors(
    test_router, galois_field, reconstruction_input
):
    # Given
    n, t, fp, p, secret_shares, secrets = reconstruction_input

    # When
    results = await _get_reconstruction(
        test_router, secret_shares, n, t, fp, p, use_omega_powers=False, error_list=[1]
    )

    # Then
    for r in results:
        for elem in r:
            assert type(elem) is GFElement
        assert r == secrets


@mark.asyncio
async def test_reconstruction_timeout(test_router, galois_field, reconstruction_input):
    """Test if reconstruction times out if one node is skipped in reconstruction"""
    # Given
    n, t, fp, p, secret_shares, secrets = reconstruction_input

    # When
    with pytest.raises(asyncio.TimeoutError):
        task = _get_reconstruction(
            test_router,
            secret_shares,
            n,
            t,
            fp,
            p,
            False,
            error_list=[1],
            skip_list=[2],
        )
        await asyncio.wait_for(task, timeout=1)


@mark.asyncio
async def test_fft_reconstruction_no_errors(
    test_router, galois_field, fft_reconstruction_input
):
    # Given
    n, t, fp, p, omega, secret_shares, secrets = fft_reconstruction_input

    # When
    results = await _get_reconstruction(
        test_router, secret_shares, n, t, fp, p, use_omega_powers=True
    )

    # Then
    for r in results:
        for elem in r:
            assert type(elem) is GFElement
        assert r == secrets


@mark.asyncio
async def test_fft_reconstruction_with_errors(
    test_router, galois_field, fft_reconstruction_input
):
    # Given
    n, t, fp, p, omega, secret_shares, secrets = fft_reconstruction_input

    # When
    results = await _get_reconstruction(
        test_router, secret_shares, n, t, fp, p, use_omega_powers=True, error_list=[1]
    )

    # Then
    for r in results:
        for elem in r:
            assert type(elem) is GFElement
        assert r == secrets


@mark.asyncio
async def test_fft_reconstruction_timeout(
    test_router, galois_field, fft_reconstruction_input
):
    """Test if reconstruction times out if one node is skipped in reconstruction"""
    # Given
    n, t, fp, p, omega, secret_shares, secrets = fft_reconstruction_input

    # When
    with pytest.raises(asyncio.TimeoutError):
        task = _get_reconstruction(
            test_router,
            secret_shares,
            n,
            t,
            fp,
            p,
            use_omega_powers=True,
            error_list=[1],
            skip_list=[2],
        )
        await asyncio.wait_for(task, timeout=1)


# TODO: No erasure tests present
# TODO: Test graceful exit (throw some Error) when reconstruction fails
