from pytest import mark
from random import randint
from honeybadgermpc.polynomial import get_omega
from honeybadgermpc.ntl.helpers import lagrange_interpolate, fft_interpolate

cache = {}


def get_points(n, galois_field):
    if n in cache:
        return cache[n]
    x = list(range(1, n + 1))
    y = [randint(0, galois_field.modulus - 1) for i in range(1, n + 1)]
    points = list(zip(x, y))
    omega = get_omega(galois_field, n, 1)
    cache[n] = x, y, points, omega
    return x, y, points, omega


@mark.parametrize("n", [2 ** i for i in range(4, 11, 2)])
def test_benchmark_lagrange_interpolate_python(benchmark, n, galois_field, polynomial):
    _, _, points, _ = get_points(n, galois_field)
    benchmark(polynomial.interpolate, points)


@mark.parametrize("n", [2 ** i for i in range(4, 11, 2)])
def test_benchmark_lagrange_interpolate_cpp(benchmark, n, galois_field):
    x, y, _, _ = get_points(n, galois_field)
    p = galois_field.modulus
    benchmark(lagrange_interpolate, x, y, p)


@mark.parametrize("n", [2 ** i for i in range(4, 21, 4)])
def test_benchmark_fft_interpolate_python(benchmark, n, galois_field, polynomial):
    _, y, _, omega = get_points(n, galois_field)
    benchmark(polynomial.interpolate_fft, y, omega)


@mark.parametrize("n", [2 ** i for i in range(4, 21, 4)])
def test_benchmark_fft_interpolate_cpp(benchmark, n, galois_field, polynomial):
    _, y, _, omega = get_points(n, galois_field)
    n = len(y)
    omega = omega.value
    p = galois_field.modulus
    z = list(range(n))
    benchmark(fft_interpolate, z, y, omega, p, n)
