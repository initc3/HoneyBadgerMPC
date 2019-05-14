# This base image contains the bare minimum dependencies / environment details
# to create the subsequent images-- this is where to put dependencies that are
# absolutely required to run our code in travis, build dev dependencies, and 
# eventually create our dev image. This is to be as small as possible to keep 
# travis times down.
#
# In order to build and push this to dockerhub, run:
# docker build . --target test-image --tag dsluiuc/honeybadgermpc-docker-base
# docker push dsluiuc/honeybadgermpc-docker-base:latest
FROM python:3.7.3-slim AS base-image

# Allows for log messages to be immediately dumped to the 
# stream instead of being buffered.
ENV PYTHONUNBUFFERED 1

# Path variables needed for Charm
ENV LIBRARY_PATH        /usr/local/lib
ENV LD_LIBRARY_PATH     /usr/local/lib

# Make sh point to bash
# This is being changed since it will avoid any errors in the `launch_mpc.sh` script
# which relies on certain code that doesn't work in container's default shell.
RUN ln -sf bash /bin/sh

RUN pip install --upgrade pip virtualenv

# Derived from https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=/opt/venv
RUN python -m virtualenv ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN echo "alias cls=\"clear && printf '\e[3J'\"" >> ~/.bashrc

# Packages absolutely required to run our tests
# Installing gcc because we need libgomp.so.1
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \ 
    libflint-dev \
    libgmp-dev \
    libmpc-dev \
    libmpfr-dev 

# This is needed otherwise the build for the power sum solver will fail.
# This is a known issue in the version of libflint-dev in apt.
# https://github.com/wbhart/flint2/issues/217
# This has been fixed if we pull the latest code from the repo. However, we want
# to avoid compiling the lib from the source since it adds 20 minutes to the build.
RUN sed -i '30c #include "flint/flint.h"' /usr/include/flint/flintxx/flint_classes.h


# This image will contain all of the apt packages required to build dependencies.
# It will also download dependencies, build them from source, and install pip dependencies 
# using pipenv. 
FROM base-image AS build-image

# Install apt dependencies required to build dependencies, or are otherwise
# not required for testing (see: vim, tmux)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bison \
    curl \
    flex \
    g++ \
    git \
    iproute2 \
    libssl-dev \
    make \
    openssl \
    tmux \
    wget \
    vim 

# Downloads rust/cargo and sets it up
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly-2018-10-24
ENV PATH "/root/.cargo/bin:${PATH}"

# Download and build NTL from source
# Shoup recommends not using O3
WORKDIR /
RUN curl -so - https://www.shoup.net/ntl/ntl-11.3.2.tar.gz | tar xzvf -
WORKDIR /ntl-11.3.2/src  
RUN ./configure CXXFLAGS="-g -O2 -fPIC -march=native -pthread -std=c++11" 
RUN make 
RUN make install

# Install betterpairing
WORKDIR /
RUN curl -so - https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz | tar xzvf - 
WORKDIR /pbc-0.5.14/
RUN ./configure
RUN make
RUN make install

# Install charm
WORKDIR /usr/src/HoneyBadgerMPC
RUN git clone https://github.com/JHUISI/charm.git 
WORKDIR /usr/src/HoneyBadgerMPC/charm
RUN git reset --hard be9587ccdd4d61c591fb50728ebf2a4690a2064f
RUN ./configure.sh
RUN make

WORKDIR /usr/src/HoneyBadgerMPC
COPY . /usr/src/HoneyBadgerMPC

# Build compute-power-sums
RUN make -C apps/shuffle/cpp

# Install all pip dependencies
# One caveat about our pipfile-- we cannot specify cython to install
# before honeybadgermpc in the pipfile, so we install it first
WORKDIR /usr/src/HoneyBadgerMPC/
RUN pip install charm/ pairing/
RUN pip install -e .[tests,docs]

# This is the image used locally through docker-compose for development.
# This will contain all of the sources used to build dependencies, as 
# well as all dependencies specified in Pipfile.
FROM build-image AS dev-image
RUN pip install -e .[dev]


# Minimal image to run tests on. This pulls in the compiled dependencies from 
# build-image, which keeps the image size down. This should be pushed up to dockerhub.
FROM base-image AS test-image
WORKDIR /usr/src/HoneyBadgerMPC/

# Copies over dependencies built from source
COPY --from=build-image /usr/local/lib/ /usr/local/lib/

# Copies over compute_power_sums binary
COPY --from=build-image /usr/local/bin/compute-power-sums /usr/local/bin/compute-power-sums

# Copies over installed pip dependencies
COPY --from=build-image $VIRTUAL_ENV $VIRTUAL_ENV

# Copies over built ntl code
COPY --from=build-image /usr/src/HoneyBadgerMPC/honeybadgermpc/ntl/ honeybadgermpc/ntl/

# Copies lib_solver
COPY --from=build-image /usr/src/HoneyBadgerMPC/*.so .