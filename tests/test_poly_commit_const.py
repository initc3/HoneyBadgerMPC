from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit_const import PolyCommitConst, gen_pc_const_crs


def test_pc_const():
    t = 3
    alpha = ZR.random()
    g = G1.rand()
    h = G1.rand()
    crs = gen_pc_const_crs(t, alpha=alpha, g=g, h=h)
    pc = PolyCommitConst(crs)
    phi = polynomials_over(ZR).random(t)
    c, phi_hat = pc.commit(phi)
    witness = pc.create_witness(phi, phi_hat, 3)
    assert c == g ** phi(alpha) * h ** phi_hat(alpha)
    assert pc.verify_eval(c, 3, phi(3), phi_hat(3), witness)
    assert not pc.verify_eval(c, 4, phi(3), phi_hat(3), witness)


def test_pc_const_preprocess():
    t = 2
    alpha = ZR.random()
    g = G1.rand()
    h = G1.rand()
    crs = gen_pc_const_crs(t, alpha=alpha, g=g, h=h)
    pc = PolyCommitConst(crs)
    pc.preprocess_prover()
    phi = polynomials_over(ZR).random(t)
    c, phi_hat = pc.commit(phi)
    witness = pc.create_witness(phi, phi_hat, 3)
    assert c == g ** phi(alpha) * h ** phi_hat(alpha)
    pc.preprocess_verifier()
    assert pc.verify_eval(c, 3, phi(3), phi_hat(3), witness)
    assert not pc.verify_eval(c, 4, phi(3), phi_hat(3), witness)
