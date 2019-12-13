#!/bin/bash

set -ev

if [ -z $1 ]; then
    tag=$IMAGE_TAG
else
    tag=$1
fi

docker run -it $tag sphinx-build -M html docs docs/_build -c docs -W
