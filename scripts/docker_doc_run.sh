#!/bin/bash

set -ev

SPHINX_BUILD_CMD=sphinx-build -M html docs docs/_build -c docs -W -v --keep-going

if [ "$TRAVIS_PULL_REQUEST" == "false" ]  || [ "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]; then
 docker run -it dsluiuc/honeybadger-prod:$TRAVIS_COMMIT $SPHINX_BUILD_CMD
else 
 docker run -it dsluiuc/honeybadger-prod:latest $SPHINX_BUILD_CMD
fi
