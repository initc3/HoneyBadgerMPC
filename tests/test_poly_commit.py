from honeybadgermpc.poly_commit import PolyCommit
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.betterpairing import G1, ZR
from random import randint


def test_poly_commit():
    poly_commit = PolyCommit(G1.rand(), G1.rand())
    degree = randint(10, 50)
    phi = polynomials_over(ZR).random(degree)
    cs, aux = poly_commit.commit(phi)
    i = randint(0, degree-1)
    witness = poly_commit.create_witness(aux, i)
    assert poly_commit.verify_eval(cs, i, phi(i), witness)
