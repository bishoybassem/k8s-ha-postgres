#!/bin/bash

docker build -t postgres-controller:1.0.0 postgres-controller/
docker build -t postgres-ha:11.3 postgres-ha/

helm uninstall postgres;

kubectl wait --for=delete pod -l app=postgres
kubectl delete pvc -l app=postgres

kubectl wait --for=delete pod -l app=consul
kubectl delete pvc -l app=consul

helm install postgres postgres-chart/