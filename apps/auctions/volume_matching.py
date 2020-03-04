# Original code was written by Harjasleen Malvai

"""
In volume matching auction, buy and sell orders are matched only on volume
while price is determined by reference to some external market.
"""

import asyncio
import logging

from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.progs.fixedpoint import FixedPoint
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    MixinConstants,
)

config = {
    MixinConstants.MultiplyShareArray: BeaverMultiplyArrays(),
    MixinConstants.MultiplyShare: BeaverMultiply(),
}


async def compute_bids(ctx, balances, bids, price):
    """Compute all valid bids for each user.
    According to current market price, a bid becomes invalid
    if the user doesn't have enough balance to pay for this bid.
    We only keep valid bids and classify them into
    buy bids(volume > 0) and sell bids(volume < 0).
    Invalid bids will be discarded after executing this function.

    Parameters
    ----------
    balances : dict of dict
        Dictionary of the form: ``{address: {cointype: balance}}``.
        Address is a string representing
        the public address of the user.
        Cointype is a string.
        Now we only support two cointypes, 'eth' and 'erc20'.
        Balance is a FixedPoint number.
    bids : list of tuple
        A list of bids.
        Each bid is a tuple of two elements ``(address, volume)``,
        the address of the owner and the volume of this bid.
        Address is a string and volume is a FixedPoint number.
        When volume is larger than zero, this bid is a buy bid,
        which means the owner wants to buy 'volume' units of tokens
        with 'volume * price' units of ETH.
        When volume is less than zero, the bid is a sell bid,
        which means the owner wants to sell 'volume' units of tokens
        for 'volume * price' units of ETH.
    price : FixedPoint
        In volume matching, price is determined by reference
        to some external lit market. Price is how many units of ETH
        have the same value as one unit of token.

    Returns
    -------
    buys : list of tuple
        List of valid buy orders ``(address, volume)``.
    sells : list of tuple
        List of valid sell orders ``(address, volume)``.
        Since we have separated buy and sell bids,
        now every sell bid has volume larger than zero.
    """

    one = ctx.Share(1)
    zero = ctx.Share(0)
    fp_zero = FixedPoint(ctx, zero)

    used_balances = {}
    # TODO for key in balances:
    for key in balances.keys():
        used_balances[key] = {
            "eth": create_clear_share(ctx, 0),
            "erc20": create_clear_share(ctx, 0),
        }

    buys = []
    sells = []

    for bid in bids:
        addr, vol = bid

        is_sell = await vol.ltz()
        is_buy = one - is_sell

        sell_vol = fp_zero - FixedPoint(ctx, await (is_sell * vol.share))
        buy_vol = FixedPoint(ctx, await (is_buy * vol.share))

        is_sell_vol_valid = one - await balances[addr]["erc20"].lt(
            sell_vol + used_balances[addr]["erc20"]
        )
        is_buy_vol_valid = one - await balances[addr]["eth"].lt(
            (await buy_vol.__mul__(price)) + used_balances[addr]["eth"]
        )

        fp_is_sell_vol_valid = FixedPoint(ctx, is_sell_vol_valid * 2 ** 32)
        fp_is_buy_vol_valid = FixedPoint(ctx, is_buy_vol_valid * 2 ** 32)

        sell_vol = await fp_is_sell_vol_valid.__mul__(sell_vol)
        buy_vol = await fp_is_buy_vol_valid.__mul__(buy_vol)

        sells.append((addr, sell_vol))
        buys.append((addr, buy_vol))

        used_balances[addr]["erc20"] = used_balances[addr]["erc20"] + sell_vol
        used_balances[addr]["eth"] = used_balances[addr]["eth"] + (
            await buy_vol.__mul__(price)
        )

    return buys, sells


async def volume_matching(ctx, buys, sells):
    """Given all valid buy and sell bids,
    this function runs the volume matching algorithm,
    where buy and sell bids are matched only on volume
    with no price information considered.
    First we compute the total amount to be matched,
    i.e., the smaller one between total buy volume
    and total sell volume.
    Then we match for buy bids and sell bids respectively.
    After matching, each bid is split into matched and rest part.
    This function returns four lists of bids,
    where matched_buys + res_buys = buys and
    matched_sells + res_sells = sells.

    Parameters
    ----------
    buys : list of tuple
        List of valid buy orders. An order is a 2-tuple:
        ``(address, volume)``.
    sells : list of tuple
        List of valid sell orders. An order is a 2-tuple:
        ``(address, volume)``.

    Returns
    -------
    matched_buys : list of tuple
        The matched part of each buy orders.
    matched_sells : list of tuple
        The matched part of each sell orders.
    res_buys : list of tuple
        The unmatched part of each buy orders.
    res_sells : list of tuple
        The unmatched part of each sell orders.
    """

    zero = ctx.Share(0)
    fp_zero = FixedPoint(ctx, zero)

    # compute total amount of volume to be matched
    matched_buys, matched_sells = [], []
    res_buys, res_sells = [], []

    total_sells = fp_zero
    for sell in sells:
        total_sells = total_sells + sell[1]

    total_buys = fp_zero
    for buy in buys:
        total_buys = total_buys + buy[1]

    f = await total_buys.lt(total_sells)
    fp_f = FixedPoint(ctx, f * 2 ** 32)
    matching_volume = (await (total_buys - total_sells).__mul__(fp_f)) + total_sells

    # match for sell bids
    rest_volume = matching_volume
    for sell in sells:
        addr, sell_vol = sell

        z1 = await fp_zero.lt(rest_volume)
        fp_z1 = FixedPoint(ctx, z1 * 2 ** 32)
        z2 = await rest_volume.lt(sell_vol)
        fp_z2 = FixedPoint(ctx, z2 * 2 ** 32)

        matched_vol = await (
            (await (rest_volume - sell_vol).__mul__(fp_z2)) + sell_vol
        ).__mul__(fp_z1)
        rest_volume = rest_volume - matched_vol

        matched_sells.append([addr, matched_vol])
        res_sells.append([addr, sell_vol - matched_vol])

    # match for buy bids
    rest_volume = matching_volume
    for buy in buys:
        addr, buy_vol = buy

        z1 = await fp_zero.lt(rest_volume)
        fp_z1 = FixedPoint(ctx, z1 * 2 ** 32)
        z2 = await rest_volume.lt(buy_vol)
        fp_z2 = FixedPoint(ctx, z2 * 2 ** 32)

        matched_vol = await (
            (await (rest_volume - buy_vol).__mul__(fp_z2)) + buy_vol
        ).__mul__(fp_z1)
        rest_volume = rest_volume - matched_vol

        matched_buys.append([addr, matched_vol])
        res_buys.append([addr, buy_vol - matched_vol])

    return matched_buys, matched_sells, res_buys, res_sells


