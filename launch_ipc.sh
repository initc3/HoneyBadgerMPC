#!/bin/bash
# Assume hosts are as follows:
"""
 127.0.0.1   hbmpc_0
 127.0.0.1   hbmpc_1
 127.0.0.1   hbmpc_2
 127.0.0.1   hbmpc_3
"""

CMD="python -m honeybadgermpc.ipc 4 1"
set -x
tmux new-session     "${CMD} hbmpc_0; sh" \; \
     splitw -h -p 50 "${CMD} hbmpc_1; sh" \; \
     splitw -v -p 50 "${CMD} hbmpc_2; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} hbmpc_3; sh"
