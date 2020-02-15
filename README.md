# HA PostgreSQL on Kubernetes

[![Build Status](https://travis-ci.org/bishoybassem/k8s-ha-postgres.svg?branch=master)](https://travis-ci.org/bishoybassem/k8s-ha-postgres)

This project serves as a proof of concept for a highly available PostgreSQL setup using Consul, HAProxy and Kubernetes. Moreover, Helm is used to package and install the database to the cluster.

## Features

The setup features the following:
* A cluster with two db pods at least (StatefulSet), one acting as master and the rest as standbys (streaming replication).
* Which pod gets to be master is based on leader election implemented using Consul. ([guide](https://learn.hashicorp.com/consul/developer-configuration/elections))
* Automatic failover in case the master db's health checks fail. 
* A ClusterIP service always pointing to the current master, to be used for writing/replication by clients/standbys.
* A headless service returning the list of healthy db pods, to be used by clients for reading.

## Implementation
The database pod consists of the following containers:
* __postgres__: the PostgreSQL database process.
* __haproxy__: listens for client connections, and proxies them to the db container within the same pod.
* __consul__: the Consul agent running in client mode. 
* __controller__: a multithreaded process written in Python that orchestrates the whole workflow. 

The __controller__ process is the one that drives the cluster to be highly available, it maintains the state within each database pod, and controls its components accordingly. The __controller__ has the following responsibilities:
* Executes the health check for db, and updates Consul's check accordingly. In case it fails, Consul would then release the leadership lock, allowing any standby pod to take over the master/leader role.
* Monitors election status and constantly tries to acquire the leadership lock. If aquired, it promotes the standby to master by executing `pg_promote()` and updates the master's ClusterIP service to point to its pod. 
* Exposes the health status via an HTTP endpoint `/controller/ready`, that is used by:
  * K8s to determine that the db pod is ready to accept connections (Readiness Probe).
  * DNS to respond with the list of healthy db pods when the headless service is queried.
  * HAProxy to determine whether to keep the connections to the database open or not. This is needed in order to force clients/slaves to retry connecting to the new master in case of a failover.
* Exposes the role via HTTP endpoint `/controller/role`, that is queried by the db container during startup, and would answer with one of the following:
  * `Master`, which causes the db to start as a normal master, and execute init scripts if needed.    
  * `Replica`, which causes the db to create a base backup of the current master (to be used as the starting point for streaming replication), and start in standby mode. 
  * `DeadMaster`, which causes the db container to block during startup/restarts.

Finally, deleting a dead master db pod, would spawn a new one whose init container __wait-pgdata-empty__ would block if the db's PersistentVolume contains data. This way, the cluster's admin would get a chance to clean up the PV, signal the init container to proceed, and then the db pod would start as a standby with a clean filesystem. 

## Requirements

To test the setup locally, the following needs to be present/installed:
* Docker (used version 19.03.5-ce).
* Minikube (used version 1.6.2, with `none` driver).
* Kubernetes (used version 1.17.0).
* Helm (used version 3.0.2).

## Steps

1. Clone the repository, and navigate to the clone directory.
2. Run the chart deployment script, which builds the docker images, installs the helm chart, and waits for the cluster to be ready:
   ```bash
   ./scripts/deploy-chart.sh
   ```
3. Monitor the cluster state by running the following:
   ```bash
   watch -t kubectl get pods
   ```
   The watch command will keep refreshing the pods' info, and the output should look like this:
   ```bash
   NAME            READY   STATUS    RESTARTS   AGE
   consul-0        1/1     Running   0          2m
   consul-1        1/1     Running   0          110s
   consul-2        1/1     Running   0          103s
   ha-postgres-0   4/4     Running   0          2m
   ha-postgres-1   4/4     Running   0          65s
   ha-postgres-2   4/4     Running   0          31s
   ```
4. In another terminal, run the demo script, which would get the master's ClusterIP service, create a test table, and start inserting records using `psql`:
   ```bash
   ./scripts/demo.sh
   ```
   The script also outputs some useful stats and keeps refreshing them:
   ```bash
   Stats (DB record counts are refreshed every 10 insert attempts!)

     Client inserts: 283 attempts, 0 failed

     ha-postgres-0: 280 records -> master
     ha-postgres-1: 280 records -> standby
     ha-postgres-2: 280 records -> standby
   ```
5. In a third terminal, overload the master db's cpu as follows:
   ```bash
   kubectl exec -it ha-postgres-0 -c postgres bash
   apt-get update
   apt-get install -y stress
   stress --cpu 1000 -t 20s
   ```
   Notice that the client inserts started to fail, and shortly, one of the standbys would be promoted to master, while the other would start replicating from it:
   ```bash
   Stats (DB record counts are refreshed every 10 insert attempts!)

     Client inserts: 415 attempts, 92 failed

     ha-postgres-0: down
     ha-postgres-1: 318 records -> master
     ha-postgres-2: 318 records -> standby
   ```
6. Now that the old master is down, the cluster admin needs to delete the pod, and cleanup its PV as follows:
   ```bash
   kubectl delete pod ha-postgres-0
   # Wait for the replacement pod to be created
   kubectl exec -it ha-postgres-0 -c wait-pgdata-empty sh
   rm -rf /pgdata/*
   touch /proceed
   ```
   The pod would then start as a standby, and catch up with the replication: 
   ```bash
   Stats (DB record counts are refreshed every 10 insert attempts!)

     Client inserts: 1246 attempts, 92 failed

     ha-postgres-0: 1148 records -> standby
     ha-postgres-1: 1148 records -> master
     ha-postgres-2: 1148 records -> standby
   ```