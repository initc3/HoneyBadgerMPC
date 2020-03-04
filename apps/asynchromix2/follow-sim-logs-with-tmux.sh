#!/bin/bash

if [ -z $TMUX ]; then
    echo "tmux is not active, will start new session"
    TMUX_CMD="new-session"
else
    echo "tmux is active, will launch into new window"
    TMUX_CMD="new-window"
fi

tmux $TMUX_CMD "docker-compose logs -f eth.blockchain.io; sh" \; \
    splitw -v -p 60 "docker-compose logs -f hbmpc.peer0.io; sh" \; \
    splitw -v -p 60 "docker-compose logs -f hbmpc.peer1.io; sh" \; \
    splitw -v -p 60 "docker-compose logs -f hbmpc.peer2.io; sh" \; \
    splitw -v -p 60 "docker-compose logs -f hbmpc.peer3.io; sh" \; \
    selectp -t 0 \; \
    splitw -h -p 60 "docker-compose logs -f hbmpc.coordinator.io; sh" \; \
    splitw -h -p 60 "docker-compose logs -f hbmpc.client.io; sh"
