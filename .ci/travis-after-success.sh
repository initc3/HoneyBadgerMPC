#!/bin/bash

set -ev

if [ "${BUILD}" == "tests" ]; then
    codecov -v
fi
