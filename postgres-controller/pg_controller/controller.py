import sys
import psycopg2
import logging
import argparse
import threading
import signal
from kubernetes import client, config
from pg_controller import state
from pg_controller.workers.election import Election, ElectionStatusHandler
from pg_controller.workers.health_monitor import HealthMonitor, HealthCheck
from pg_controller.workers.management import ManagementServer


class PostgresHealthCheck(HealthCheck):

    def __init__(self, db, db_user):
        self._db = db
        self._db_user = db_user

    def do_health_check(self):
        try:
            conn = psycopg2.connect(database=self._db, user=self._db_user, host="localhost", connect_timeout=1)
            conn.cursor().execute("SELECT 1")
            state.INSTANCE.done_initializing()
            logging.info("Postgres is healthy!")
            return True
        except psycopg2.Error:
            if state.INSTANCE.initializing:
                logging.info("Postgres is still initializing!")
            else:
                state.INSTANCE.did_fail()
                logging.exception("Postgres is not healthy!")

            return state.INSTANCE.initializing


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):

    def __init__(self, promote_trigger_file, pod_ip):
        self._promote_trigger_file = promote_trigger_file
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
        api_instance = client.CoreV1Api()
        body = {
           "subsets": [
              {
                 "addresses": [{"ip": self._pod_ip}],
                 "ports": [{"port": 5432}]
              }
           ]
        }
        api_instance.patch_namespaced_endpoints("postgres-master", self._current_namespace, body)


HEALTH_CHECK_NAME = "postgresAlive"
worker_threads = []


def get_args():
    parser = argparse.ArgumentParser(description='Controller daemon for postgres')
    parser.add_argument('--time-step', type=int,
                        help='The period (in seconds) to wait between checks/updates for health monitoring and '
                             'leader election')
    parser.add_argument('--management-port', type=int, default=80,
                        help='The port on which the controller exposes the management API')
    parser.add_argument('--health-check-db',
                        help='The name of the database to use for the test connection to postgres')
    parser.add_argument('--health-check-db-user',
                        help='The user to use for the test connection to postgres')
    parser.add_argument('--promote-trigger-file',
                        help='The file that triggers replica to master promotion')
    parser.add_argument('--pod-ip',
                        help='')

    return parser.parse_args()


def start_health_monitor(args):
    health_monitor = HealthMonitor(HEALTH_CHECK_NAME,
                                   PostgresHealthCheck(args.health_check_db, args.health_check_db_user),
                                   args.time_step)
    health_monitor.start()
    worker_threads.append(health_monitor)


def start_election(args):
    election = Election("service/postgres/master",
                        ["serfHealth", HEALTH_CHECK_NAME],
                        PostgresMasterElectionStatusHandler(args.promote_trigger_file, args.pod_ip),
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
        start_health_monitor(args)
        start_election(args)
        start_management_server(args)
    except:
        logging.exception("An exception was encountered during startup!")
        stop()
