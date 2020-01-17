import sys
import psycopg2
import logging
import argparse
import threading
import signal
import requests
from kubernetes import client, config
from pg_controller import state
from pg_controller.workers.election import Election, ElectionStatusHandler
from pg_controller.workers.health_monitor import HealthMonitor, HealthCheck
from pg_controller.workers.management import ManagementServer


class PgBouncerHealthCheck(HealthCheck):

    def __init__(self, db, db_user, pgbouncer_admin_user):
        self._db = db
        self._db_user = db_user
        self._pgbouncer_admin_user = pgbouncer_admin_user

    def do_health_check(self):
        try:
            conn = psycopg2.connect(database=self._db, user=self._db_user, host="localhost", port=6432,
                                    connect_timeout=1)
            conn.cursor().execute("SELECT 1")
            logging.info("PgBouncer/Postgres is healthy!")
            return True
        except psycopg2.Error:
            logging.exception("PgBouncer/Postgres is not healthy!")

        if state.INSTANCE.initialized:
            self._kill_db_connections()

        return False

    def check_updated(self, is_healthy):
        state.INSTANCE.healthy = is_healthy

    def check_update_failed(self):
        state.INSTANCE.healthy = False

    def _kill_db_connections(self):
        try:
            conn = psycopg2.connect(database="pgbouncer", user=self._pgbouncer_admin_user, host="localhost", port=6432)
            conn.autocommit = True
            conn.cursor().execute("KILL " + self._db)
            logging.info("Db connections were killed!")
        except psycopg2.Error:
            logging.exception("An error occurred while trying to kill the db connections!")


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):

    def __init__(self, promote_trigger_file, master_service, pod_ip):
        self._promote_trigger_file = promote_trigger_file
        self._master_service = master_service
        self._pod_ip = pod_ip

        config.load_incluster_config()
        self._current_namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    def handle_status(self, is_leader):
        state.INSTANCE.role = state.ROLE_MASTER if is_leader else state.ROLE_REPLICA

        if is_leader:
            self._update_master_endpoint()
            logging.info("Creating trigger file for master promotion!")
            open(self._promote_trigger_file, "w").close()

        continue_trying = not is_leader
        return continue_trying

    def _update_master_endpoint(self):
        logging.info("Updating k8s master service to point to %s!" % self._pod_ip)
        api_instance = client.CoreV1Api()
        body = {
           "subsets": [
              {
                 "addresses": [{"ip": self._pod_ip}],
                 "ports": [
                    {"name": "pgbouncer", "port": 6432}, 
                    {"name": "postgres", "port": 5432}
                 ]
              }
           ]
        }
        api_instance.patch_namespaced_endpoints(self._master_service, self._current_namespace, body)


HEALTH_CHECK_NAME = "postgresAlive"
ELECTION_CONSUL_KEY = "service/postgres/master"
worker_threads = []


def get_args():
    parser = argparse.ArgumentParser(description='Controller daemon for ha-postgres')
    parser.add_argument('--time-step', type=int,
                        help='The period (in seconds) to wait between checks/updates for health monitoring and '
                             'leader election')
    parser.add_argument('--management-port', type=int, default=80,
                        help='The port on which the controller exposes the management API')
    parser.add_argument('--health-check-db',
                        help='The name of the database to use for the test connection to pgbouncer')
    parser.add_argument('--health-check-db-user',
                        help='The user to use for the test connection to pgbouncer')
    parser.add_argument('--pgbouncer-admin-user',
                        help='The pgbouncer user to use to kill the db connections in case of failure.')
    parser.add_argument('--promote-trigger-file',
                        help='The file that triggers replica to master promotion')
    parser.add_argument('--master-service',
                        help='The name of the k8s service pointing to the current master')
    parser.add_argument('--pod-ip',
                        help='The ip of this pod')

    return parser.parse_args()


def set_initial_role():
    response = requests.get(Election.CONSUL_KV_URL.format(ELECTION_CONSUL_KEY))
    if response.status_code == 404:
        state.INSTANCE.role = state.ROLE_MASTER
    elif response.status_code == 200:
        state.INSTANCE.role = state.ROLE_REPLICA
    else:
        response.raise_for_status()


def start_health_monitor(args):
    health_check = PgBouncerHealthCheck(args.health_check_db, args.health_check_db_user, args.pgbouncer_admin_user)
    health_monitor = HealthMonitor(HEALTH_CHECK_NAME, health_check, args.time_step)
    health_monitor.start()
    worker_threads.append(health_monitor)


def start_election(args):
    election = Election(ELECTION_CONSUL_KEY,
                        [HEALTH_CHECK_NAME],
                        PostgresMasterElectionStatusHandler(args.promote_trigger_file,
                                                            args.master_service, args.pod_ip),
                        args.time_step)
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
        start_management_server(args)
        set_initial_role()
        start_health_monitor(args)
        state.INSTANCE.wait_till_healthy()
        start_election(args)
        state.INSTANCE.done_initializing()
    except:
        logging.exception("An exception was encountered during startup!")
        stop()
