import logging
import random

from pytest import mark

from apps.auctions.volume_matching import (
    compute_bids,
    compute_new_balances,
    create_clear_share,
    create_secret_share,
    volume_matching,
)

from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
)

STANDARD_ARITHMETIC_MIXINS = [BeaverMultiplyArrays(), BeaverMultiply()]

PREPROCESSING = ["triples", "zeros", "bits"]
n, t = 3, 1
k = 10000


@mark.asyncio
async def test_volume_matching(test_preprocessing, test_runner):
    async def _prog(ctx):
        ctx.preproc = FakePreProcessedElements()

        bids = []
        for i in range(num_bids):
            bids.append([_bids[i][0], create_secret_share(ctx, _bids[i][1])])

        balances = {}
        for addr in addrs:
            balances[addr] = {
                "eth": create_clear_share(ctx, bal[addr][0]),
                "erc20": create_clear_share(ctx, bal[addr][1]),
            }

        _balances = {}
        for key, x in balances.items():
            _balances[key] = [await x["eth"].open(), await x["erc20"].open()]
        logging.info(f"balances {_balances}")

        price = create_clear_share(ctx, p)

        buys, sells = await compute_bids(ctx, balances, bids, price)

        _buys = [await x[1].open() for x in buys]
        _sells = [await x[1].open() for x in sells]
        logging.info(f"buys initial: {_buys} and sells initial: {_sells}")

        for i in range(num_bids):
            assert _buys[i] == b[i]
            assert _sells[i] == s[i]

        matched_buys, matched_sells, res_buys, res_sells = await volume_matching(
            ctx, buys, sells
        )

        _matched_buys = [await x[1].open() for x in matched_buys]
        _matched_sells = [await x[1].open() for x in matched_sells]
        logging.info(
            f"buys matched: {_matched_buys} and sells matched: {_matched_sells}"
        )

        _res_buys = [await x[1].open() for x in res_buys]
        _res_sells = [await x[1].open() for x in res_sells]
        logging.info(f"buys rest: {_res_buys} and sells rest: {_res_sells}")

        for i in range(num_bids):
            assert _matched_buys[i] + _res_buys[i] == _buys[i]
            assert _matched_sells[i] + _res_sells[i] == _sells[i]
            assert _matched_buys[i] == m_buy[i]
            assert _matched_sells[i] == m_sell[i]

        res_balances = await compute_new_balances(
            balances, matched_buys, matched_sells, price
        )

        _res_balances = {}
        for key, x in res_balances.items():
            _res_balances[key] = [await x["eth"].open(), await x["erc20"].open()]
        logging.info(f"balances rest {_res_balances}")

        for addr in addrs:
            assert final_balances[addr] == _res_balances[addr]

    # random sample price, users addresses, initial balances and bids
    p = random.randint(1, 3)
    logging.info(f"_price: {p}")

    num_addrs = random.randint(1, 2)
    logging.info(f"num_addrs: {num_addrs}")

    addrs = []
    bal = {}
    for i in range(num_addrs):
        addrs.append(f"0x{i + 120}")
        bal[addrs[i]] = [random.randint(10, 40) * p, random.randint(10, 40)]
    logging.info(f"addrs: {addrs}")
    logging.info(f"bal: {bal}")

    num_bids = random.randint(2, 3)
    logging.info(f"number of bids: {num_bids}")
    _bids = []
    for i in range(num_bids):
        _bids.append([addrs[random.randint(1, num_addrs) - 1], random.randint(-30, 30)])
    logging.info(f"_bids: {_bids}")

    # compute valid buy bids b and sell bids s
    sum_buy = 0
    sum_sell = 0
    b = []
    s = []
    used_balances = {}
    for addr in addrs:
        used_balances[addr] = [0, 0]

    for i in range(num_bids):
        b.append(0)
        s.append(0)

        addr, vol = _bids[i]
        if vol > 0:  # buy
            if vol * p + used_balances[addr][0] <= bal[addr][0]:
                b[i] = vol
                used_balances[addr][0] += vol * p
                sum_buy += vol
        else:  # sell
            if used_balances[addr][1] - vol <= bal[addr][1]:
                s[i] = -vol
                used_balances[addr][1] -= vol
                sum_sell -= vol
    logging.info(f"b: {b}")
    logging.info(f"s: {s}")

    # compute matched buy bids m_buy and matched sell bids m_sell
    matched = min(sum_sell, sum_buy)
    m_buy = []
    for i in range(num_bids):
        vol = min(matched, b[i])
        m_buy.append(vol)
        matched -= vol
    matched = min(sum_sell, sum_buy)
    m_sell = []
    for i in range(num_bids):
        vol = min(matched, s[i])
        m_sell.append(vol)
        matched -= vol
    logging.info(f"matched buy: {m_buy}\nmatched sell: {m_sell}")

    # compute balances after matching final_balances
    sum_eth = 0
    sum_erc = 0
    for addr in addrs:
        sum_eth += bal[addr][0]
        sum_erc += bal[addr][1]
    logging.info(f"sum eth: {sum_eth} sum erc: {sum_erc}")

    final_balances = {}
    for addr in addrs:
        final_balances[addr] = [bal[addr][0], bal[addr][1]]
    for i in range(num_bids):
        addr = _bids[i][0]
        final_balances[addr][0] -= p * m_buy[i]
        final_balances[addr][1] += m_buy[i]

        final_balances[addr][1] -= m_sell[i]
        final_balances[addr][0] += p * m_sell[i]
    logging.info(f"final balances: {final_balances}")

    await test_runner(_prog, n, t, PREPROCESSING, k, STANDARD_ARITHMETIC_MIXINS)
