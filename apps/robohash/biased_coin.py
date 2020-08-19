import asyncio
import logging

from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.progs.mixins.share_arithmetic import MixinConstants, BeaverMultiply
from honeybadgermpc.progs.mixins.dataflow import Share

from honeybadgermpc.progs import fixedpoint

config = {
    MixinConstants.MultiplyShare: BeaverMultiply(),
}

# Fixing the fixed point paramters
fixedpoint.F = 8
fixedpoint.KAPPA = 8
fixedpoint.K = 16


def convert_integer_ss_to_fixed_point_ss(ctx, integer_ss):
    logging.info(
        f"convert secret share int {integer_ss} (type: {type(integer_ss)}) to secret share fixed point ..."
    )
    if not isinstance(integer_ss, Share):
        logging.info(f"cast {integer_ss} into a Share")
        integer_ss = ctx.Share(integer_ss)

    scaled_integer_ss = integer_ss * 2 ** fixedpoint.F

    logging.info(f"scaled secret share int: {scaled_integer_ss}")
    # if not isinstance(scaled_integer_ss, Share):
    #   scaled_integer_ss = ctx.Share(int(scaled_integer_ss * 2 ** fixedpoint.F))

    return fixedpoint.FixedPoint(ctx, scaled_integer_ss)


# Assumption - weight is a 8 bit value
async def flip_biased_coin(ctx, weight):
    logging.info(f"starting biased coin flip for weight: {weight}")

    bits = 8

    # Setting normalizing factor to 1/2^bits and converting it to Fixedpoint
    # representation
    normalizing_factor = fixedpoint.FixedPoint(
        ctx, ctx.Share(int(2 ** fixedpoint.F / 2 ** bits))
    )
    logging.info(f"normalizing factor: {normalizing_factor}")

    # Normalizing weight to a real value in [0, 1] by multiplying
    # with the normalizing factor
    normalized_weight = await convert_integer_ss_to_fixed_point_ss(ctx, weight).__mul__(
        normalizing_factor
    )
    logging.info(f"normalized weight: {normalized_weight}")

    # Flipping a 8 bit fair coin
    coin = ctx.Share(0)

    logging.info(f"8 bit fair coin: {coin}")

    for i in range(bits):
        coin += 2 ** i * ctx.preproc.get_bit(ctx)
        logging.info(f"8 bit fair coin: {coin}")

    # Normalizing coin value to a real value in [0, 1] by
    # multiplying with the normalizing factor
    fp_coin = convert_integer_ss_to_fixed_point_ss(ctx, coin)
    logging.info(f"fixed point coin to normalize: {fp_coin}")

    normalized_coin = await fp_coin.__mul__(normalizing_factor)
    logging.info(f"normalized coin: {normalized_coin}")
    logging.info(f"normalized weight: {normalized_weight}")

    result = await normalized_coin.lt(normalized_weight)

    return result
    # return coin


# Assumption - secret_param_1, secret_param_2 will be instantiated using
# some mom's and dad's gene attribute respectively
async def flip_biased_coin_2(ctx, secret_param_1, secret_param_2):

    logging.info(f"sec param 1: {secret_param_1}")
    logging.info(f"sec param 1 type: {type(secret_param_1)}")
    logging.info(f"sec param 2: {secret_param_2}")
    logging.info(f"sec param 2 type: {type(secret_param_2)}")

    # Flipping a biased coin based o 1st secret param
    coin1 = await flip_biased_coin(ctx, secret_param_1)
    logging.info(f"coin 1: {coin1}")

    # Flipping a biased coin based on 2nd secret param
    coin2 = await flip_biased_coin(ctx, secret_param_2)
    logging.info(f"coin 2: {coin2}")

    # Xoring both biased coins to get the final biased coin
    final_coin = await ((ctx.Share(1) - coin1) * coin2 + coin1 * (ctx.Share(1) - coin2))
    logging.info(f"final coin: {final_coin}")

    return final_coin


async def prog(ctx):

    # Number of biased coins that need to be flipped
    N = 11

    # Intializing Dad's and Mom's secret gene as some arbitrary numbers
    dad = 153
    mom = 221

    res = ""

    for i in range(N):

        # Secret share of Dad's and Mom's gene
        dad_ss = ctx.Share(dad)
        mom_ss = ctx.Share(mom)

        # Flipping a biased coin whose secret parameters depend on parent genes
        coin_ss = await flip_biased_coin_2(ctx, dad_ss, mom_ss)

        # Opening the output
        coin = await coin_ss.open()

        print(f"[{ctx.myid}] Biased coin {i}: {coin}")

        if coin == 0:
            res += "D"
        else:
            res += "M"

    print("Result = ", res)


async def test_flip_biased_coin():
    # Create a test network of 4 nodes (no sockets, just asyncio tasks)
    n, t = 4, 1
    pp = FakePreProcessedElements()
    pp.generate_triples(1500, n, t)
    pp.generate_bits(3000, n, t)
    program_runner = TaskProgramRunner(n, t, config)
    program_runner.add(prog)
    results = await program_runner.join()
    return results


def main():
    # Run the tutorials
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_flip_biased_coin())


if __name__ == "__main__":
    main()
    print("Tutorial 1 ran successfully")
