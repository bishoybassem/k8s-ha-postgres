import logging
import unittest

from kubernetes import client, stream
from psycopg2 import OperationalError
from retry.api import retry_call

import test_utils


class IntegrationTest(unittest.TestCase):

    def test1_replication(self):
        master_pod_ip = self.assert_lb_backend_state("master", 1)[0][1]

        table_name, table_row_count = test_utils.create_table_in_seed_db()
        logging.info("Checking that the main db cluster is logically replicating from the seed one")
        retry_call(self.assert_table_size, fargs=[master_pod_ip, table_name, table_row_count], tries=3, delay=3)

        standby_pods = self.assert_lb_backend_state("standby", 2)

        standby_pods_ips = [pod[1] for pod in standby_pods]
        self.assertNotIn(master_pod_ip, standby_pods_ips)

        for pod_name, pod_ip in standby_pods:
            logging.info("Checking that the standby pod %s (main db cluster) is replicating from its master", pod_name)
            retry_call(self.assert_table_size, fargs=[pod_ip, table_name, table_row_count], tries=3, delay=3)

    def test2_failover(self):
        master_pod_name, master_pod_ip = self.assert_lb_backend_state("master", 1)[0]
        logging.info("Current master db pod is %s with ip %s", master_pod_name, master_pod_ip)

        logging.info("Opening connections to the master through the lb service")
        master_conns = [test_utils.open_db_conn(test_utils.LB_SVC_IP) for _ in range(10)]

        logging.info("Opening connections to the standbys through the lb service")
        standby_conns = [test_utils.open_db_conn(test_utils.LB_SVC_IP, test_utils.STANDBY_DB_PORT) for _ in range(10)]

        test_utils.start_db_pod_stress(master_pod_name)

        logging.info("Waiting for the lb to mark the master pod as not healthy")
        retry_call(self.assert_lb_backend_state, fargs=["master", 0], tries=10, delay=3)

        logging.info("Checking that all master connections are closed")
        for conn in master_conns:
            self.assert_conn_is_closed(conn[0])

        logging.info("Checking that new connections can not be opened to the master through the lb service")
        with self.assertRaises(OperationalError):
            test_utils.open_db_conn(test_utils.LB_SVC_IP)

        logging.info("Checking that a new master is elected, and that the lb is updated accordingly")
        new_master_pod_ip = retry_call(self.assert_lb_backend_state, fargs=["master", 1],
                                       tries=10, delay=3)[0][1]
        self.assertNotEqual(master_pod_ip, new_master_pod_ip)

        logging.info("Checking that the standby connections opened to the new master are closed")
        for standby_conn in [conn[0] for conn in standby_conns if conn[1] == new_master_pod_ip]:
            retry_call(self.assert_conn_is_closed, fargs=[standby_conn], tries=3, delay=3)

        logging.info("Checking that the remaining standby connections are still open")
        for standby_conn in [conn[0] for conn in standby_conns if conn[1] != new_master_pod_ip]:
            standby_conn.cursor().execute('SELECT 1')
            standby_conn.close()

        self.__class__.dead_master_db_pod_name = master_pod_name

    def test3_replication_after_failover(self):
        master_pod_ip = self.assert_lb_backend_state("master", 1)[0][1]
        standby_pod_name, standby_pod_ip = self.assert_lb_backend_state("standby", 1)[0]

        self.assertNotEqual(master_pod_ip, standby_pod_ip, "Expected master and standby ips to be different")

        table_name, table_row_count = test_utils.create_table()
        logging.info("Checking table size on %s", standby_pod_name)
        retry_call(self.assert_table_size, fargs=[standby_pod_ip, table_name, table_row_count], tries=3, delay=3)

    def test4_old_master_cleanup(self):
        dead_master_db_pod_name = self.__class__.dead_master_db_pod_name

        logging.info("Deleting the dead master pod %s", dead_master_db_pod_name)
        test_utils.API_INSTANCE.delete_namespaced_pod(dead_master_db_pod_name, test_utils.MAIN_NAMESPACE)

        logging.info("Waiting for the newly created pod to start, and block for pgdata cleanup")
        retry_call(self.assert_db_pod_is_waiting_for_pgdata_cleanup, fargs=[dead_master_db_pod_name],
                   tries=10, delay=3)

        test_utils.clean_pgdata(dead_master_db_pod_name)

        logging.info("Waiting for the newly created pod to be added to the lb standby backend")
        standby_pods = retry_call(self.assert_lb_backend_state, fargs=["standby", 2], tries=30, delay=3)

        standby_pods_names = [pod[0] for pod in standby_pods]
        self.assertIn(dead_master_db_pod_name, standby_pods_names)

    def test5_standby_failure(self):
        standby_pods = self.assert_lb_backend_state("standby", 2)

        logging.info("Opening connections to the standbys through the lb service")
        conns = [test_utils.open_db_conn(test_utils.LB_SVC_IP, test_utils.STANDBY_DB_PORT) for _ in range(10)]

        for pod in standby_pods:
            test_utils.kill_wal_receiver_continuously(pod[0])

        logging.info("Waiting for the lb to mark the standbys as not healthy")
        retry_call(self.assert_lb_backend_state, fargs=["standby", 0], tries=20, delay=3)

        logging.info("Checking that all opened connections are closed")
        for conn in conns:
            self.assert_conn_is_closed(conn[0])

        logging.info("Checking that new connections can not be opened to the standbys through the lb service")
        with self.assertRaises(OperationalError):
            test_utils.open_db_conn(test_utils.LB_SVC_IP, test_utils.STANDBY_DB_PORT)

        logging.info("Waiting for the lb to enable back the standby pods")
        retry_call(self.assert_lb_backend_state, fargs=["standby", 2], tries=10, delay=3)

        logging.info("Check that the lb accepts new connections for the standby backend")
        test_utils.open_db_conn(test_utils.LB_SVC_IP, test_utils.STANDBY_DB_PORT)[0].close()

    def assert_table_size(self, db_host_ip, table_name, expected_row_count):
        query = "SELECT count(*) FROM " + table_name
        row_count = test_utils.execute_query(db_host_ip, 5432, query)[0][0]
        self.assertEqual(expected_row_count, row_count)

    def assert_conn_is_closed(self, conn):
        with self.assertRaises(OperationalError) as cm:
            conn.cursor().execute('SELECT 1')

        self.assertTrue(str(cm.exception).startswith("server closed the connection unexpectedly"),
                        "OperationalError message not as expected")

    def assert_lb_backend_state(self, backend, enabled_count):
        servers = test_utils.get_lb_backend_servers(backend)
        logging.info("Current %s backend state: %s", backend, servers)

        enabled_servers = list(filter(lambda server: server[2] == '2', servers))
        self.assertEqual(enabled_count, len(enabled_servers),
                         "Expected %d enabled servers, got: %s" % (enabled_count, len(enabled_servers)))

        enabled_pods = [(test_utils.get_pod_name_by_ip(server[1]), server[1]) for server in enabled_servers]
        return enabled_pods

    def assert_db_pod_is_waiting_for_pgdata_cleanup(self, pod_name):
        output = stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, pod_name, test_utils.MAIN_NAMESPACE,
                               container='clean-data', command=['pgrep', 'sleep'], stderr=True,
                               stdin=False, stdout=True, tty=False)

        self.assertTrue(output.isdigit(), "Expected a process number as output, but none found!")
