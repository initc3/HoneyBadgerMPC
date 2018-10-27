#!/bin/bash

set -ev

pip install --upgrade pip

if [ "${BUILD}" == "tests" ]; then
    pip install --upgrade codecov
    docker-compose -f .travis.compose.yml build --no-cache test-hbmpc
elif [ "${BUILD}" == "flake8" ]; then
    pip install --upgrade flake8
elif [ "${BUILD}" == "docs" ]; then
    docker-compose -f .travis.compose.yml build --no-cache test-hbmpc
fi
