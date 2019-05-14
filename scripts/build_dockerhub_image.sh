#!/bin/bash

# This script is used to create the docker image we push to dockerhub.
# This requires that you have access to the dsluiuc dockerhub page. 
# Currently, only Drake and Samarth have access to this.
# Usage: sh scripts/build_dockerhub_image.sh

docker login
docker build . --target test-image --tag dsluiuc/honeybadgermpc-test-image
docker push dsluiuc/honeybadgermpc-test-image:latest