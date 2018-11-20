#!/bin/bash
pids=""
THREAD_NUM=200
mkfifo tmp
exec 9<>tmp
for ((i = 0; i < $THREAD_NUM; i++))
do
    echo -ne "\n" 1>&9
done


# launch multiple curl in parallel to download inputs
while IFS='' read -r line ; do
    read -u 9
    {
	    curl -sSO $line 
	    pids="$pids $!"
	    echo -ne "\n" 1>&9
	}&

done < "$1"

# wait for multiple curl to finish
for pid in $pids; do
    wait $pid 
done

rm tmp

