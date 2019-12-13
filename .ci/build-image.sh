#!/bin/bash

set -ev

if [ -z $1 ]; then
    tag=$IMAGE_TAG
else
    tag=$1
fi

echo "Building image $tag"
docker build -t $tag --build-arg SETUP_EXTRAS=$SETUP_EXTRAS --target tests .
