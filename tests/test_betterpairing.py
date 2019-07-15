def test_zr_math():
    from honeybadgermpc.betterpairing import ZR

    assert ZR("2") ** 3 == 8
    assert ZR(200) / 10 == ZR(20)
    assert 4 + ZR(14) == 18
    assert ZR("0xa") - ZR(4) == 6
    a = ZR.random()
    assert a ** -3 * a ** -5 == a ** -8
    assert (a ** -1) * a == a ** 0
    assert a ** 0 == 1


def test_bilinear_math():
    from honeybadgermpc.betterpairing import ZR, G1, G2, GT, pair

    a = G1.rand()
    b = G2.rand()
    c = pair(a, b)
    i = ZR.random()
    assert pair(a ** i, b) == c ** i
    assert pair(a, b ** i) == c ** i
    assert pair(a ** i, b ** i) == c ** (i ** 2)
    a.preprocess()
    b.preprocess(3)
    c.preprocess(5)
    i = ZR.random()
    assert pair(a ** i, b) == c ** i
    assert pair(a, b ** i) == c ** i
    assert pair(a ** i, b ** i) == c ** (i ** 2)
    a **= ZR.random()
    b **= ZR.random()
    c **= ZR.random()
    a2 = G1.rand()
    assert a / a2 == a * a2 ** -1
    b2 = G2.rand()
    assert b / b2 == b * b2 ** -1
    c2 = GT.rand()
    assert c / c2 == c * c2 ** -1
    assert (a ** -1) ** -1 == a
    assert (b ** -1) ** -1 == b
    assert (c ** -1) ** -1 == c


def test_serialization():
    from honeybadgermpc.betterpairing import ZR, G1, G2, GT

    a = ZR.random()
    b = G1.rand()
    c = G2.rand()
    d = GT.rand()
    assert a == ZR(a.__getstate__())
    # assert b == G1(b.__getstate__())
    assert c == G2(c.__getstate__())
    assert d == GT(d.__getstate__())

    bb = G1()
    bb.__setstate__(b.__getstate__())
    assert bb == b
