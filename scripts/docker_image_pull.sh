#!/bin/bash
if [ "$TRAVIS_PULL_REQUEST" == "false" ]  || [ "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]; then
 docker pull dsluiuc/honeybadger-prod:$TRAVIS_COMMIT;
 export HB_BUILD_VERSION=$TRAVIS_COMMIT;
else 
 docker pull dsluiuc/honeybadger-prod:latest;
 export HB_BUILD_VERSION="latest";
fi

echo "HB_BUILD_VERSION set to" 
echo $HB_BUILD_VERSION