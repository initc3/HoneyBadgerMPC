#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import os

from setuptools import setup, find_packages

NAME = 'honeybadgermpc'
DESCRIPTION = 'honeybadgermpc'
REQUIRES_PYTHON = '>=3.7.0'
VERSION = None

REQUIRED = [
    'gmpy2',
]

TESTS_REQUIRES = [
    'flake8',
    'pytest',
    'pytest-asyncio',
    'pytest-cov',
    'pytest-env',
]

DEV_REQUIRES = [
    'ipdb',
    'ipython',
]

DOCS_REQUIRE = [
    'Sphinx',
    'sphinx-autobuild',
    'sphinx_rtd_theme',
    'm2r',
]

ETH_REQUIRES = ['web3', 'ethereum']

EXTRAS = {
    'tests': TESTS_REQUIRES,
    'dev': DEV_REQUIRES + TESTS_REQUIRES + DOCS_REQUIRE,
    'docs': DOCS_REQUIRE,
    'eth': ETH_REQUIRES,
}

here = os.path.abspath(os.path.dirname(__file__))

try:
    with io.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = '\n' + f.read()
except FileNotFoundError:
    long_description = DESCRIPTION

about = {}
if not VERSION:
    with open(os.path.join(here, NAME, '__version__.py')) as f:
        exec(f.read(), about)
else:
    about['__version__'] = VERSION

setup(
    name=NAME,
    version=about['__version__'],
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    python_requires=REQUIRES_PYTHON,
    install_requires=REQUIRED,
    extras_require=EXTRAS,
    classifiers=[
        'Development Status :: 1 - Planning',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    packages=find_packages(),
)
