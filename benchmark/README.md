# How to benchmark?

* Add a file in this folder with the prefix `test_benchmark` in the name.
* Follow other benchmarks already written on how to write benchmark code. You can also refer to the [official documentation](https://pytest-benchmark.readthedocs.io/en/latest/).
* To run all benchmarks: `pytest -v benchmark`
* To run a single benchmark: `pytest -v benchmark -k <benchmark_method_name>`