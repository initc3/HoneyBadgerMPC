#!/bin/bash
if [ "$TRAVIS_PULL_REQUEST" == "false" ]  || [ "$TRAVIS_PULL_REQUEST_SLUG" == "initc3/HoneyBadgerMPC" ]; then
 docker run -it dsluiuc/honeybadger-prod:$TRAVIS_COMMIT sphinx-build -M html docs docs/_build -c docs -W
else 
 docker run -it dsluiuc/honeybadger-prod:latest sphinx-build -M html docs docs/_build -c docs -W
fi
