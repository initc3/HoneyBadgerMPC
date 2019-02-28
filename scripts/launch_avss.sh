#!/bin/bash

# This script runs AVSS in 5 processes.
# Usage: sh scripts/launch_avss.sh honeybadgermpc/hbavss_multi.py conf/avss/local.ini

if [ $# -eq 3 ] ; then
    echo '>> Invalid number of args passed.'
    exit 1
fi

if [ -z "$1" ]
  then
    echo "MPC file to run not specified."
fi

if [ -z "$2" ]
  then
    echo "MPC config file prefix not specified."
fi

# Change dir/file.py to dir.file
FILE_PATH=$1
DIRS=(${FILE_PATH//\// })
DOT_SEPARATED_PATH=$(IFS=. ; echo "${DIRS[*]}")
MODULE_PATH=${DOT_SEPARATED_PATH::-3}

CONFIG_PATH=$2

CMD="python -m ${MODULE_PATH}"
echo ">>> Command to be executed: '${CMD}'"

# Generate config file locally
set -x
tmux new-session     "${CMD} -d -f ${CONFIG_PATH}.0; sh" \; \
     splitw -h -p 50 "${CMD} -d -f ${CONFIG_PATH}.1; sh" \; \
     splitw -v -p 50 "${CMD} -d -f ${CONFIG_PATH}.2; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} -d -f ${CONFIG_PATH}.3; sh" \; \
     splitw -v -p 50 "${CMD} -d -f ${CONFIG_PATH}.4; sh"
