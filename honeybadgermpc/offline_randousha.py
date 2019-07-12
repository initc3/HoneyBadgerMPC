import time
import asyncio
import logging
from honeybadgermpc.config import HbmpcConfig
from honeybadgermpc.exceptions import HoneyBadgerMPCError
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.polynomial import EvalPoint, polynomials_over
from honeybadgermpc.reed_solomon import EncoderFactory, DecoderFactory
from honeybadgermpc.mpc import Mpc
from honeybadgermpc.ipc import ProcessProgramRunner
from honeybadgermpc.utils.misc import (
    wrap_send,
    transpose_lists,
    flatten_lists,
    subscribe_recv,
)


class HyperInvMessageType(object):
    SUCCESS = "S"
    ABORT = "A"


async def _recv_loop(n, recv, s=0):
    results = [None] * n
    for _ in range(n):
        sender_id, value = await recv()
        results[sender_id - s] = value
    return results


async def randousha(n, t, k, my_id, _send, _recv, field):
    """
    Generates a batch of (n-2t)k secret sharings of random elements
    """
    poly = polynomials_over(field)
    eval_point = EvalPoint(field, n, use_omega_powers=False)
    big_t = n - (2 * t) - 1  # This is same as `T` in the HyperMPC paper.
    encoder = EncoderFactory.get(eval_point)

    # Pick k random elements
    def to_int(coeffs):
        return tuple(map(int, coeffs))

    my_randoms = [field.random() for _ in range(k)]

    # Generate t and 2t shares of the random element.
    coeffs_t = [to_int(poly.random(t, r).coeffs) for r in my_randoms]
    coeffs_2t = [to_int(poly.random(2 * t, r).coeffs) for r in my_randoms]
    unref_t = encoder.encode(coeffs_t)
    unref_2t = encoder.encode(coeffs_2t)

    subscribe_recv_task, subscribe = subscribe_recv(_recv)

    def _get_send_recv(tag):
        return wrap_send(tag, _send), subscribe(tag)

    # Start listening for my share of t and 2t shares from all parties.
    send, recv = _get_send_recv("H1")
    share_recv_task = asyncio.create_task(_recv_loop(n, recv))

    # Send each party their shares.
    to_send_t = transpose_lists(unref_t)
    to_send_2t = transpose_lists(unref_2t)
    for i in range(n):
        send(i, (to_send_t[i], to_send_2t[i]))

    # Wait until all shares are received.
    received_shares = await share_recv_task
    unrefined_t_shares, unrefined_2t_shares = zip(*received_shares)

    # Apply the hyper-invertible matrix.
    # Assume the unrefined shares to be coefficients of a polynomial
    # and then evaluate that polynomial at powers of omega.
    ref_t = encoder.encode(transpose_lists(list(unrefined_t_shares)))
    ref_2t = encoder.encode(transpose_lists(list(unrefined_2t_shares)))

    # Parties with id in [N-2t+1, N] need to start
    # listening for shares which they have to check.
    send, recv = _get_send_recv("H2")
    to_send_t = transpose_lists(ref_t)
    to_send_2t = transpose_lists(ref_2t)

    if my_id > big_t:
        share_chk_recv_task = asyncio.create_task(_recv_loop(n, recv))

    # Send shares of parties with id in [N-2t+1, N] to those parties.
    for i in range(big_t + 1, n):
        send(i, (to_send_t[i], to_send_2t[i]))

    # Parties with id in [N-2t+1, N] need to verify that the shares are in-fact correct.
    if my_id > big_t:
        shares_to_check = await share_chk_recv_task
        shares_t, shares_2t = zip(*shares_to_check)
        response = HyperInvMessageType.ABORT

        def get_degree(p):
            for i in range(len(p))[::-1]:
                if p[i] != 0:
                    return i
            return 0

        def get_degree_and_secret(shares):
            decoder = DecoderFactory.get(eval_point)
            polys = decoder.decode(list(range(n)), transpose_lists(list(shares)))
            secrets = [p[0] for p in polys]
            degrees = [get_degree(p) for p in polys]
            return degrees, secrets

        degree_t, secret_t = get_degree_and_secret(shares_t)
        degree_2t, secret_2t = get_degree_and_secret(shares_2t)

        # Verify that the shares are in-fact `t` and `2t` shared.
        # Verify that both `t` and `2t` shares of the same value.
        if (
            all(deg == t for deg in degree_t)
            and all(deg == 2 * t for deg in degree_2t)
            and secret_t == secret_2t
        ):
            response = HyperInvMessageType.SUCCESS

        logging.debug(
            "[%d] Degree check: %s, Secret Check: %s",
            my_id,
            all(deg == t for deg in degree_t)
            and all(deg == 2 * t for deg in degree_2t),
            secret_t == secret_2t,
        )

    # Start listening for the verification response.
    send, recv = _get_send_recv("H3")
    response_recv_task = asyncio.create_task(_recv_loop(n - big_t - 1, recv, big_t + 1))

    # Send the verification response.
    if my_id > big_t:
        for i in range(n):
            send(i, response)

    responses = await response_recv_task
    subscribe_recv_task.cancel()

    # If any of [T+1, N] parties say that the shares are inconsistent then abort.
    if responses.count(HyperInvMessageType.SUCCESS) != n - big_t - 1:
        raise HoneyBadgerMPCError("Aborting because the shares were inconsistent.")

    out_t = flatten_lists([s[: big_t + 1] for s in ref_t])
    out_2t = flatten_lists([s[: big_t + 1] for s in ref_2t])

    return tuple(zip(out_t, out_2t))


