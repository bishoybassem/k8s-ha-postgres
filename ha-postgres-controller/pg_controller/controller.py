import argparse
import logging
import signal
import sys
import threading

import psycopg2
import requests
from kubernetes import client, config

from pg_controller import state
from pg_controller.checks import PostgresAliveCheck, PostgresStandbyReplicationCheck
from pg_controller.workers.election import Election, ElectionStatusHandler
from pg_controller.workers.health_monitor import HealthMonitor
from pg_controller.workers.management import ManagementServer


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):

    def __init__(self, master_service, pod_ip, db_port):
        self._master_service = master_service
        self._pod_ip = pod_ip
        self._db_port = db_port

        config.load_incluster_config()
        self._current_namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    def handle_status(self, is_leader):
        if is_leader:
            if state.INSTANCE.role == state.ROLE_REPLICA:
                self._promote()

            self._update_master_endpoint()
            state.INSTANCE.role = state.ROLE_MASTER
            return False
        else:
            state.INSTANCE.role = state.ROLE_REPLICA
            # Return true to signal the election thread to keep trying.
            return True

    @staticmethod
    def _promote():
        logging.info("Executing pg_promote()!")
        conn = None
        try:
            conn = psycopg2.connect(user="controller", host="localhost")
            conn.autocommit = True
            conn.cursor().execute("SELECT pg_promote(false);")
        finally:
            if conn:
                conn.close()

    def _update_master_endpoint(self):
        logging.info("Updating k8s master service to point to %s!" % self._pod_ip)
        api_instance = client.CoreV1Api()
        body = {
           "subsets": [
              {
                 "addresses": [{"ip": self._pod_ip}],
                 "ports": [{"port": int(self._db_port)}]
              }
           ]
        }
        api_instance.patch_namespaced_endpoints(self._master_service, self._current_namespace, body)


ELECTION_CONSUL_KEY = "service/postgres/master"
worker_threads = []


def get_args():
    parser = argparse.ArgumentParser(description='Controller daemon for ha-postgres')
    parser.add_argument('--time-step', type=int,
                        help='The period (in seconds) to wait between checks/updates for health monitoring and '
                             'leader election')
    parser.add_argument('--alive-check-failure-threshold', type=int, default=1,
                        help='The number of failures after which the alive health check would be considered failed')
    parser.add_argument('--standby-replication-check-failure-threshold', type=int, default=3,
                        help='The number of failures after which the standby replication health check '
                             'would be considered failed')
    parser.add_argument('--management-port', type=int, default=80,
                        help='The port on which the controller exposes the management API')
    parser.add_argument('--master-service',
                        help='The name of the k8s service pointing to the current master')
    parser.add_argument('--pod-ip',
                        help='The ip of this pod')
    parser.add_argument('--db-port',
                        help='The public port for the database that HAProxy listens to')

    return parser.parse_args()


def set_initial_role():
    response = requests.get(Election.CONSUL_KV_URL.format(ELECTION_CONSUL_KEY))
    if response.status_code == 404:
        state.INSTANCE.role = state.ROLE_MASTER
    elif response.status_code == 200:
        state.INSTANCE.role = state.ROLE_REPLICA
    else:
        response.raise_for_status()


def start_alive_health_monitor(args):
    health_check = PostgresAliveCheck(args.alive_check_failure_threshold)
    health_monitor = HealthMonitor(health_check, args.time_step)
    health_monitor.setName("AliveMonitor")
    health_monitor.start()
    worker_threads.append(health_monitor)


def start_standby_replication_health_monitor(args):
    health_check = PostgresStandbyReplicationCheck(args.standby_replication_check_failure_threshold)
    health_monitor = HealthMonitor(health_check, args.time_step)
    health_monitor.setName("ReplicationMonitor")
    health_monitor.start()
    worker_threads.append(health_monitor)


def start_election(args):
    handler = PostgresMasterElectionStatusHandler(args.master_service,
                                                  args.pod_ip, args.db_port)

    election = Election(ELECTION_CONSUL_KEY,
                        [state.ALIVE_HEALTH_CHECK_NAME, state.STANDBY_REPLICATION_HEALTH_CHECK_NAME],
                        handler, args.time_step)
    election.start()
    worker_threads.append(election)


def start_management_server(args):
    management_server = ManagementServer(args.management_port)
    management_server.start()
    worker_threads.append(management_server)


def stop(*args):
    for worker_thread in worker_threads:
        worker_thread.stop()
        if worker_thread.is_alive():
            worker_thread.join()


def start():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='[%(asctime)s][%(threadName)s] %(levelname)s: %(message)s')

    signal.signal(signal.SIGTERM, stop)

    threading.current_thread().name = "Controller"
    args = get_args()

    try:
        set_initial_role()
        start_management_server(args)
        start_alive_health_monitor(args)
        start_standby_replication_health_monitor(args)
        state.INSTANCE.wait_till_healthy()
        start_election(args)
        state.INSTANCE.done_initializing()
    except:
        logging.exception("An exception was encountered during startup!")
        stop()
