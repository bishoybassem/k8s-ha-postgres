import logging
import random
import re
import sys
import unittest

import psycopg2
from kubernetes import client, config, stream
from psycopg2 import OperationalError
from retry.api import retry_call

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s: %(message)s')


class IntegrationTest(unittest.TestCase):

    def setUp(self):
        config.load_kube_config()
        self._api_instance = client.CoreV1Api()
        self._master_svc_ip = self._api_instance.read_namespaced_service('postgres-master', 'default').spec.cluster_ip

    def test1_replication(self):
        all_db_pods = self.get_all_db_pods()
        self.assertEquals(len(all_db_pods), 3)

        table_name, table_row_count = self.create_table()
        for db_pod_name, db_pod_ip in all_db_pods.items():
            logging.info("Checking table size on %s", db_pod_name)
            retry_call(self.assert_table_size, fargs=[db_pod_ip, table_name, table_row_count], tries=5, delay=1)

    def test2_failover(self):
        master_db_pod_name, master_db_pod_ip = self.get_master_db_pod()
        logging.info("Current master db pod is %s with ip %s", master_db_pod_name, master_db_pod_ip)

        standby_db_pods = self.get_read_db_pods()
        del standby_db_pods[master_db_pod_name]

        logging.info("Opening connections to the master service")
        master_conns = [self.open_db_conn(self._master_svc_ip) for _ in range(10)]

        standby_conns = []
        for standby_db_pod_name, standby_db_pod_ip in standby_db_pods.items():
            logging.info("Opening connections to standby db pod: %s", standby_db_pod_name)
            standby_conns += [self.open_db_conn(standby_db_pod_ip) for _ in range(10)]

        self.start_db_pod_stress(master_db_pod_name)

        logging.info("Waiting for the master db pod to become NotReady")
        retry_call(self.assert_pod_is_not_ready, fargs=[master_db_pod_name], tries=10, delay=3)

        logging.info("Checking that all opened connections to master are closed")
        for conn in master_conns:
            retry_call(self.assert_conn_is_closed, fargs=[conn], tries=5, delay=1)

        logging.info("Checking that new connections can not be opened to the failed master")
        with self.assertRaises(OperationalError):
            self.open_db_conn(master_db_pod_ip)

        logging.info("Checking that all opened connections to standby db pods are still open")
        for conn in standby_conns:
            conn.cursor().execute('SELECT 1')

        logging.info("Checking that a new master is elected, and that the master service is updated accordingly")
        retry_call(self.assert_master_service_changed, fargs=[master_db_pod_name], tries=10, delay=3)

        logging.info("Checking that the read service excludes the old master db pod")
        retry_call(self.assert_read_service_excludes_pod, fargs=[master_db_pod_name], tries=5, delay=1)

        self.__class__.dead_master_db_pod_name = master_db_pod_name

    def test3_replication_after_failover(self):
        ready_db_pods = self.get_read_db_pods()
        self.assertEquals(len(ready_db_pods), 2)

        table_name, table_row_count = self.create_table()
        for db_pod_name, db_pod_ip in ready_db_pods.items():
            logging.info("Checking table size on %s", db_pod_name)
            retry_call(self.assert_table_size, fargs=[db_pod_ip, table_name, table_row_count], tries=5, delay=1)

    def test4_old_master_cleanup(self):
        dead_master_db_pod_name = self.__class__.dead_master_db_pod_name
        logging.info("Deleting the dead master db pod %s", dead_master_db_pod_name)
        self._api_instance.delete_namespaced_pod(dead_master_db_pod_name, 'default')

        logging.info("Waiting for the newly created pod to start, and block for pgdata cleanup")
        retry_call(self.assert_db_pod_is_waiting_for_pgdata_cleanup, fargs=[dead_master_db_pod_name],
                   tries=10, delay=3)

        self.clean_pgdata(dead_master_db_pod_name)

        logging.info("Waiting for the newly created pod to be ready")
        retry_call(self.assert_pod_is_ready, fargs=[dead_master_db_pod_name], tries=20, delay=5)

        dead_master_db_pod_ip = self.get_all_db_pods()[dead_master_db_pod_name]
        logging.info("Waiting for the newly created pod to accept new connections")
        retry_call(self.assert_conn_can_be_opened, fargs=[dead_master_db_pod_ip], tries=5, delay=1)

    def test5_standby_failure(self):
        standby_db_pod_name = self.__class__.dead_master_db_pod_name
        standby_db_pod_ip = self.get_all_db_pods()[standby_db_pod_name]

        logging.info("Opening connections to standby db pod: %s", standby_db_pod_name)
        conns = [self.open_db_conn(standby_db_pod_ip) for _ in range(10)]

        self.kill_wal_receiver_continuously(standby_db_pod_name)

        logging.info("Waiting for the standby db pod to become NotReady")
        retry_call(self.assert_pod_is_not_ready, fargs=[standby_db_pod_name], tries=10, delay=5)

        logging.info("Checking that all opened connections are closed")
        for conn in conns:
            retry_call(self.assert_conn_is_closed, fargs=[conn], tries=5, delay=1)

        logging.info("Waiting for the standby db pod to be back to ready")
        retry_call(self.assert_pod_is_ready, fargs=[standby_db_pod_name], tries=10, delay=2)

        logging.info("Waiting for the standby db pod to accept new connections")
        retry_call(self.assert_conn_can_be_opened, fargs=[standby_db_pod_ip], tries=5, delay=1)

    def assert_table_size(self, db_host_ip, table_name, expected_row_count):
        query = "SELECT count(*) FROM " + table_name
        row_count = self.execute_query(db_host_ip, query)[0][0]
        self.assertEqual(expected_row_count, row_count)

    def assert_conn_is_closed(self, conn):
        with self.assertRaises(OperationalError) as cm:
            conn.cursor().execute('SELECT 1')

        self.assertTrue(str(cm.exception).startswith("server closed the connection unexpectedly"),
                        "OperationalError message not as expected")

    def assert_conn_can_be_opened(self, db_host_ip):
        conn = self.open_db_conn(db_host_ip)
        conn.close()

    def assert_master_service_changed(self, old_master_db_pod_name):
        self.assertNotEqual(self.get_master_db_pod()[0], old_master_db_pod_name)

    def assert_read_service_excludes_pod(self, excluded_pod):
        self.assertNotIn(excluded_pod, self.get_read_db_pods().keys())

    def assert_db_pod_is_waiting_for_pgdata_cleanup(self, pod_name):
        output = stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, pod_name, 'default',
                               container='wait-pgdata-empty', command=['pgrep', 'sleep'], stderr=True,
                               stdin=False, stdout=True, tty=False)

        self.assertTrue(output.isdigit(), "Expected a process number as output, but none found!")

    def assert_pod_is_ready(self, pod_name):
        self.assertTrue(self.is_pod_condition(pod_name, 'Ready'), "Expected pod to be in Ready condition")

    def assert_pod_is_not_ready(self, pod_name):
        self.assertFalse(self.is_pod_condition(pod_name, 'Ready'), "Expected pod to be in NotReady condition")

    def create_table(self):
        table_name = 't' + str(random.randint(0, 100000))
        table_row_count = 1000
        row_data = 'X' * 1000
        query = 'CREATE TABLE ' + table_name + ' AS select generate_series(1, %s) AS id, %s AS data'

        logging.info("Creating new table %s with %d records", table_name, table_row_count)
        self.execute_query(self._master_svc_ip, query, (table_row_count, row_data))
        return table_name, table_row_count

    def get_master_db_pod(self):
        endpoint_subsets = self._api_instance.read_namespaced_endpoints('postgres-master', 'default').subsets
        self.assertEqual(1, len(endpoint_subsets))

        endpoint_addresses = endpoint_subsets[0].addresses
        self.assertEqual(1, len(endpoint_addresses))

        master_db_pod_ip = endpoint_addresses[0].ip
        for item in self._api_instance.list_namespaced_pod('default').items:
            if item.status.pod_ip == master_db_pod_ip:
                return item.metadata.name, item.status.pod_ip

        raise AssertionError("The pod with the master ip should have been found")

    def get_read_db_pods(self):
        endpoint_subsets = self._api_instance.read_namespaced_endpoints('postgres', 'default').subsets
        self.assertEqual(1, len(endpoint_subsets))
        return {address.hostname: address.ip for address in endpoint_subsets[0].addresses}

    def get_all_db_pods(self):
        return {item.metadata.name: item.status.pod_ip
                for item in self._api_instance.list_namespaced_pod('default').items
                if item.metadata.labels.get('app') == 'ha-postgres'}

    def is_pod_condition(self, pod_name, condition_type):
        for condition in self._api_instance.read_namespaced_pod(pod_name, 'default').status.conditions:
            if condition.type == condition_type:
                return condition.status == 'True'

        raise AssertionError("Condition with type '%s' should have been found!" % condition_type)

    @staticmethod
    def open_db_conn(db_host_ip):
        return psycopg2.connect(user='postgres', password='su123', database='postgres',
                                host=db_host_ip, port=5433)

    @classmethod
    def execute_query(cls, db_host_ip, query, *query_params):
        conn = None
        try:
            conn = cls.open_db_conn(db_host_ip)
            cursor = conn.cursor()
            cursor.execute(query, *query_params)
            if re.match('^(insert|create)', query, re.IGNORECASE):
                conn.commit()
            else:
                return cursor.fetchall()
        finally:
            if conn:
                conn.close()

    @staticmethod
    def start_db_pod_stress(pod_name):
        stress_commands = [
            ['apt-get', 'update'],
            ['apt-get', 'install', '-y', 'stress'],
            ['bash', '-c', 'stress --cpu 1000 -t 15s &']
        ]

        full_output = ''
        for cmd in stress_commands:
            full_output += stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, pod_name, 'default',
                                         container='postgres', command=cmd, stderr=True, stdin=False,
                                         stdout=True, tty=False)

        logging.info("Started stress command for pod %s, output:\n %s", pod_name, full_output)

    @staticmethod
    def kill_wal_receiver_continuously(db_pod_name):
        stress_commands = [
            ['bash', '-c', "echo 'while true; do pkill -f walreceiver; done' > kill_wal.sh"],
            ['bash', '-c', 'timeout 35s bash kill_wal.sh &'],
        ]

        full_output = ''
        for cmd in stress_commands:
            full_output += stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, db_pod_name, 'default',
                                         container='postgres', command=cmd, stderr=True, stdin=False,
                                         stdout=True, tty=False)

        logging.info("Started killing wal receiver continuously for pod %s, output:\n %s", db_pod_name, full_output)

    @staticmethod
    def clean_pgdata(db_pod_name):
        cleanup_command = [
            '/bin/sh', '-c',
            'rm -rf /pgdata/*; touch /proceed']

        output = stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, db_pod_name, 'default',
                               container='wait-pgdata-empty', command=cleanup_command, stderr=True, stdin=False,
                               stdout=True, tty=False)

        logging.info("Executed cleanup command for pod %s, output: %s", db_pod_name, output)
