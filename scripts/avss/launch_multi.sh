#!/bin/bash

CMD="python -m honeybadgermpc.hbavss_multi"
CONFIG_PATH=conf/hbavss.multi.ini

# Generate config file locally
set -x
tmux new-session     "${CMD} 0 ${CONFIG_PATH}; sh" \; \
     splitw -h -p 50 "${CMD} 1 ${CONFIG_PATH}; sh" \; \
     splitw -v -p 50 "${CMD} 2 ${CONFIG_PATH}; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} 3 ${CONFIG_PATH}; sh" \; \
     splitw -v -p 50 "${CMD} 4 ${CONFIG_PATH}; sh"
