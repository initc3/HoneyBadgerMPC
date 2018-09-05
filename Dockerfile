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

ARG BUILD
RUN pip install --no-cache-dir .[$BUILD]

RUN make -C honeybadgermpc/apps/shuffle/cpp
RUN sed -i '30c #include "flint/flint.h"' /usr/include/flint/flintxx/flint_classes.h
RUN python honeybadgermpc/apps/shuffle/solver/solver_build.py