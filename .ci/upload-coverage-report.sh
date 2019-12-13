#!/bin/bash

set -ev

pip install --upgrade codecov

# Copy the coverage report from the container to the host
docker cp \
    $(docker ps -alq --format "{{.Names}}"):/usr/src/HoneyBadgerMPC/coverage.xml .

# upload the report
codecov -v
