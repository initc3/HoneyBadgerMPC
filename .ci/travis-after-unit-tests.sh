#!/bin/bash
# Script that runs after unit tests have run. This copies the coverage.xml file
# from the docker image used for tests and uploads the report
# Then, it tags and uploads all of the docker images to dockerhub with the branch name
# When processing the travis run for merging into dev, push with the latest tag.

set -ev

# Don't run this on unit tests-- only pushes
if [[ "$TRAVIS_PULL_REQUEST" == "false" ]]; then
    # Log in to docker
    docker login -u $DOCKER_USER -p $DOCKER_PASS

    # We need to tag the images to upload with the current branch name
    ./scripts/stager.py tag -t prod -b $TRAVIS_BRANCH -s $TRAVIS_COMMIT

    # We then need to upload the images to dockerhub
    ./scripts/stager.py push -t prod -b $TRAVIS_BRANCH
    
    # Add the latest tag as well if we're on dev
    if [[ "$TRAVIS_BRANCH" == "dev" ]]; then
        ./scripts/stager.py tag -t prod -s $TRAVIS_BRANCH
        scripts/stager.py push -t prod 
    fi
fi