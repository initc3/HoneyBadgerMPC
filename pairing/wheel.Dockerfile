FROM quay.io/pypa/manylinux1_x86_64 as wheel_builder

ENV PYTHONUNBUFFERED=1

RUN mkdir -p /usr/src/pairing
WORKDIR /usr/src/pairing
COPY . /usr/src/pairing

RUN sh scripts/build-wheel.sh


FROM python:alpine3.8
COPY --from=wheel_builder /usr/src/pairing/wheelhouse/ /usr/src/wheelhouse
COPY --from=wheel_builder /usr/src/pairing/dist/ /usr/src/dist

ENV PYTHONUNBUFFERED=1
RUN pip install --upgrade pip ipython
RUN apk --update add libgcc libc6-compat

WORKDIR /usr/src/app
COPY scripts/_manylinux.py /usr/local/bin/
RUN pip install /usr/src/wheelhouse/*.whl
