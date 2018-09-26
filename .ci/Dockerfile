FROM python:alpine3.8

ENV PYTHONUNBUFFERED=1

RUN apk --update add make gcc musl-dev gmp-dev mpc1-dev mpfr-dev libffi-dev openssl-dev

RUN mkdir -p /usr/src/HoneyBadgerMPC
WORKDIR /usr/src/HoneyBadgerMPC

RUN pip install --upgrade pip

COPY . /usr/src/HoneyBadgerMPC

ARG BUILD
RUN pip install --no-cache-dir .[$BUILD]
