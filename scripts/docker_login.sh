#!/bin/bash
echo $TRAVIS_PULL_REQUEST_SLUG;
if [ "$TRAVIS_PULL_REQUEST" == "false" ]  || [ "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]
 then
 	echo "Logging in with docker credentials"; 
 	docker login -p $DOCKER_PASS -u $DOCKER_USER 
fi