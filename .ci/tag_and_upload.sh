#!/bin/bash
# Script to fetch, tag, and upload images to dockerhub. 
# This should only be ran on push builds

set -ev

# We tag the images to upload with the current branch name
# If we are on dev, then we also tag latest
if [[ "$TRAVIS_BRANCH" == "dev" ]]; then
    UPLOAD_TAGS="$TRAVIS_BRANCH latest"
else
    UPLOAD_TAGS=$TRAVIS_BRANCH
fi

# Log in to docker
docker login -u $DOCKER_USER -p $DOCKER_PASS

# Pull images for the current commit
./scripts/stager.py -vv pull -t prod -b $TRAVIS_COMMIT

# Tag the images
./scripts/stager.py -vv tag -t prod -b $UPLOAD_TAGS -s $TRAVIS_COMMIT

# Upload the tagged images to dockerhub
scripts/stager.py -vv push -t prod -b $UPLOAD_TAGS
