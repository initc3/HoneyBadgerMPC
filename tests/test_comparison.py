from pytest import mark
from random import randint
from honeybadgermpc.field import GF
from honeybadgermpc.comparison import comparison
from honeybadgermpc.mpc import Subgroup
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply, BeaverMultiplyArrays, InvertShare, InvertShareArray, DivideShares,
    DivideShareArrays, Equality)

STANDARD_ARITHMETIC_MIXINS = [
    BeaverMultiply(),
    BeaverMultiplyArrays(),
    InvertShare(),
    InvertShareArray(),
    DivideShares(),
    DivideShareArrays(),
    Equality()
]

PREPROCESSING = ['rands', 'triples', 'zeros', 'cubes', 'bits']
n, t = 4, 1
k = 10000


@mark.asyncio
async def test_comparison(test_preprocessing, galois_field, test_runner):
    num_len = 3
    p = Subgroup.BLS12_381
    field = GF(p)
    to_generate = ['zeros', 'rands', 'triples', 'bits']
    for x in to_generate:
        test_preprocessing.generate(x, n, t, k=2000)

    ranges = [0, p//2**128, p//2**64, p//2**32, p//2**16, p]
    constants = []
    for m in range(len(ranges)-1):
        term = [randint(ranges[m], ranges[m+1]) for _ in range(num_len)]
        constants.append(term)

    async def _prog(context):
        for m in range(len(ranges)-1):
            arr1 = [test_preprocessing.elements.get_zero(context) +
                    field(constant) for constant in constants[m]]
            arr2 = [arr1[0], arr1[1] + field(3), arr1[2] - field(250)]
            arr_res = [True, False, True]

            for i in range(num_len):
                result = await comparison(context, arr1[i], arr2[i])
                result_open = await result.open()

                if result_open == 1:
                    assert not arr_res[i]
                else:
                    assert arr_res

    await test_runner(_prog, n, t, PREPROCESSING, k, STANDARD_ARITHMETIC_MIXINS)
