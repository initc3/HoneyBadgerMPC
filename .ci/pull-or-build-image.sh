#!/bin/bash

set -ev

if [ "$TRAVIS_REPO_SLUG" == "initc3/HoneyBadgerMPC" ]; then
    docker pull $IMAGE_TAG
else
    docker build -t $IMAGE_TAG --build-arg SETUP_EXTRAS=$SETUP_EXTRAS --target tests .
fi
