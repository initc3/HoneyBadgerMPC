#!/bin/bash
#
#  shaper.sh
#  ---------
#  A utility script for traffic shaping using tc
#
#  Usage
#  -----
#  shape.sh start - starts the shaper
#  shape.sh stop - stops the shaper
#  shape.sh restart - restarts the shaper
#  shape.sh show - shows the rules currently being shaped
#
#  tc uses the following units when passed as a parameter.
#    kbps: Kilobytes per second
#    mbps: Megabytes per second
#    kbit: Kilobits per second
#    mbit: Megabits per second
#    bps: Bytes per second
#  Amounts of data can be specified in:
#    kb or k: Kilobytes
#    mb or m: Megabytes
#    mbit: Megabits
#    kbit: Kilobits
#
#  AUTHORS
#  -------
#  Aaron Blankstein
#  Jeff Terrace
#
#  Original script written by: Scott Seong
#  Taken from URL: http://www.topwebhosts.org/tools/traffic-control.php
#

set -e  # fail if any command fails

# Name of the traffic control command.
TC=/sbin/tc
# Interface to shape
IF=lo

start() {
    # Average to delay packets by
    LATENCY=200ms
    # Jitter value for packet delay
    # Packets will be delayed by $LATENCY +/- $JITTER
    JITTER=50ms

    if [ -z "$2" ]
    then
        echo "Using default latency: $LATENCY"
    else
        LATENCY=$2
    fi

    if [ -z "$3" ]
    then
        echo "Using default jitter: $JITTER"
    fi
    
    $TC qdisc add dev $IF root handle 1:0 netem delay $LATENCY $JITTER 
    $TC qdisc add dev $IF parent 1:1 handle 10: netem delay $LATENCY $JITTER 
}

stop() {
    set +e  # Let stop
    $TC qdisc del dev $IF root
    # $TC qdisc del dev $IF parent 1:1
    set -e
}

show() {
    $TC -s qdisc ls dev $IF
}

case "$1" in

start)

echo -n "Starting bandwidth shaping: "
start $1 $2 $3
echo "done"
;;

stop)

echo -n "Stopping bandwidth shaping: "
stop
echo "done"
;;

show)

echo "Bandwidth shaping status for $IF:"
show
echo ""
;;

*)

pwd=$(pwd)
echo "Usage: shaper.sh {start <latency> <jitter>|stop|show}"
;;

esac 
exit 0
