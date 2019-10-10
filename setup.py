#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

from setuptools import setup, find_packages
from setuptools.extension import Extension
from Cython.Build import cythonize

NAME = "honeybadgermpc"
DESCRIPTION = "honeybadgermpc"
REQUIRES_PYTHON = ">=3.7.0"
VERSION = None

REQUIRED = ["gmpy2", "zfec", "pycrypto", "cffi", "psutil", "pyzmq"]

TESTS_REQUIRES = [
    "flake8",
    "pep8-naming",
    "pytest",
    "pytest-asyncio",
    "pytest-mock",
    "pytest-cov",
    "pytest-env",
    "pytest-xdist",
    "pytest-benchmark",
    "pytest-benchmark[histogram]",
    "pyyaml",
]

DEV_REQUIRES = ["ipdb", "ipython"]

DOCS_REQUIRE = [
    "Sphinx",
    "sphinx-autobuild",
    "sphinx_rtd_theme",
    "sphinx_tabs",
    "m2r",
    "doc8",
]

ETH_REQUIRES = ["web3", "ethereum"]

AWS_REQUIRES = ["boto3", "paramiko"]

EXTRAS = {
    "tests": TESTS_REQUIRES,
    "dev": DEV_REQUIRES + TESTS_REQUIRES + DOCS_REQUIRE + ETH_REQUIRES,
    "docs": DOCS_REQUIRE + ETH_REQUIRES,
    "eth": ETH_REQUIRES,
    "aws": AWS_REQUIRES,
}

here = os.path.abspath(os.path.dirname(__file__))

try:
    with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
        long_description = f"\n{f.read()}"
except FileNotFoundError:
    long_description = DESCRIPTION

if not VERSION:
    g = {}

    # TODO: consolidate how we do this
    with open(os.path.join(here, NAME, "__version__.py")) as f:
        exec(f.read(), g)
        VERSION = g["__version__"]


extra_compile_args = ["-std=c++11", "-O3", "-pthread", "-fopenmp", "-march=native"]
extra_link_args = [
    "-std=c++11",
    "-O3",
    "-pthread",
    "-fopenmp",
    "-lntl",
    "-lgmp",
    "-lm",
    "-march=native",
]

extensions = [
    Extension(
        name="honeybadgermpc.ntl._hbmpc_ntl_helpers",
        sources=["honeybadgermpc/ntl/hbmpc_ntl_helpers.pyx"],
        language="c++",
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    )
]

setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=REQUIRES_PYTHON,
    setup_requires=["cffi>=1.0.0", "Cython"],
    install_requires=REQUIRED,
    cffi_modules=["apps/asynchromix/solver/solver_build.py:ffibuilder"],
    extras_require=EXTRAS,
    ext_modules=cythonize(extensions),
    classifiers=[
        "Development Status :: 1 - Planning",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
    packages=find_packages(),
)
