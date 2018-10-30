FROM python:3.7.1-stretch

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y vim tmux

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly-2018-10-24

ENV PATH /root/.cargo/bin:$PATH

RUN apt-get update && apt-get install -y libgmp-dev libmpc-dev libmpfr-dev libntl-dev libflint-dev

WORKDIR /usr/src/HoneyBadgerMPC

RUN pip install --upgrade pip

COPY . /usr/src/HoneyBadgerMPC

RUN pip install -e pairing/

# TODO Explain why this is there, and whether this is a temporary workaround,
# and if it is provide pointers to possible better alternatives.
RUN sed -i '30c #include "flint/flint.h"' /usr/include/flint/flintxx/flint_classes.h

ARG BUILD
RUN pip install --no-cache-dir .[$BUILD]

RUN make -C honeybadgermpc/apps/shuffle/cpp
