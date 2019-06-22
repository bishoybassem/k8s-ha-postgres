import sys
import psycopg2
import logging
import argparse
import threading
from os import path
from election import Election, ElectionStatusHandler
from health_monitor import HealthMonitor, HealthCheck


class PostgresHealthCheck(HealthCheck):

    def __init__(self, db, db_user):
        self._db = db
        self._db_user = db_user
        self._initializing = True

    def do_health_check(self):
        try:
            conn = psycopg2.connect(database=self._db, user=self._db_user, host="localhost")
            conn.cursor().execute("SELECT 1")
            self._initializing = False
            logging.info("Postgres is healthy!")
            return True
        except psycopg2.Error:
            logging.exception("Postgres is not healthy! Ignore if still initializing "
                              "(_initializing: %s)" % self._initializing)
            return self._initializing


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):

    def __init__(self, state_dir):
        self._state_dir = state_dir

    def handle_status(self, is_leader):
        with open(path.join(self._state_dir, "role"), "w") as role_file:
            role_file.write("master" if is_leader else "slave")

        return True


def main():
    parser = argparse.ArgumentParser(description='Controller daemon for postgres')
    parser.add_argument('--time-step', type=int,
                        help='The period (in seconds) to wait between checks/updates for health monitoring and '
                             'leader election')
    parser.add_argument('--state-dir', type=directory,
                        help='The directory where the controller stores its status '
                             '(must be mounted to the postgres container)')
    parser.add_argument('--health-check-db',
                        help='The name of the database to use for the test connection to postgres')
    parser.add_argument('--health-check-db-user',
                        help='The user to use for the test connection to postgres')

    args = parser.parse_args()

    threading.current_thread().name = "Controller"
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='[%(asctime)s][%(threadName)s] %(levelname)s: %(message)s')

    health_check_name = "postgresAlive"
    health_monitor = HealthMonitor(health_check_name,
                                   PostgresHealthCheck(args.health_check_db, args.health_check_db_user),
                                   args.time_step)
    health_monitor.start()

    election = Election("service/postgres/master",
                        ["serfHealth", health_check_name],
                        PostgresMasterElectionStatusHandler(args.state_dir),
                        args.time_step)
    election.start()
    election.join()


def directory(dir_path):
    if path.isdir(dir_path):
        return dir_path
    else:
        raise argparse.ArgumentTypeError("%s is not a valid directory!" % dir_path)


if __name__ == '__main__':
    main()
