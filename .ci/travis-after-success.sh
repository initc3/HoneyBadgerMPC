#!/bin/bash

if [ "${BUILD}" == "tests" ]; then
    codecov -v
fi
