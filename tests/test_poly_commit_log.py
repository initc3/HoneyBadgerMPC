from pytest import mark
from honeybadgermpc.betterpairing import ZR, G1
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit_log import PolyCommitLog

@mark.parametrize("t", [3, 6, 10])
def test_pc_log(t):
    pc = PolyCommitLog()
    phi = polynomials_over(ZR).random(t)
    # ToDo: see if other polycommits return the commit randomness
    # rather than expecting it as arg
    r = ZR.random()
    c = pc.commit(phi, r)
    witness = pc.create_witness(phi, r, 3)
    assert pc.verify_eval(c, 3, phi(3), witness)
    assert not pc.verify_eval(c, 4, phi(3), witness)
    assert not pc.verify_eval(G1.rand(), 3, phi(3), witness)

@mark.parametrize("t", [3, 6, 10])
def test_pc_log_batch(t):
    pc = PolyCommitLog()
    phi = polynomials_over(ZR).random(t)
    r = ZR.random()
    c = pc.commit(phi, r)
    witnesses = pc.batch_create_witness(phi, r)
    assert pc.verify_eval(c, 4, phi(4), witnesses[3])
