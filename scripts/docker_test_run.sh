#!/bin/bash
if [ "$TRAVIS_PULL_REQUEST" == "false" ]  || [ "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]; then
 docker run -it dsluiuc/honeybadger-prod:$TRAVIS_COMMIT pytest -v --cov --cov-report=term-missing --cov-report=xml -Wignore::DeprecationWarning -nauto
else 
 docker run -it dsluiuc/honeybadger-prod:latest pytest -v --cov --cov-report=term-missing --cov-report=xml -Wignore::DeprecationWarning -nauto
fi
