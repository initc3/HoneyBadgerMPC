from .mpc import PreProcessedElements, Subgroup
from .field import GF
from gmpy2 import num_digits


async def comparison(context, a_share, b_share):

    """MULTIPARTY COMPARISON - An Improved Multiparty Protocol for
    Comparison of Secret-shared Values by Tord Ingolf Reistad (2007)
    This method `greater_than_equal` method which can compare
    Zp field elements and gives a secret result shared over Zp.
    `greater_than_equal` method which can compare Zp field
    """

    pp_elements = PreProcessedElements()
    modulus = Subgroup.BLS12_381
    field = GF(modulus)
    num_len = num_digits(modulus, 2)

    async def get_random_bit():
        r = pp_elements.get_rand(context)
        r_square = await (r*r)
        r_sq = await r_square.open()

        if pow(r_sq, (modulus-1)//2) != field(1) or r_sq == 0:
            return await get_random_bit()

        root = r_sq.sqrt()
        return (~field(2)) * ((~root)*r + field(1))

    # assert 2 * a_share + 1 < modulus, "[a] < (p-1)/2 must hold"
    # assert 2 * b_share + 1 < modulus, "[b] < (p-1)/2 must hold"

    # ############# PART 1 ###############
    # First Transformation
    r_bits = [pp_elements.get_bit(context) for _ in range(num_len)]
    r_bigb = field(0)
    for i, b in enumerate(r_bits):
        r_bigb = r_bigb + (2**i) * b

    # assert 2**num_len < modulus

    z = a_share - b_share

    twoz0_open = int(await (2*z).open()) % 2
    a_open = int(await a_share.open())
    b_open = int(await b_share.open())
    assert (a_open < b_open) == (twoz0_open)

    c = await (2 * z + r_bigb).open()
    c_bits = [field(int(x)) for x in list('{0:0255b}'.format(c.value))]
    c_bits.reverse()
    r_0 = r_bits[0]
    c0 = c_bits[0]

    r_bigb_open = await r_bigb.open()
    r_0_open = int(r_bigb_open) % 2
    r_0_open2 = await r_0.open()
    assert r_0_open == r_0_open2
    rbgtc = int(r_bigb_open) > int(c)
    assert twoz0_open == (c0 ^ r_0_open ^ rbgtc)

    # ############# PART 2 ###############
    # Compute bigx
    bigx = field(0)
    for i in range(num_len-1):
        cr = field(0)
        for j in range(i+1, num_len):
            c_xor_r = r_bits[j] + c_bits[j] - field(2)*c_bits[j]*r_bits[j]
            cr = cr + c_xor_r
        cr_open = await cr.open()
        pp = pow(2, int(cr_open))
        bigx = bigx + (field(1) - c_bits[i]) * pp * r_bits[i]
    bigx = bigx + (field(1) - c_bits[num_len-1]) * r_bits[num_len-1]    # ???

    # ############# PART 3 ###############
    # Extracting LSB
    # TODO
    # assert bigx.v.value < sqrt(4 * modulus)

    s_bits = [pp_elements.get_bit(context) for _ in range(num_len)]

    s_0 = s_bits[0]
    s1 = s_bits[-1]        # [s_{num_len-1}]
    s2 = s_bits[-2]        # [s_{num_len-2}]
    s1s2 = await (s1*s2)

    s_bigb = field(0)
    for i, b in enumerate(s_bits):
        s_bigb = s_bigb + (2**i) * b

    # Compute d_hat for check
    # d_hat = s_hat + x
    s_hat_bits = s_bits[:-2]
    assert len(s_hat_bits) == len(s_bits) - 2
    s_hat_bigb = field(0)
    for i, b in enumerate(s_hat_bits):
        s_hat_bigb = s_hat_bigb + (2**i) * b

    d_hat = s_hat_bigb + bigx
    d_hat_open = await d_hat.open()
    import math
    # Condition from paper
    assert int(d_hat_open) < 2**(num_len-2) + math.sqrt(4 * modulus)

    d_hat_0_open = int(d_hat_open) % 2

    bigd = s_bigb + bigx
    d = await bigd.open()
    d0 = int(d) & 1

    # TODO
    # assert d > sqrt(4 * modulus)

    # d0 ^ (d < 2**{num_len-1})
    dxor1 = d0 ^ (d.value < 2**(num_len-1))
    # d0 ^ (d < 2**{num_len-1})
    dxor2 = d0 ^ (d.value < 2**(num_len-2))
    # d0 ^ (d < (2**{num_len-2} + 2**{num_len-1}))
    dxor12 = d0 ^ (d.value < (2**(num_len-1) + 2**(num_len-2)))

    d_0 = d0 * (field(1) + s1s2 - s1 - s2) \
        + dxor2 * (s2 - s1s2) \
        + dxor1 * (s1 - s1s2) \
        + dxor12 * s1s2

    # Check alternate way of computing d_hat_0
    d_0_open = await d_0.open()
    assert d_0_open == d_hat_0_open

    x_0 = s_0 + d_0 - 2 * (await (s_0 * d_0))    # [x0] = [s0] ^ [d0], equal to [r]B > c

    # Check alternate way of computing x0
    bigx_open = await bigx.open()
    bigx_0_open = int(bigx_open) % 2
    x_0_open = await x_0.open()
    assert x_0_open == bigx_0_open
    assert int(int(r_bigb_open) > int(c)) == int(x_0_open)

    r_0_open = await r_0.open()
    c0_xor_r0 = c0 + r_0 - 2*c0*r_0
    final_val = c0_xor_r0 + x_0 - 2 * (await (c0_xor_r0 * x_0))
    return final_val
