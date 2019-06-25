#!/bin/bash

docker build -t postgres-controller:1.0.0 postgres-controller/
docker build -t postgres-ha:11.3 postgres-ha/

helm uninstall postgres;

kubectl delete pvc postgres-data-postgres-0 postgres-data-postgres-1 postgres-data-postgres-2

helm install postgres postgres-chart/