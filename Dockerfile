FROM python:3.7.1-stretch

# Allows for log messages to be immediately dumped to the 
# stream instead of being buffered.
ENV PYTHONUNBUFFERED    1 

# Adds cargo to path for rust dependencies
ENV PATH                /root/.cargo/bin:$PATH

# Path variables needed for Charm
ENV LIBRARY_PATH        /usr/local/lib
ENV LD_LIBRARY_PATH     /usr/local/lib

# Downloads rust and sets it up
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly-2018-10-24

# Install apt dependencies
RUN apt-get update && apt-get install -y \
    vim \
    tmux \
    bison \
    flex \
    libgmp-dev \
    libmpc-dev \
    libmpfr-dev \
    libflint-dev
# Download and build NTL from source
# Shoup recommends not using O3
RUN wget -qO- https://www.shoup.net/ntl/ntl-11.3.2.tar.gz | tar xzvf - \
         &&  cd ntl-11.3.2/src \
         && ./configure CXXFLAGS="-g -O2 -fPIC -march=native -pthread -std=c++11" \
         && make -j4 \
         && make install

# Sets default directory for running the rest of the commands
WORKDIR /usr/src/HoneyBadgerMPC

RUN pip install --upgrade pip

COPY . /usr/src/HoneyBadgerMPC

RUN pip install pairing/

RUN wget -qO- https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz | tar xzvf - \
    && cd pbc-0.5.14 \
    && ./configure \
    && make \
    && make install


# Make sh point to bash
# This is being changed since it will avoid any errors in the `launch_mpc.sh` script
# which relies on certain code that doesn't work in container's default shell.
RUN ln -sf bash /bin/sh

# Downloads and installs charm
RUN git clone https://github.com/JHUISI/charm.git \
    && cd charm \
    && git reset --hard be9587ccdd4d61c591fb50728ebf2a4690a2064f \
    && ./configure.sh \
    && make install

# This is needed otherwise the build for the power sum solver will fail.
# This is a known issue in the version of libflint-dev in apt.
# https://github.com/wbhart/flint2/issues/217
# This has been fixed if we pull the latest code from the repo. However, we want
# to avoid compiling the lib from the source since it adds 20 minutes to the build.
RUN sed -i '30c #include "flint/flint.h"' /usr/include/flint/flintxx/flint_classes.h

ARG BUILD
RUN pip install Cython

# Runs setup.py
RUN pip install --no-cache-dir -e .[$BUILD]

RUN make -C apps/shuffle/cpp

RUN echo "alias cls=\"clear && printf '\e[3J'\"" >> ~/.bashrc
