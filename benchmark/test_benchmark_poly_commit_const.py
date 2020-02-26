from pytest import mark
from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit_const import PolyCommitConst, gen_pc_const_crs


@mark.parametrize("t", [3, 10, 20, 33])
def test_benchmark_commit(benchmark, t):
    alpha = ZR.random()
    g = G1.rand()
    h = G1.rand()
    crs = gen_pc_const_crs(t, alpha=alpha, g=g, h=h)
    pc = PolyCommitConst(crs)
    phi = polynomials_over(ZR).random(t)
    benchmark(pc.commit, phi)


@mark.parametrize("t", [3, 10, 20, 33])
def test_benchmark_create_witness(benchmark, t):
    alpha = ZR.random()
    g = G1.rand()
    h = G1.rand()
    crs = gen_pc_const_crs(t, alpha=alpha, g=g, h=h)
    pc = PolyCommitConst(crs)
    phi = polynomials_over(ZR).random(t)
    c, phi_hat = pc.commit(phi)
    pc.preprocess_prover(10)
    i = ZR.random()
    benchmark(pc.create_witness, phi, phi_hat, i)
