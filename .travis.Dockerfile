FROM dsluiuc/honeybadgermpc-docker-base

WORKDIR /usr/src/HoneyBadgerMPC

COPY . /usr/src/HoneyBadgerMPC

RUN pip install -e .
RUN make -C apps/shuffle/cpp -j