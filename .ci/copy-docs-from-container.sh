#!/bin/bash

set -ev

docker cp \
    $(docker ps -alq --format "{{.Names}}"):/usr/src/HoneyBadgerMPC/docs/_build \
    docs/_build
