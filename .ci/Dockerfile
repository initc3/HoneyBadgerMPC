FROM dsluiuc/honeybadgermpc-base AS travis-image

WORKDIR /usr/src/HoneyBadgerMPC
COPY . /usr/src/HoneyBadgerMPC

RUN pip install -e .["tests,docs"]
RUN make -C apps/asynchromix/cpp

