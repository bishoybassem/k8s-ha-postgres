#!/bin/sh -e

pod_name=$(cat $1 | cut -s -d ',' -f 1)
addr=$(cat $1 | cut -s -d ',' -f 2)

echo "master backend state before:"
echo "show servers state master" | nc localhost 9998

echo "Disabling server master0 and shutting down the sessions..."
echo "set server master/master0 state maint" | nc localhost 9998
echo "shutdown sessions server master/master0" | nc localhost 9998

if [ -n "$pod_name" ]; then
	echo "Enabling server master0 for pod $pod_name with ip $addr..."
	echo "set server master/master0 addr $addr" | nc localhost 9998
	echo "set server master/master0 state ready" | nc localhost 9998
fi

echo "master backend state after:"
echo "show servers state master" | nc localhost 9998