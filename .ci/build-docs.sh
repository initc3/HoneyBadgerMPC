#!/bin/bash

set -ev

docker run -it $IMAGE_TAG sphinx-build -M html docs docs/_build -c docs -W
