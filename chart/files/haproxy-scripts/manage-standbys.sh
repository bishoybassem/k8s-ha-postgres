#!/bin/sh -e

backend_state="$(echo "show servers state standby" | nc localhost 9998)"
echo -e "standby backend state before:\n$backend_state\n"

servers_to_disable="$(echo "$backend_state" | grep " standby[0-9]")"

while read entry; do
	pod_name=$(echo $entry | cut -s -d ',' -f 1)
	addr=$(echo $entry | cut -s -d ',' -f 2)
	srv_name=standby$(echo $pod_name | grep -o '[^-]*$')
	echo "Enabling server $srv_name for pod $pod_name with ip $addr..."
	echo "set server standby/$srv_name addr $addr" | nc localhost 9998
	echo "set server standby/$srv_name state ready" | nc localhost 9998

	servers_to_disable="$(echo "$servers_to_disable" | grep -v " $srv_name ")"
done < $1

IFS=$'\n'
for entry in $servers_to_disable; do
	srv_name=$(echo $entry | cut -d ' ' -f 4)
	srv_addr=$(echo $entry | cut -d ' ' -f 5)
	if [ "$srv_addr" != "127.0.0.1" ]; then
		echo "Disabling server $srv_name as it has a non-localhost ip..."
		echo "set server standby/$srv_name state maint" | nc localhost 9998
		echo "set server standby/$srv_name addr 127.0.0.1" | nc localhost 9998
		echo "shutdown sessions server standby/$srv_name" | nc localhost 9998
	fi
done

echo "standby backend state after:"
echo "show servers state standby" | nc localhost 9998