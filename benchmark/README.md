# How to benchmark?

* Add a file in this folder with the prefix `test_benchmark` in the name.
* Follow other benchmarks already written on how to write benchmark code. You can also refer to the [official documentation](https://pytest-benchmark.readthedocs.io/en/latest/).
* To run all benchmarks: `pytest -v benchmark`
* To run a single benchmark: `pytest -v benchmark -k <benchmark_method_name>`

## Disabling Benchmark Tests
It's possible to test only the logic of the benchmark tests with the
[`--benchmark-disable`](https://pytest-benchmark.readthedocs.io/en/latest/usage.html#commandline-options) option.

> Benchmarked functions are only ran once and no stats are reported.
> Use this if you want to run the test but don't do any benchmarking.

Example:

```shell
$ pytest -v --benchmark-disable benchmark/
```

## Reducing Parametrization
Many tests are parametrized such that the same logic will be executed
multiple times, for different parameter values. In order to allow for
only testing one set of parameter values, meaning running a particular
test only once, as opposed to running it multiple times with different
parameter values, the custom "boolean" `pytest` marker, `skip_bench` is
available. To set `skip_bench` to `True` use the option
`-m skip_bench`:

```shell
$ pytest -v -m skip_bench benchmark/
```

For instance, without `-m skip_bench`:

```shell
$ pytest -v benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft

benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[1]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[3]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[5]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[10]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[25]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[33]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[50]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[100]
benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[256]
```

and with `-m skip_bench`:

```shell
pytest -v -m skip_bench benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft

benchmark/test_benchmark_reed_solomon.py::test_benchmark_gao_robust_decode_fft[1]
```

## Logic Only Benchmark Tests Execution
To only check whether the benchmark tests actually run properly,
without benchmarking them and without testing for many sets of
paramter values, use both `--benchmark-disable` and `-m skip_bench`:

```shell
$ pytest -v --benchmark-disable -m skip_bench benchmark/
```
