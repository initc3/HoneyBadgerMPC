#!/bin/bash
pids=""
RESULT=0

# launch multiple curl in parallel to download inputs
while IFS='' read -r line ; do
    curl -sSO $line &
    pids="$pids $!"
done < "$1"

# wait for multiple curl to finish
for pid in $pids; do
    wait $pid 
done