async def compute_new_balances(balances, matched_buys, matched_sells, price):
    """Update balances for each user after volume matching

    Parameters
    ----------
    balances : dict of dict
        Balances of users before matching.
        The dict is of the form: ``{address: {cointype: balance}}``,
        same as in the :func:`compute_bids` function.
    matched_buys : list of tuple
        List of matched buy bids.
    matched_sells : list of tuple
        List of matched sell bids.
    price: FixedPoint
        External market price

    Returns
    -------
    balances : dict of dict
        Updated balances after matching.
    """

    for sell in matched_sells:
        addr, vol = sell

        balances[addr]["erc20"] = balances[addr]["erc20"] - vol
        balances[addr]["eth"] = balances[addr]["eth"] + (await vol.__mul__(price))

    for buy in matched_buys:
        addr, vol = buy

        balances[addr]["eth"] = balances[addr]["eth"] - (await vol.__mul__(price))
        balances[addr]["erc20"] = balances[addr]["erc20"] + vol

    return balances


def create_secret_share(ctx, x):
    return FixedPoint(ctx, ctx.Share(x * 2 ** 32) + ctx.preproc.get_zero(ctx))


def create_clear_share(ctx, x):
    return FixedPoint(ctx, ctx.Share(x * 2 ** 32))


async def prog(ctx, *, balances=None, bids=None):
    price = create_clear_share(ctx, 3)

    balances = {
        addr: {
            coin: create_clear_share(ctx, balance) for coin, balance in wallet.items()
        }
        for addr, wallet in balances.items()
    }

    _balances = [
        (await x["eth"].open(), await x["erc20"].open()) for x in balances.values()
    ]
    logging.info(f"balances initial {_balances}")

    bids = [(addr, create_secret_share(ctx, bid)) for addr, bid in bids]
    buys, sells = await compute_bids(ctx, balances, bids, price)

    _buys = [await x[1].open() for x in buys]
    _sells = [await x[1].open() for x in sells]
    logging.info(f"buys initial: {_buys} and sells initial: {_sells}")

    matched_buys, matched_sells, res_buys, res_sells = await volume_matching(
        ctx, buys, sells
    )

    _matched_buys = [await x[1].open() for x in matched_buys]
    _matched_sells = [await x[1].open() for x in matched_sells]
    logging.info(f"buys matched: {_matched_buys} and sells matched: {_matched_sells}")

    _res_buys = [await x[1].open() for x in res_buys]
    _res_sells = [await x[1].open() for x in res_sells]
    logging.info(f"buys rest: {_res_buys} and sells rest: {_res_sells}")

    _balances = [
        (await x["eth"].open(), await x["erc20"].open()) for x in balances.values()
    ]
    logging.info(f"balances rest {_balances}")

    final_balances = await compute_new_balances(
        balances, matched_buys, matched_sells, price
    )

    _final_balances = [
        (await x["eth"].open(), await x["erc20"].open())
        for x in final_balances.values()
    ]
    logging.info(f"balances rest {_final_balances}")

    logging.info(f"[{ctx.myid}] done")


async def dark_pewl(*, balances=None, bids=None):
    n, t = 4, 1
    k = 10000
    pp = FakePreProcessedElements()
    pp.generate_zeros(k, n, t)
    pp.generate_triples(k, n, t)
    pp.generate_bits(k, n, t)
    program_runner = TaskProgramRunner(n, t, config)
    program_runner.add(prog, balances=balances, bids=bids)
    results = await program_runner.join()
    return results


def main(*, balances=None, bids=None):
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(dark_pewl(balances=balances, bids=bids))


if __name__ == "__main__":
    # import random

    addresses = tuple("0x1{i}" for i in range(32, 64))

    balances = {
        addresses[0]: {"eth": 15, "erc20": 1},
        addresses[1]: {"eth": 18, "erc20": 0},
        addresses[2]: {"eth": 2, "erc20": 3},
        addresses[3]: {"eth": 0, "erc20": 15},
    }
    # balances.update({addr: {"eth": 100, "erc20": 100} for addr in addresses[4:]})
    bids = [
        (addresses[0], 5),
        (addresses[1], 7),
        (addresses[2], -3),
        (addresses[3], -11),
    ]
    # bids.extend(((addr, random.randint(-10, 10)) for addr in addresses[4:]))

    main(balances=balances, bids=bids)
