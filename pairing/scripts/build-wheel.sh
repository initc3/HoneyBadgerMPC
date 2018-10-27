#!/bin/bash
set -ex

curl https://sh.rustup.rs -sSf | sh -s -- --default-toolchain nightly-2018-10-24 -y
export PATH="$HOME/.cargo/bin:$PATH"

export PYBIN=/opt/python/cp37-cp37m/bin
export PYTHON_SYS_EXECUTABLE="$PYBIN/python"
"${PYBIN}/pip" install -U pip setuptools wheel setuptools-rust
"${PYBIN}/python" setup.py bdist_wheel

for whl in dist/*.whl; do
    auditwheel repair "$whl"
done
