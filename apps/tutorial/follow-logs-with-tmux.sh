#!/bin/bash

if [ -z $TMUX ]; then
    echo "tmux is not active, will start new session"
    TMUX_CMD="new-session"
else
    echo "tmux is active, will launch into new window"
    TMUX_CMD="new-window"
fi

tmux $TMUX_CMD "docker-compose -f tutorial-2.yml logs -f node0; sh" \; \
    splitw -h -p 50 "docker-compose -f tutorial-2.yml logs -f node1; sh" \; \
    splitw -v -p 50 "docker-compose -f tutorial-2.yml logs -f node2; sh" \; \
    selectp -t 0 \; \
    splitw -v -p 50 "docker-compose -f tutorial-2.yml logs -f node3; sh"
