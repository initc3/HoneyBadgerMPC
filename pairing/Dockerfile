FROM python:3-stretch

ENV PYTHONUNBUFFERED=1

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly

ENV PATH /root/.cargo/bin:$PATH

RUN mkdir -p /usr/src/pairing
WORKDIR /usr/src/pairing

RUN pip install --upgrade pip ipython

COPY . /usr/src/pairing

RUN pip install --no-cache-dir -e .
