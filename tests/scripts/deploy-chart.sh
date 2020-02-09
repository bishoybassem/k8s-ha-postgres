#!/bin/bash -e

docker build -t ha-postgres-controller:1.0.0 ha-postgres-controller/
docker build -t ha-postgres:12.1 ha-postgres/

if helm ls | grep -Fq ha-postgres; then
	helm uninstall ha-postgres
	kubectl wait --for=delete pods -l 'app in (consul, ha-postgres)'
	kubectl delete pvc -l 'app in (consul, ha-postgres)' --wait
fi

helm install -f chart/values.yaml ${1:+-f $1} ha-postgres chart/

postgres_count=$(kubectl get statefulset ha-postgres -o jsonpath='{.spec.replicas}')
for i in $(seq 0 $((postgres_count - 1))); do 
	kubectl wait --for=condition=Ready pod ha-postgres-$i --timeout 2m
done