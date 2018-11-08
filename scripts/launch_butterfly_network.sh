#!/bin/bash
# Assume hosts are as follows:
"""
 127.0.0.1   hbmpc_0
 127.0.0.1   hbmpc_1
 127.0.0.1   hbmpc_2
 127.0.0.1   hbmpc_3
"""

CMD="python -m apps.shuffle.butterfly_network"
CONFIG_PATH=conf/ipc.network.local/hbmpc.ini
set -x
rm sharedata/READY # NOTE: see butterly_network.py wait_for_preprocessing
tmux new-session     "${CMD} 0 ${CONFIG_PATH}; sh" \; \
     splitw -h -p 50 "${CMD} 1 ${CONFIG_PATH}; sh" \; \
     splitw -v -p 50 "${CMD} 2 ${CONFIG_PATH}; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} 3 ${CONFIG_PATH}; sh"
