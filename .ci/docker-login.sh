#!/bin/bash

set -ev

echo "Logging in with docker credentials"
echo "$DOCKER_PASSWORD" | docker login --username "$DOCKER_USERNAME" --password-stdin
