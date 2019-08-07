# HA PostgreSQL on Kubernetes

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
* Monitors election status and constantly tries to acquire the leadership lock. If aquired, it promotes the standby to master via `trigger_file` and updates the master's ClusterIP service to point to its pod. 
* Exposes the health status via an HTTP endpoint `/controller/ready`, that is used by:
  * K8s to determine that the db pod is ready to accept connections (Readiness Probe).
  * DNS to respond with the list of healthy db pods when the headless service is queried.
  * HAProxy to determine whether to keep the connections to the database open or not. This is needed in order to force clients/slaves to retry connecting to the new master in case of a failover.
* Exposes the role via HTTP endpoint `/controller/role`, that is queried by the db container during startup, and would answer with one of the following:
  * `Master`, which causes the db to start as a normal master, and execute init scripts if needed.    
  * `Replica`, which causes the db to create a base backup of the current master (to be used as the starting point for streaming replication), and start in standby mode. 
  * `DeadMaster`, which causes the db container to block during startup, thus giving a chance to the cluster's admin to cleanup the underlying PersistentVolume, and delete this pod. This way, a new db pod would be spawned as a standby with a clean filesystem. 

## Requirements

To test the setup locally, the following needs to be present/installed:
* Docker (used version 18.09.0-ce).
* Minikube (used version 1.0.0, with `none` driver).
* Kubernetes (used version 1.14.0).
* Helm (used version 3.0.0-alpha.1).

## Steps

1. Clone the repository, and navigate to the clone directory.
2. Run the deployment script, which builds the docker images, and installs the helm chart:
   ```bash
   ./deploy-minikube.sh
   ```
   The script also watches the pods, and when the cluster is ready, the output should look like this:
   ```bash
   NAME            READY   STATUS    RESTARTS   AGE
   consul-0        1/1     Running   0          2m2s
   consul-1        1/1     Running   0          103s
   consul-2        1/1     Running   0          95s
   ha-postgres-0   4/4     Running   0          2m2s
   ha-postgres-1   4/4     Running   0          69s
   ha-postgres-2   4/4     Running   0          44s
   ```
3. In another terminal, run the demo script, which would get the master's ClusterIP service, create a test table, and start inserting records using `psql`:
   ```bash
   ./demo.sh
   ```
   The script also outputs some useful stats and keeps refreshing them:
   ```bash
   Stats (DB record counts are refreshed every 10 insert attempts!)

     Client inserts: 259 attempts, 0 failed

     ha-postgres-0: 250 records -> master
     ha-postgres-1: 250 records -> standby
     ha-postgres-2: 250 records -> standby
   ```
4. In a third terminal, simulate a db failure by shutting it down (You might need to execute it twice so that the db container enters `CrashLoopBackOff` state and stays down a bit):
   ```bash
   kubectl exec -it ha-postgres-0 -c postgres -- su -c "/usr/lib/postgresql/11/bin/pg_ctl stop" postgres
   ```
   Notice that the client inserts started to fail, and after a couple of seconds, one of the standbys would be promoted to master, while the other would start replicating from it:
   ```bash
   Stats (DB record counts are refreshed every 10 insert attempts!)

     Client inserts: 599 attempts, 60 failed

     ha-postgres-0: down
     ha-postgres-1: 530 records -> standby
     ha-postgres-2: 530 records -> master
   ```
5. Now that the old master is down, the cluster admin needs to cleanup its PV and delete the pod:
   ```bash
   kubectl exec -it ha-postgres-0 -c postgres -- rm -rf "/var/lib/postgresql/data"
   kubectl delete pod ha-postgres-0
   ```
   After a bit, a new pod is created, starts as a standby, and catches up with the replication: 
   ```bash
   Stats (DB record counts are refreshed every 10 insert attempts!)

     Client inserts: 949 attempts, 60 failed

     ha-postgres-0: 880 records -> standby
     ha-postgres-1: 880 records -> standby
     ha-postgres-2: 880 records -> master
   ```