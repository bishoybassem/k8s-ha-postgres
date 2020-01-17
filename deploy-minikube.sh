#!/bin/bash

docker build -t ha-postgres-controller:1.0.0 ha-postgres-controller/
docker build -t ha-postgres:11.3 ha-postgres/
docker build -t ha-pgbouncer:1.12.0 ha-pgbouncer/

helm uninstall ha-postgres

kubectl wait --for=delete pod -l app=ha-postgres
kubectl delete pvc -l app=ha-postgres

kubectl wait --for=delete pod -l app=consul
kubectl delete pvc -l app=consul

helm install ha-postgres chart/

watch -t kubectl get pods -o wide