import asyncio
import logging
from honeybadgermpc.exceptions import HoneyBadgerMPCError
from honeybadgermpc.polynomial import EvalPoint, polynomials_over
from honeybadgermpc.reed_solomon import Algorithm, EncoderFactory, DecoderFactory
from honeybadgermpc.batch_reconstruction import subscribe_recv, wrap_send


class HyperInvMessageType(object):
    SUCCESS = "S"
    ABORT = "A"


async def _recv_loop(n, recv, s=0):
    results = [None]*n
    for _ in range(n):
        sender_id, value = await recv()
        results[sender_id-s] = value
    return results


async def generate_double_shares(n, t, my_id, _send, _recv, field):
    poly = polynomials_over(field)
    eval_point, algorithm = EvalPoint(field, n, use_fft=True), Algorithm.FFT
    big_t = n - (2 * t) - 1  # This is same as `T` in the HyperMPC paper.
    encoder = EncoderFactory.get(eval_point, algorithm)

    # Pick a random element.
    my_random = field.random()
    coeffs_t = tuple(map(int, poly.random(t, my_random).coeffs))
    coeffs_2t = tuple(map(int, poly.random(2*t, my_random).coeffs))

    # Generate t and 2t shares of the random element.
    shares_to_send = (encoder.encode(coeffs_t), encoder.encode(coeffs_2t))

    subscribe_recv_task, subscribe = subscribe_recv(_recv)

    def _get_send_recv(tag):
        return wrap_send(tag, _send), subscribe(tag)

    # Start listening for my share of t and 2t shares from all parties.
    send, recv = _get_send_recv("H1")
    share_recv_task = asyncio.create_task(_recv_loop(n, recv))

    # Send each party their shares.
    for i in range(n):
        send(i, (shares_to_send[0][i], shares_to_send[1][i]))

    # Wait until all shares are received.
    received_shares = await share_recv_task
    unrefined_t_shares, unrefined_2t_shares = zip(*received_shares)

    # Apply the hyper-invertible matrix.
    # Assume the unrefined shares to be coefficients of a polynomial
    # and then evaluate that polynomial at powers of omega.
    refined_shares = (encoder.encode(unrefined_t_shares),
                      encoder.encode(unrefined_2t_shares))

    # Parties with id in [N-2t+1, N] need to start
    # listening for shares which they have to check.
    send, recv = _get_send_recv("H2")
    if my_id > big_t:
        share_chk_recv_task = asyncio.create_task(_recv_loop(n, recv))

    # Send shares of parties with id in [N-2t+1, N] to those parties.
    for i in range(big_t+1, n):
        send(i, (refined_shares[0][i], refined_shares[1][i]))

    # Parties with id in [N-2t+1, N] need to verify that the shares are in-fact correct.
    if my_id > big_t:
        shares_to_check = await share_chk_recv_task
        shares_t, shares_2t = zip(*shares_to_check)
        response = HyperInvMessageType.ABORT

        def get_degree_and_secret(shares):
            decoder = DecoderFactory.get(eval_point, algorithm)
            polynomial = poly(decoder.decode(list(range(n)), shares))
            return len(polynomial.coeffs)-1, polynomial(0)

        degree_t, secret_t = get_degree_and_secret(shares_t)
        degree_2t, secret_2t = get_degree_and_secret(shares_2t)
        # Verify that the shares are in-fact `t` and `2t` shared.
        # Verify that both `t` and `2t` shares of the same value.
        if degree_t == t and degree_2t == 2*t and secret_t == secret_2t:
            response = HyperInvMessageType.SUCCESS
        logging.debug("[%d] Degree check: %s, Secret Check: %s", my_id,
                      degree_t == t and degree_2t == 2*t, secret_t == secret_2t)

    # Start listening for the verification response.
    send, recv = _get_send_recv("H3")
    response_recv_task = asyncio.create_task(_recv_loop(n-big_t-1, recv, big_t+1))

    # Send the verification response.
    if my_id > big_t:
        for i in range(n):
            send(i, response)

    responses = await response_recv_task
    subscribe_recv_task.cancel()
    # If any of [T+1, N] parties say that the shares are inconsistent then abort.
    if responses.count(HyperInvMessageType.SUCCESS) != n-big_t-1:
        raise HoneyBadgerMPCError("Aborting because the shares were inconsistent.")

    return tuple(zip(refined_shares[0][:big_t+1], refined_shares[1][:big_t+1]))
