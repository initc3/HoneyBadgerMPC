# Dockerfile is used to create a development environment for running our code
# The dockerfile is composed of several distinct phases: 
# - Base 
#   - Install baseline dependencies used to build our main dependencies (e.g. cffi,
#     make, etc.)
#   - Commands in this section should be changed as little as possible to improve 
#     cache performance
# - Dependencies
#   - This is composed of a bunch of different targets, each of which inherit from
#     the base target, and create a single dependency. 
#   - It's essential to only copy what's necessary from the build context in this 
#     stage to improve caching
# - Final target
#   - Pull in all created dependencies from the other targets into one streamlined 
#     target
#   - We should create a dev and prod target.

##
# Base target:
# All used targets should be based off of this target, and as such, changes to this 
# should be kept to an absolute minimum, as it causes the longest builds.
# This should contain all setup required by all other targets, such as environment
# variables, and essential apt dependencies.
##
FROM python:3.7.3-slim AS base

# Allows for log messages to be immediately dumped to the 
# stream instead of being buffered.
ENV PYTHONUNBUFFERED 1 

# Path variables needed for Charm
ENV LIBRARY_PATH /usr/local/lib
ENV LD_LIBRARY_PATH /usr/local/lib
ENV LIBRARY_INCLUDE_PATH /usr/local/include

ENV PYTHON_LIBRARY_PATH /opt/venv
ENV PATH ${PYTHON_LIBRARY_PATH}/bin:${PATH}

# Make sh point to bash
# This is being changed since it will avoid any errors in the `launch_mpc.sh` script
# which relies on certain code that doesn't work in container's default shell.
RUN ln -sf bash /bin/sh

# Install apt dependencies
# Put apt dependencies here that are needed by all build paths
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    iproute2 \
    libflint-dev \
    libgmp-dev \
    libffi-dev \
    libmpc-dev \
    libmpfr-dev \
    libssl-dev \
    openssl \ 
    sudo 

# Setup virtualenv
RUN pip install --upgrade pip virtualenv
RUN python -m virtualenv ${PYTHON_LIBRARY_PATH}

# Install pip dependencies here that are absolutely required by setup.py for 
# better cache performance. These should be changed rarely, as they cause
# long rebuild times.
RUN pip install \
    cffi \
    Cython \
    gmpy2 \
    psutil \
    pycrypto \
    pyzmq \
    zfec 

# This is needed otherwise the build for the power sum solver will fail.
# This is a known issue in the version of libflint-dev in apt.
# https://github.com/wbhart/flint2/issues/217
# This has been fixed if we pull the latest code from the repo. However, we want
# to avoid compiling the lib from the source since it adds 20 minutes to the build.
RUN sed -i '30c #include "flint/flint.h"' /usr/include/flint/flintxx/flint_classes.h

##
# Build Target:
# Isolated target to build heavy dependencies
# Built dependencies must be manually copied over in later stages.
##
FROM base AS build
WORKDIR /

# Install apt dependencies. These dependencies should only be those which are
# needed for building dependencies. Any other dependencies should be installed 
# in later targets
RUN apt-get install -y --no-install-recommends \
    bison \
    cmake \
    flex \
    wget

# Downloads rust and sets it up
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly
ENV PATH "/root/.cargo/bin:${PATH}"


# Install NTL
WORKDIR /
RUN curl -so - https://www.shoup.net/ntl/ntl-11.3.2.tar.gz | tar xzvf -
WORKDIR /ntl-11.3.2/src  
RUN ./configure CXXFLAGS="-g -O2 -fPIC -march=native -pthread -std=c++11" 
RUN make 
RUN make install

# Install better pairing
# Creates dependencies in /usr/local/include/pbc and /usr/local/lib
WORKDIR /
RUN curl -so - https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz | tar xzvf - 
WORKDIR /pbc-0.5.14/
RUN ./configure
RUN make
RUN make install

# Install charm
# Creates /charm/dist/Charm_Crypto...x86_64.egg, which gets copied into the venv
# /opt/venv/lib/python3.7/site-packages/Charm_crypto...x86_64.egg
WORKDIR /
RUN git clone https://github.com/JHUISI/charm.git 
WORKDIR /charm
RUN git reset --hard be9587ccdd4d61c591fb50728ebf2a4690a2064f
RUN ./configure.sh
RUN make install 

# Copy pairing from build context and install it
COPY pairing/ pairing/
RUN pip install pairing/

# Install final dependencies needed in prod, as well as 
# pull in dependencies from the build target.
# The reason there is this pre-prod target is so that we can have a final target,
# prod, which pulls in all remaining files from the build context into the 
# docker image. This will give us the best possible caching performance given 
# routine file changes.
#
# Furthermore, by splitting these targets, we can continue building off of this
# target for dev targets later with good cache performance by delaying copying 
# changed files until the end of the dev targets.
FROM base AS pre-prod
WORKDIR /usr/src/HoneyBadgerMPC/

COPY --from=build ${PYTHON_LIBRARY_PATH} ${PYTHON_LIBRARY_PATH}
COPY --from=build /usr/local/include/ /usr/local/include/
COPY --from=build ${LIBRARY_PATH} ${LIBRARY_PATH}

COPY apps/asynchromix/cpp/ apps/asynchromix/cpp/
RUN make -C apps/asynchromix/cpp

COPY setup.py .
COPY README.md .
COPY honeybadgermpc/__version__.py honeybadgermpc/
COPY honeybadgermpc/__init__.py honeybadgermpc/
COPY honeybadgermpc/ntl/ honeybadgermpc/ntl/
COPY apps/asynchromix/solver/ apps/asynchromix/solver/
RUN pip install -e .['tests,docs']

# This is the target that can minimally run the unit tests.
FROM pre-prod AS prod
COPY . .

# This is the target that installs the remaining dependencies we
# want to have on the dev machines. This is the best place to install 
# dependencies from pip, npm, apt, etc. for rapid iteration, as
# it will not affect the build times or image sizes of the production image.
# Once a dependency is deemed necessary enough, it can be later moved into 
# the production image.
FROM pre-prod AS pre-dev
WORKDIR /

# Install solidity
RUN git clone --recursive https://github.com/ethereum/solidity.git
WORKDIR /solidity/
RUN git checkout v0.4.24 # Old version necessary to work???
RUN git submodule update --init --recursive
RUN ./scripts/install_deps.sh
RUN mkdir build/
WORKDIR /solidity/build/
RUN cmake ..
RUN make install
WORKDIR /

# Bash commands
RUN echo "alias cls=\"clear && printf '\e[3J'\"" >> ~/.bashrc

# Install Nodejs
RUN curl -sL https://deb.nodesource.com/setup_8.x | bash

# If you're testing out apt dependencies, put them here
RUN apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    tmux \
    vim

RUN npm install -g ganache-cli

# Install remaining pip dependencies here
WORKDIR /usr/src/HoneyBadgerMPC/
RUN pip install -e .['dev']

FROM pre-dev AS dev
COPY . .

