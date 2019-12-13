#!/bin/bash

set -ev

docker run -it $IMAGE_TAG \
    pytest --verbose \
           --numprocesses=auto \
           --cov \
           --cov-report=term-missing \
           --cov-report=xml \
           -Wignore::DeprecationWarning
