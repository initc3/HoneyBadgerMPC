"""
hbMPC tutorial 1. Running sample MPC programs in the testing simulator
"""
import asyncio
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.progs.mixins.dataflow import Share
from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.utils.typecheck import TypeCheck
from honeybadgermpc.progs.mixins.share_arithmetic import (
    MixinConstants,
    BeaverMultiply,
    BeaverMultiplyArrays,
)

config = {
    MixinConstants.MultiplyShareArray: BeaverMultiplyArrays(),
    MixinConstants.MultiplyShare: BeaverMultiply(),
}


@TypeCheck()
async def beaver_multiply(ctx, x: Share, y: Share):
    """The hello world of MPC: beaver multiplication
     - Linear operations on Share objects are easy
     - Shares of random values are available from preprocessing
     - Opening a Share returns a GFElementFuture
    """
    a, b, ab = ctx.preproc.get_triples(ctx)
    D = await (x - a).open()
    E = await (y - b).open()

    # D*E is multiplying GFElements
    # D*b, E*a are multiplying GFElement x Share -> Share
    # ab is a Share
    # overall the sum is a Share

    xy = (D * E) + (D * b) + (E * a) + ab
    return xy


async def random_permute_pair(ctx, x, y):
    """
    Randomly permute a pair of secret shared values.
    Input: `x`, `y` are `Share` objects
    Output: A pair of `Share` objects `(o1,o2)`, which are fresh
       shares that take on the value `(x,y)` or `(y,x)` with equal
       probability
    Preprocessing:
    - One random bit
    - One beaver multiplication
    """
    b = ctx.preproc.get_bit(ctx)
    # just a local scalar multiplication
    one_or_minus_one = ctx.field(2) * b - ctx.field(1)
    m = one_or_minus_one * (x - y)
    o1 = (x + y + m) * (1 / ctx.field(2))
    o2 = (x + y - m) * (1 / ctx.field(2))
    return (o1, o2)


# Working with arrays
def dot_product(ctx, x_shares, y_shares):
    """Although the above example of Beaver multiplication is perfectly valid,
    you can also just use the `*` operator of the Share object, which does
    the same thing.

    This is also an example of dataflow programming. The return value of this
    operation is a `ShareFuture`, which defines addition and multiplication
    operations as well (like in Viff). As a result, all of these multiplications
    can take place in parallel.
    """
    res = ctx.ShareFuture()
    res.set_result(ctx.Share(0))
    for x, y in zip(x_shares, y_shares):
        res += x * y
    return res


async def prog(ctx):
    # Test with random sharings of hardcoded values
    x = ctx.Share(5) + ctx.preproc.get_zero(ctx)
    y = ctx.Share(7) + ctx.preproc.get_zero(ctx)
    xy = await beaver_multiply(ctx, x, y)

    # Check openings of the multiplied values
    X = await x.open()
    Y = await y.open()
    XY = await xy.open()
    assert XY == X * Y
    print(f"[{ctx.myid}] Beaver Multiplication OK")
    # print(f'x:{y} y:{x}: xy:{xy}')
    # print(f'x.open(): {X} y.open(): {Y} xy.open(): {XY}')

    # Sample dot product (4 * 5 + 8 * 10) == 100
    # Each product of two Shares returns a ShareFuture
    a = ctx.Share(4) + ctx.preproc.get_zero(ctx)
    b = ctx.Share(8) + ctx.preproc.get_zero(ctx)
    c = ctx.Share(5) + ctx.preproc.get_zero(ctx)
    d = ctx.Share(10) + ctx.preproc.get_zero(ctx)
    res = dot_product(ctx, (a, b), (c, d))
    res_ = await res.open()
    assert res_ == res
    print(f"[{ctx.myid}] Dot Product OK")

    # Randomly permute (x,y) or (y,x)
    o1, o2 = await random_permute_pair(ctx, x, y)
    # Unless you open it, no one knows which permutation it is
    O1 = await o1.open()
    O2 = await o2.open()
    # print(f'O1:{O1} O2:{O2}')
    assert O1 in (X, Y) and O2 in (X, Y)
    print(f"[{ctx.myid}] Permute Pair OK")


async def tutorial_1():
    # Create a test network of 4 nodes (no sockets, just asyncio tasks)
    n, t = 4, 1
    pp = FakePreProcessedElements()
    pp.generate_zeros(100, n, t)
    pp.generate_triples(100, n, t)
    pp.generate_bits(100, n, t)
    program_runner = TaskProgramRunner(n, t, config)
    program_runner.add(prog)
    results = await program_runner.join()
    return results


def main():
    # Run the tutorials
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tutorial_1())
    # loop.run_until_complete(tutorial_2())


if __name__ == "__main__":
    main()
    print("Tutorial 1 ran successfully")
