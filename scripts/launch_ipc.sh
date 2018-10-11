#!/bin/bash
# Assume hosts are as follows:
"""
 127.0.0.1   hbmpc_0
 127.0.0.1   hbmpc_1
 127.0.0.1   hbmpc_2
 127.0.0.1   hbmpc_3
"""

CMD="python -m honeybadgermpc.ipc"
CONFIG_PATH=conf/ipc.network.local
set -x
tmux new-session     "${CMD} ${CONFIG_PATH}/hbmpc_0.ini; sh" \; \
     splitw -h -p 50 "${CMD} ${CONFIG_PATH}/hbmpc_1.ini; sh" \; \
     splitw -v -p 50 "${CMD} ${CONFIG_PATH}/hbmpc_2.ini; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} ${CONFIG_PATH}/hbmpc_3.ini; sh"
