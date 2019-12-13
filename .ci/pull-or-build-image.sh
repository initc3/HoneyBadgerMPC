#!/bin/bash

set -ev

if [ -z $1 ]; then
    tag=$IMAGE_TAG
else
    tag=$1
fi

echo "TRAVIS_EVENT_TYPE is: $TRAVIS_EVENT_TYPE"
echo "TRAVIS_REPO_SLUG is: $TRAVIS_REPO_SLUG"
echo "TRAVIS_PULL_REQUEST_SLUG is: $TRAVIS_PULL_REQUEST_SLUG"

if [[ "$TRAVIS_EVENT_TYPE" == "push" && "$TRAVIS_REPO_SLUG" == "initc3/HoneyBadgerMPC" || "$TRAVIS_EVENT_TYPE" == "pull_request" && "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]]; then
    . .ci/pull-image.sh $tag
else
    . .ci/build-image.sh $tag
fi
