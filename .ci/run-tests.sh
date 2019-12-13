#!/bin/bash

set -ev

if [ -z $1 ]; then
    tag=$IMAGE_TAG
else
    tag=$1
fi

docker run -it $tag \
    pytest --verbose \
           --numprocesses=auto \
           --cov \
           --cov-report=term-missing \
           --cov-report=xml \
           -Wignore::DeprecationWarning
