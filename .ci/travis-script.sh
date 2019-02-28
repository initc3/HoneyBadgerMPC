#!/bin/bash

set -ev

BASE_CMD="docker-compose -f .travis.compose.yml run --rm test-hbmpc"

if [ "${BUILD}" == "tests" ]; then
    # Run only hbmpc test cases present within the `tests` directory.
    $BASE_CMD pytest -v tests/ --cov=honeybadgermpc --cov-report=term-missing --cov-report=xml
elif [ "${BUILD}" == "flake8" ]; then
    flake8
elif [ "${BUILD}" == "docs" ]; then
    $BASE_CMD sphinx-build -M html docs docs/_build -c docs -W
    $BASE_CMD doc8 docs/
fi
