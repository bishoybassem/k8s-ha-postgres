import sys
import psycopg2
import logging
import argparse
import threading
import signal
import state
from election import Election, ElectionStatusHandler
from health_monitor import HealthMonitor, HealthCheck
from management import ManagementServer


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
                logging.exception("Postgres is not healthy!")

            return state.INSTANCE.initializing


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):

    def handle_status(self, is_leader):
        state.INSTANCE.role = state.ROLE_MASTER if is_leader else state.ROLE_SLAVE

        return True


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
                        PostgresMasterElectionStatusHandler(),
                        args.time_step)
    election.start()
    worker_threads.append(election)


def start_management_server(args):
    management_server = ManagementServer(args.management_port)
    management_server.start()
    worker_threads.append(management_server)


def stop(signum, frame):
    for worker_thread in worker_threads:
        worker_thread.stop()
        if worker_thread.is_alive():
            worker_thread.join()


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='[%(asctime)s][%(threadName)s] %(levelname)s: %(message)s')

    signal.signal(signal.SIGTERM, stop)

    threading.current_thread().name = "Controller"
    args = get_args()
    start_health_monitor(args)
    start_election(args)
    start_management_server(args)


if __name__ == '__main__':
    main()
