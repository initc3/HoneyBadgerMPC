ARG HBMPC_DEPS_DIGEST="46902d869ea881d7b00b72ff6accf2558a5e15849da5fa5cc722b4ff82a507f8"

FROM initc3/honeybadgermpc-deps@sha256:$HBMPC_DEPS_DIGEST AS build-compute-power-sums
COPY apps/asynchromix/cpp/ /usr/src/apps/asynchromix/cpp/
RUN make -C /usr/src/apps/asynchromix/cpp

FROM initc3/honeybadgermpc-deps@sha256:$HBMPC_DEPS_DIGEST AS pre-tests

COPY pairing /usr/src/pairing
RUN pip install -v /usr/src/pairing/

ENV HBMPC_HOME /usr/src/HoneyBadgerMPC
WORKDIR $HBMPC_HOME
COPY --from=build-compute-power-sums /usr/local/bin/compute-power-sums /usr/local/bin/

COPY setup.py .
COPY README.md .
COPY honeybadgermpc/__version__.py honeybadgermpc/
COPY honeybadgermpc/__init__.py honeybadgermpc/
COPY honeybadgermpc/ntl/ honeybadgermpc/ntl/
COPY apps/asynchromix/solver/ apps/asynchromix/solver/
ARG SETUP_EXTRAS="tests,docs"
RUN pip install -e .[$SETUP_EXTRAS]

FROM pre-tests AS tests
COPY . .

FROM tests as pre-dev
WORKDIR /

# solidity
COPY --from=ethereum/solc:0.4.24 /usr/bin/solc /usr/bin/solc

# Bash commands
RUN echo "alias cls=\"clear && printf '\e[3J'\"" >> ~/.bashrc

# Make sh point to bash
# This is being changed since it will avoid any errors in the `launch_mpc.sh` script
# which relies on certain code that doesn't work in container's default shell.
RUN ln -sf bash /bin/sh

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
WORKDIR $HBMPC_HOME
RUN pip install -e .['dev']

FROM pre-dev as dev
COPY . .
