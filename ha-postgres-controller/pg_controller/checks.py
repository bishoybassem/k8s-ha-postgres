import logging

import psycopg2

from pg_controller import state
from pg_controller.workers.health_monitor import HealthCheck


class PostgresAliveCheck(HealthCheck):

    def __init__(self, failure_threshold):
        super().__init__(state.ALIVE_HEALTH_CHECK_NAME, failure_threshold)

    def do_health_check_impl(self):
        conn = None
        try:
            conn = psycopg2.connect(user="controller", host="localhost", connect_timeout=1)
            conn.cursor().execute("SELECT 1")
            logging.info("Postgres is alive!")
            return True
        except psycopg2.Error:
            logging.exception("Postgres is not alive!")
            return False
        finally:
            if conn:
                conn.close()

    def check_updated(self, is_passing):
        state.INSTANCE.set_health_check(state.ALIVE_HEALTH_CHECK_NAME, is_passing)

    def check_update_failed(self):
        state.INSTANCE.set_health_check(state.ALIVE_HEALTH_CHECK_NAME, False)


class PostgresStandbyReplicationCheck(HealthCheck):

    def __init__(self, failure_threshold):
        super().__init__(state.STANDBY_REPLICATION_HEALTH_CHECK_NAME, failure_threshold)

    def do_health_check_impl(self):
        if state.INSTANCE.role != state.ROLE_REPLICA:
            logging.info("Skipping check as the role is not Replica!")
            return True

        conn = None
        try:
            conn = psycopg2.connect(user="controller", host="localhost", connect_timeout=1)
            cursor = conn.cursor()
            cursor.execute("SELECT wal_receiver_status()")
            wal_receiver_status = cursor.fetchone()[0]
            if wal_receiver_status != "streaming":
                logging.error("Postgres is not replicating! (wal receiver status: %s, occurrence #%d)",
                              wal_receiver_status, self._failure_count + 1)
                return False

            logging.info("Postgres is replicating!")
            return True
        except psycopg2.Error:
            logging.exception("Postgres is not replicating!")
            return False
        finally:
            if conn:
                conn.close()

    def check_updated(self, is_passing):
        state.INSTANCE.set_health_check(state.STANDBY_REPLICATION_HEALTH_CHECK_NAME, is_passing)

    def check_update_failed(self):
        pass