#!/bin/bash -e

function quit() {
	exit 0
}

trap quit INT TERM 

echo "Waiting for db pods to be ready..."
kubectl wait --for=condition=Ready pod -l app=ha-postgres

master_service_ip=$(kubectl get svc postgres-master -o jsonpath='{.spec.clusterIP}')
echo "Master db service ip $master_service_ip"

export PGHOST=${master_service_ip}
export PGUSER=postgres
export PGPASSWORD=su123
export PGDATABASE=postgres
export PGPORT=5433
export PGCONNECT_TIMEOUT=1
echo "Creating test table ..."
psql -qc "create table if not exists test(id serial, data text)"

function db_stats() {
	db_pods=$(kubectl get pods -l app=ha-postgres -o jsonpath='{range .items[*]}{.metadata.name}_{.status.podIP} {end}')
	for pod in $db_pods; do
		pod_name=$(echo $pod | cut -d _ -f 1)
		pod_ip=$(echo $pod | cut -d _ -f 2)
		record_count=$(psql -h $pod_ip -Atc "select count(*) from test" 2>&1)
		if [ $? -ne 0 ]; then
			echo "\t$pod_name: down"
			continue
		fi
		role=master
		in_recovery=$(psql -h $pod_ip -Atc "SELECT pg_is_in_recovery();" 2>&1)
		if [ "${in_recovery}" == "t" ]; then
			role=standby
		fi 
		echo "\t$pod_name: ${record_count} records -> ${role}"
	done
}

count=0
failed=0
current_db_stats=""
while true; do
	timeout --preserve-status 1s psql -qc "insert into test (data) values ('some text')" &> /dev/null || failed=$(( $failed + 1 ))
	
	count=$(( $count + 1 ))
	if [ $(( $count % 10 )) -eq 0 ]; then
		current_db_stats=$(db_stats)
	fi
	clear
	echo -e "Stats (DB record counts are refreshed every 10 insert attempts!)\n"
	echo -e "\tClient inserts: $count attempts, $failed failed\n"
	echo -e "$current_db_stats"
	sleep 0.05s
done