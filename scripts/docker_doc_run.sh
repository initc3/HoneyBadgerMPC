#!/bin/bash

set -ev

SPHINX_BUILD_CMD="sphinx-build -M html docs docs/_build -c docs -W -v --keep-going"
IMAGE_TAG=latest

if [ "$TRAVIS_PULL_REQUEST" == "false" ]  || [ "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]; then
    IMAGE_TAG=$TRAVIS_COMMIT
fi
# docker run -it dsluiuc/honeybadger-prod:$TRAVIS_COMMIT $SPHINX_BUILD_CMD
#else 
# docker run -it dsluiuc/honeybadger-prod:latest $SPHINX_BUILD_CMD
#fi
 
docker run -it dsluiuc/honeybadger-prod:$IMAGE_TAG $SPHINX_BUILD_CMD
