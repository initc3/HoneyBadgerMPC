FROM quay.io/pypa/manylinux1_x86_64 as wheel_builder

COPY ./pairing /usr/src/pairing
#RUN git clone -b docker-build https://github.com/sbellem/pairing.git /usr/src/pairing
WORKDIR /usr/src/pairing

RUN sh scripts/build-wheel.sh


FROM python:alpine3.8
COPY --from=wheel_builder /usr/src/pairing/wheelhouse/ /usr/src/wheelhouse
COPY --from=wheel_builder /usr/src/pairing/scripts/_manylinux.py /usr/local/bin/

ENV PYTHONUNBUFFERED=1

RUN apk --update add make gcc vim tmux

RUN apk --update add musl-dev gmp-dev mpc1-dev mpfr-dev libressl-dev libffi-dev libc6-compat

RUN mkdir -p /usr/src/HoneyBadgerMPC
WORKDIR /usr/src/HoneyBadgerMPC

RUN pip install --upgrade pip

COPY . /usr/src/HoneyBadgerMPC

RUN pip install pycrypto
RUN pip install zfec

RUN pip install /usr/src/wheelhouse/*.whl

RUN pip install --no-cache-dir -e .[dev]
