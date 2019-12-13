#!/bin/bash

set -ev

if [ -z $1 ]; then
    tag=$IMAGE_TAG
else
    tag=$1
fi

. .ci/build-image.sh $tag
. .ci/docker-login.sh
docker push $tag
