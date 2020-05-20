#!/bin/bash

set -ev

if [ -z $1 ]; then
    tag=$IMAGE_TAG
else
    tag=$1
fi

docker run -it $tag \
    pytest --verbose \
           --benchmark-disable \
           -m skip_bench \
           benchmark/
