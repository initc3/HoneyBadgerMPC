#!/bin/bash

set -x

CMD="docker-compose -f network.yml up"

docker-compose -f network.yml rm -sf

tmux new-session     "${CMD} hbmpc_0; sh" \; \
     splitw -h -p 50 "${CMD} hbmpc_1; sh" \; \
     splitw -v -p 50 "${CMD} hbmpc_2; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} hbmpc_3; sh"
