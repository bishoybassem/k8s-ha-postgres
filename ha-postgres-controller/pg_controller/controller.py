import argparse
import logging
import threading

import psycopg2
import requests

from pg_controller import state
from pg_controller.checks import PostgresAliveCheck, PostgresStandbyReplicationCheck
from pg_controller.workers.election import Election, ElectionStatusHandler
from pg_controller.workers.health_monitor import HealthMonitor
from pg_controller.workers.management import ManagementServer


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):
    """
    Promotes a standby database to master, by executing Postgres's 'pg_promote' sql function against the monitored
    database.
    """

    def __init__(self):
        pass

    def handle_status(self, is_leader):
        """
        Executes 'pg_promote' sql function if the election is won, and the database role is 'Standby'. It also handles
        promotion failures by setting the role to 'DeadMaster'.
        """
        if is_leader is False or state.INSTANCE.role != state.ROLE_STANDBY:
            return

        logging.info('Executing pg_promote()!')
        conn = None
        try:
            conn = psycopg2.connect(user='controller', host='localhost')
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute('SELECT pg_promote(true)')
            result = cursor.fetchall()
            if result[0][0] is not True:
                raise RuntimeError('pg_promote was not successful! (result: %s)' % result)

            state.INSTANCE.role = state.ROLE_MASTER
        except:
            logging.exception('An exception occurred during promotion!')
            state.INSTANCE.role = state.ROLE_DEAD_MASTER
        finally:
            if conn:
                conn.close()

    def continue_participating(self):
        """Returns True if the role is 'Standby'."""
        return state.INSTANCE.role == state.ROLE_STANDBY


class Controller:

    def __init__(self):
        self._worker_threads = []
        self._args = self._parse_args()
        state.INSTANCE = state.State(self._args.consul_key_prefix, self._args.host_name)

    @staticmethod
    def _parse_args():
        parser = argparse.ArgumentParser(description='Controller daemon for ha-postgres')
        parser.add_argument('--consul-key-prefix', default='service/postgres',
                            help='The Consul key path prefix to use for the election key or for storing state')
        parser.add_argument('--check-interval', type=int,
                            help='The time interval (in seconds) between two consecutive health/leader election checks')
        parser.add_argument('--connect-timeout', type=int, default=1,
                            help='The timeout (in seconds) for connecting to Postgres during health checks')
        parser.add_argument('--alive-check-failure-threshold', type=int, default=1,
                            help='The number of consecutive failures for the alive health check to be considered failed')
        parser.add_argument('--standby-replication-check-failure-threshold', type=int, default=4,
                            help='The number of consecutive failures for the standby replication health check '
                                 'to be considered failed')
        parser.add_argument('--management-port', type=int, default=80,
                            help='The port on which the controller exposes the management API')
        parser.add_argument('--host-name', help='The name of this host')
        parser.add_argument('--host-ip', help='The ip of this host')
        return parser.parse_args()

    def _start_alive_health_monitor(self):
        """Starts a monitoring worker thread with the alive health check."""
        health_check = PostgresAliveCheck(self._args.alive_check_failure_threshold, self._args.connect_timeout)
        health_monitor = HealthMonitor(health_check, self._args.check_interval)
        health_monitor.setName("AliveMonitor")
        health_monitor.start()
        self._worker_threads.append(health_monitor)

    def _start_standby_replication_health_monitor(self):
        """Starts a monitoring worker thread with the standby replication health check."""
        health_check = PostgresStandbyReplicationCheck(self._args.standby_replication_check_failure_threshold,
                                                       self._args.connect_timeout)
        health_monitor = HealthMonitor(health_check, self._args.check_interval)
        health_monitor.setName("ReplicationMonitor")
        health_monitor.start()
        self._worker_threads.append(health_monitor)

    @staticmethod
    def _register_consul_service():
        """Registers the 'postgres' service in Consul."""
        logging.info("Registering Consul service: postgres")
        response = requests.put(state.CONSUL_BASE_URL + "/agent/service/register", json={"Name": "postgres"})
        logging.info("Response (%d) %s", response.status_code, response.text)
        response.raise_for_status()

    def _start_election(self,):
        """Starts the election worker thread."""
        election = Election(election_consul_key=self._args.consul_key_prefix + "/master",
                            consul_session_checks=[state.ALIVE_HEALTH_CHECK_NAME,
                                                   state.STANDBY_REPLICATION_HEALTH_CHECK_NAME],
                            election_status_handler=PostgresMasterElectionStatusHandler(),
                            host_name=self._args.host_name,
                            host_ip=self._args.host_ip,
                            check_interval_seconds=self._args.check_interval)
        election.start()
        self._worker_threads.append(election)

    def _start_management_server(self):
        """Starts the management server worker thread."""
        management_server = ManagementServer(self._args.management_port)
        management_server.start()
        self._worker_threads.append(management_server)

    def stop(self, *args):
        """Stops all worker threads, and waits for them to finish."""
        for worker_thread in self._worker_threads:
            worker_thread.stop()
            if worker_thread.is_alive():
                worker_thread.join()

    def start(self):
        """Starts the controller process."""
        threading.current_thread().name = "Controller"
        try:
            self._start_management_server()
            self._start_alive_health_monitor()
            self._start_standby_replication_health_monitor()
            self._register_consul_service()
            state.INSTANCE.wait_till_healthy()
            self._start_election()
            state.INSTANCE.done_initializing()
        except:
            logging.exception("An exception was encountered during startup!")
            self.stop()
