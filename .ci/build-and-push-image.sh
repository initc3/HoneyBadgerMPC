#!/bin/bash

set -ev

docker build -t $IMAGE_TAG --build-arg SETUP_EXTRAS=$SETUP_EXTRAS --target tests .
bash .ci/docker-login.sh
docker push $IMAGE_TAG
