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

echo "Creating test table ..."
psql -qc "create table if not exists test(id serial, data text)"

function db_stats() {
	db_count=$(kubectl get statefulset ha-postgres -o jsonpath='{.status.replicas}')
	for i in $(seq 0 $(( db_count - 1 ))); do
		record_count=$(kubectl exec -it ha-postgres-$i -c postgres -- psql -Atc "select count(*) from test" -U postgres 2>&1)
		if [ $? -ne 0 ]; then
			echo "\tha-postgres-$i: down"
			continue
		fi
		role=master
		in_recovery=$(kubectl exec -it ha-postgres-$i -c postgres -- psql -Atc "SELECT pg_is_in_recovery();" -U postgres 2>&1)
		if [ "${in_recovery%?}" == "t" ]; then
			role=standby
		fi 
		echo "\tha-postgres-$i: ${record_count%?} records -> ${role}"
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