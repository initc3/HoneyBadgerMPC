#!/bin/bash

set -ev

pip install --upgrade pip

if [ "${BUILD}" == "tests" ]; then
    pip install --upgrade codecov
    docker-compose -f .travis.compose.yml build test-hbmpc
elif [ "${BUILD}" == "black" ]; then
    pip install --upgrade black
elif [ "${BUILD}" == "flake8" ]; then
    pip install --upgrade flake8 pep8-naming
elif [ "${BUILD}" == "docs" ]; then
    docker-compose -f .travis.compose.yml build test-hbmpc
fi
