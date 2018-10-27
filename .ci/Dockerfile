FROM quay.io/pypa/manylinux1_x86_64 as wheel_builder

COPY ./pairing /usr/src/pairing
WORKDIR /usr/src/pairing

RUN sh scripts/build-wheel.sh


FROM python:alpine3.8
COPY --from=wheel_builder /usr/src/pairing/wheelhouse/ /usr/src/wheelhouse
COPY --from=wheel_builder /usr/src/pairing/scripts/_manylinux.py /usr/local/bin/

ENV PYTHONUNBUFFERED=1

RUN apk --update add gcc musl-dev gmp-dev libc6-compat mpc1-dev mpfr-dev

RUN mkdir -p /usr/src/HoneyBadgerMPC
WORKDIR /usr/src/HoneyBadgerMPC

RUN pip install --upgrade pip
RUN pip install pycrypto
RUN pip install zfec

COPY . /usr/src/HoneyBadgerMPC

RUN pip install /usr/src/wheelhouse/*.whl

ARG BUILD
RUN pip install --no-cache-dir .[$BUILD]
