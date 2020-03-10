#!/bin/bash -e

function quit() {
	exit 0
}

trap quit INT TERM 

export LB_POD_IP=$(kubectl get pods -l app=postgres-lb -o jsonpath='{.items[0].status.podIP}')
export LB_STATS_PORT=9999
export PGHOST=$(kubectl get svc postgres -o jsonpath='{.spec.clusterIP}')
export PGUSER=postgres
export PGPASSWORD=su123
export PGDATABASE=postgres
export PGPORT=5432
export PGCONNECT_TIMEOUT=1

echo "Creating test table ..."
psql -qc "create table if not exists test(id serial, data text)"

function print_row() {
	printf "\t %-13s | %-7s | %-7s | %-7s | %s\n" "$1" "$2" "$3" "$4" "$5"
}

function lb_stats() {
	db_pods=$(kubectl get pods -l app=ha-postgres -o jsonpath='{range .items[*]}{.metadata.name}:{.status.podIP} {end}')
	servers_state="$(echo "show servers state" | nc $LB_POD_IP $LB_STATS_PORT | grep 5432)"
	print_row POD BACKEND ENABLED RECORDS "IN RECOVERY"
	for pod in $db_pods; do
		pod_name=$(echo $pod | cut -d : -f 1)
		pod_ip=$(echo $pod | cut -d : -f 2)
		backend_name=-
		is_enabled=-
		server=$(echo "$servers_state" | grep $pod_ip 2>/dev/null)
		if [ -n "$server" ]; then
			backend_name=$(echo $server | cut -d ' ' -f 2)
			srv_op_state=$(echo $server | cut -d ' ' -f 6)
			is_enabled=$(test "$srv_op_state" == "2" && echo "t" || echo "f")
		fi
		record_count=$(psql -h $pod_ip -Atc "select count(*) from test" 2>/dev/null)
		if [ $? -ne 0 ]; then
			record_count=-
		fi
		in_recovery=$(psql -h $pod_ip -Atc "SELECT pg_is_in_recovery();" 2>/dev/null)
		if [ $? -ne 0 ]; then
			in_recovery=-
		fi
		printf "\t %-13s | %-7s | %-7s | %-7s | %s\n" $pod_name $backend_name $is_enabled $record_count $in_recovery
	done
}

count=0
failed=0
current_lb_stats=""
while true; do
	timeout --preserve-status 1s psql -qc "insert into test (data) values ('some text')" &> /dev/null || failed=$(( $failed + 1 ))
	
	count=$(( $count + 1 ))
	if [ $(( $count % 10 )) -eq 0 ]; then
		current_lb_stats=$(lb_stats)
	fi
	clear
	echo -e "Stats (LB/DB stats are refreshed every 10 insert attempts!)\n"
	echo -e "\tClient inserts: $count attempts, $failed failed\n"
	echo -e "$current_lb_stats"
	sleep 0.05s
done