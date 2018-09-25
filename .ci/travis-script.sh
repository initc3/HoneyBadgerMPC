#!/bin/bash

BASE_CMD="docker-compose -f .travis.compose.yml run --rm test-hbmpc"

if [ "${BUILD}" == "tests" ]; then
    $BASE_CMD pytest -v --cov=honeybadgermpc --cov-report=term-missing --cov-report=xml
elif [ "${BUILD}" == "flake8" ]; then
    flake8 honeybadgermpc/
elif [ "${BUILD}" == "docs" ]; then
    sphinx-build -M html docs docs/_build -c docs -W
fi
