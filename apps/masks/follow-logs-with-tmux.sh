#!/bin/bash

if [ -z $TMUX ]; then
    echo "tmux is not active, will start new session"
    TMUX_CMD="new-session"
else
    echo "tmux is active, will launch into new window"
    TMUX_CMD="new-window"
fi

tmux $TMUX_CMD "docker-compose logs -f blockchain; sh" \; \
    splitw -h -p 50 "docker-compose logs -f setup; sh" \; \
    splitw -v -p 50 "docker-compose logs -f mpcnet; sh" \; \
    selectp -t 0 \; \
    splitw -v -p 50 "docker-compose logs -f client; sh"
