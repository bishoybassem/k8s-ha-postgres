#!/bin/bash 

kubectl wait --for=condition=Ready pod -l app=postgres

master_service_ip=$(kubectl get svc postgres-master -o json | jq .spec.clusterIP -r)

export PGPASSWORD=su123

psql -h ${master_service_ip} -U postgres <<-EOF
	create table if not exists test1(
		data text
	);
EOF

count=0
while true; do
	sleep 0.1s
	psql -h ${master_service_ip} -U postgres <<-EOF
		insert into test1 values ('$count record');
	EOF
	count=$(( $count + 1 ))
done