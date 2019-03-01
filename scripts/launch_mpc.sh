#!/bin/bash

# This script runs an MPC program in 4 processes.
# Usage: sh scripts/launch_mpc.sh honeybadgermpc/ipc.py conf/mpc/local

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

set -x
rm -f sharedata/READY # NOTE: see preprocessing.py wait_for_preprocessing
tmux new-session     "${CMD} -d -f ${CONFIG_PATH}.0.json; sh" \; \
     splitw -h -p 50 "${CMD} -d -f ${CONFIG_PATH}.1.json; sh" \; \
     splitw -v -p 50 "${CMD} -d -f ${CONFIG_PATH}.2.json; sh" \; \
     selectp -t 0 \; \
     splitw -v -p 50 "${CMD} -d -f ${CONFIG_PATH}.3.json; sh"
