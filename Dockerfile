# Dockerfile contains multiple levels of images--
# First, a base image containing dependencies shared by all other images:
#   - apt dependencies
#   - rust
#   - ntl
#   - pbc
#   - charm
#   - base pip dependencies (cython & setup.py)
#   - ethereum
# 
# Thereafter, it adds ever increasing levels of dependencies-- 
#   - Test requirements (including doc requirements)
#   - Dev requirements (including aws)
#
# In order to build and push this to dockerhub, run:
# docker build . --target test-image --tag dsluiuc/honeybadgermpc-docker-base
# docker push dsluiuc/honeybadgermpc-docker-base:latest
FROM python:3.7.3-slim AS base-image

# Allows for log messages to be immediately dumped to the 
# stream instead of being buffered.
ENV PYTHONUNBUFFERED    1 

# Path variables needed for Charm
ENV LIBRARY_PATH        /usr/local/lib
ENV LD_LIBRARY_PATH     /usr/local/lib

# Make sh point to bash
# This is being changed since it will avoid any errors in the `launch_mpc.sh` script
# which relies on certain code that doesn't work in container's default shell.
RUN ln -sf bash /bin/sh

# Install apt dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bison \
    curl \
    flex \
    g++ \
    git \
    iproute2 \
    libflint-dev \
    libgmp-dev \
    libmpc-dev \
    libmpfr-dev \
    libssl-dev \
    make \
    openssl \
    tmux \
    wget \
    vim 

# This is needed otherwise the build for the power sum solver will fail.
# This is a known issue in the version of libflint-dev in apt.
# https://github.com/wbhart/flint2/issues/217
# This has been fixed if we pull the latest code from the repo. However, we want
# to avoid compiling the lib from the source since it adds 20 minutes to the build.
RUN sed -i '30c #include "flint/flint.h"' /usr/include/flint/flintxx/flint_classes.h
RUN echo "alias cls=\"clear && printf '\e[3J'\"" >> ~/.bashrc

# RUN python -m venv /opt/venv
# ENV PATH "/opt/venv/bin:${PATH}"

# Downloads rust and sets it up
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly-2018-10-24
ENV PATH "/root/.cargo/bin:${PATH}"

# Download and build NTL from source
# Shoup recommends not using O3
RUN curl -so - https://www.shoup.net/ntl/ntl-11.3.2.tar.gz | tar xzvf -
WORKDIR /ntl-11.3.2/src  
RUN ./configure CXXFLAGS="-g -O2 -fPIC -march=native -pthread -std=c++11" 
RUN make 
RUN make install
WORKDIR /


# Install betterpairing
RUN curl -so - https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz | tar xzvf - 
WORKDIR /pbc-0.5.14/
RUN ./configure
RUN make
RUN make install
WORKDIR /


# Downloads and installs charm
RUN git clone https://github.com/JHUISI/charm.git 
WORKDIR /charm/
RUN git reset --hard be9587ccdd4d61c591fb50728ebf2a4690a2064f
RUN ./configure.sh
RUN make install
WORKDIR /


# Ethereum .[eth] extras
RUN apt-get install -y --no-install-recommends \
    git cmake g++ \
    libffi-dev libssl-dev sudo
RUN curl -sL https://deb.nodesource.com/setup_8.x | bash
RUN apt-get install -y --no-install-recommends nodejs npm
RUN npm install -g ganache-cli
RUN git clone --recursive https://github.com/ethereum/solidity.git
WORKDIR /solidity/
RUN git checkout v0.4.24 # Old version necessary to work???
RUN git submodule update --init --recursive
RUN ./scripts/install_deps.sh
RUN mkdir build/
WORKDIR build
RUN cmake ..
RUN make install
WORKDIR /


# Below derived from https://pythonspeed.com/articles/multi-stage-docker-python/
WORKDIR /usr/src/HoneyBadgerMPC
COPY . /usr/src/HoneyBadgerMPC

RUN pip install --upgrade pip
RUN pip install Cython
RUN pip install -e .
RUN pip install pairing/

RUN make -C apps/asynchromix/cpp

# Installs test dependencies
# For now, upload this to docker-hub
#
# TODO: see if we can shrink this image size more.
# I was able to do it by copying over from LIBRARY_PATH, /opt/venv/ 
# and compiled outputs from apps and ntl, but I couldn't manage to get
# lib_solver to import correctly.
FROM base-image AS test-image
RUN pip install -e .["tests,docs"]

# Actual image to use for dev work
FROM test-image as dev-release
# -e so that it installs locally
# RUN pip install --user -e .["dev,aws"]
RUN pip install -e .["dev,aws"]