async def generate_triples(n, t, k, my_id, _send, _recv, field):
    subscribe_recv_task, subscribe = subscribe_recv(_recv)

    def _get_send_recv(tag):
        return wrap_send(tag, _send), subscribe(tag)

    # Start listening for my share of t and 2t shares from all parties.
    send, recv = _get_send_recv("randousha")
    rs_t2t = await randousha(n, t, 3 * k, my_id, send, recv, field)

    as_t2t = rs_t2t[0 * k : 1 * k]
    bs_t2t = rs_t2t[1 * k : 2 * k]
    rs_t2t = rs_t2t[2 * k : 3 * k]

    as_t, _ = zip(*as_t2t)
    bs_t, _ = zip(*bs_t2t)
    as_t = list(map(field, as_t))
    bs_t = list(map(field, bs_t))
    rs_t, rs_2t = zip(*rs_t2t)

    # Compute degree reduction to get triples
    # TODO: Use the mixins and preprocessing system
    async def prog(ctx):
        assert len(rs_2t) == len(rs_t) == len(as_t) == len(bs_t)

        abrs_2t = [a * b + r for a, b, r in zip(as_t, bs_t, rs_2t)]
        abrs = await ctx.ShareArray(abrs_2t, 2 * t).open()
        abs_t = [abr - r for abr, r in zip(abrs, rs_t)]
        return list(zip(as_t, bs_t, abs_t))

    # TODO: compute triples through degree reduction
    send, recv = _get_send_recv("opening")
    ctx = Mpc(f"mpc:opening", n, t, my_id, send, recv, prog, {})

    result = await ctx._run()
    subscribe_recv_task.cancel()

    return result


async def generate_bits(n, t, k, my_id, _send, _recv, field):
    subscribe_recv_task, subscribe = subscribe_recv(_recv)

    def _get_send_recv(tag):
        return wrap_send(tag, _send), subscribe(tag)

    # Start listening for my share of t and 2t shares from all parties.
    send, recv = _get_send_recv("randousha")
    rs_t2t = await randousha(n, t, 2 * k, my_id, send, recv, field)

    # To generate bits, we generate a batch of `t,2t` sharings of
    # [u]_t, [u]_2t, [r]_t, [r]_2t. The goal is to recontruct `u^2`
    # so we can return `[u]/sqrt(u^2)`. The [r] sharings are used
    # for publicly reconstructing:
    #    u^2 = open([u]_t * [u]_t + [r]_2t) - [r]_t
    us_t2t = rs_t2t[0:k]
    rs_t2t = rs_t2t[k : 2 * k]

    us_t, _ = zip(*us_t2t)
    us_t = list(map(field, us_t))
    rs_t, rs_2t = zip(*rs_t2t)

    # Compute degree reduction to get the bit
    async def prog(ctx):
        u2rs_2t = [u * u + r for u, r in zip(us_t, rs_2t)]
        assert len(u2rs_2t) == len(rs_t)
        u2rs = await ctx.ShareArray(u2rs_2t, 2 * t).open()
        u2s_t = [u2r - r for u2r, r in zip(u2rs, rs_t)]
        u2s = await ctx.ShareArray(u2s_t).open()
        bits = [u / u2.sqrt() for u, u2 in zip(us_t, u2s)]
        return bits

    # TODO: compute triples through degree reduction
    send, recv = _get_send_recv("opening")
    ctx = Mpc(f"mpc:opening", n, t, my_id, send, recv, prog, {})
    result = await ctx._run()
    # print(f'[{my_id}] Generate triples complete')
    subscribe_recv_task.cancel()
    return result


########################
# Process runner
########################


async def _run(peers, n, t, k, my_id):
    field = GF(Subgroup.BLS12_381)
    async with ProcessProgramRunner(peers, n, t, my_id) as runner:
        send, recv = runner.get_send_recv("0")
        start_time = time.time()
        await randousha(n, t, k, my_id, send, recv, field)
        end_time = time.time()
        logging.info("[%d] Finished in %s", my_id, end_time - start_time)


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        _run(
            HbmpcConfig.peers,
            HbmpcConfig.N,
            HbmpcConfig.t,
            HbmpcConfig.extras["k"],
            HbmpcConfig.my_id,
        )
    )
