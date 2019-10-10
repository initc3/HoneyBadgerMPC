from pytest import mark
from honeybadgermpc.betterpairing import ZR
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit_log import PolyCommitLog


@mark.parametrize("t", [3, 10, 20, 33])
def test_benchmark_commit(benchmark, t):
    pc = PolyCommitLog(degree_max=t)
    r = ZR.random()
    phi = polynomials_over(ZR).random(t)
    benchmark(pc.commit, phi, r)


@mark.parametrize("t", [3, 10, 20, 33])
def test_benchmark_create_witness(benchmark, t):
    pc = PolyCommitLog(degree_max=t)
    r = ZR.random()
    phi = polynomials_over(ZR).random(t)
    benchmark(pc.create_witness, phi, r, 3)


@mark.parametrize("t", [3, 10, 20, 33])
def test_benchmark_create_batch_witness(benchmark, t):
    pc = PolyCommitLog(degree_max=t)
    r = ZR.random()
    phi = polynomials_over(ZR).random(t)
    pc.preprocess_prover()
    benchmark(pc.batch_create_witness, phi, r, n=3*t+1)
