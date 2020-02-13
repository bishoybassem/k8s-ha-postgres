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
        table_name, table_row_count = self.create_table()
        for db_pod_name, db_pod_ip in self.get_all_db_pods().items():
            logging.info("Checking table size on %s", db_pod_name)
            retry_call(self.assert_table_size, fargs=(db_pod_ip, table_name, table_row_count), tries=5, delay=1)

    def assert_table_size(self, db_host_ip, table_name, expected_row_count):
        query = "SELECT count(*) FROM " + table_name
        row_count = self.execute_query(db_host_ip, query)[0][0]
        self.assertEqual(expected_row_count, row_count)

    def test2_failover(self):
        logging.info("Opening connections to the master service")
        conns = [self.open_db_conn(self._master_svc_ip) for _ in range(10)]

        master_db_pod_name, master_db_pod_ip = self.get_master_db_pod()
        logging.info("Current master db pod is %s with ip %s", master_db_pod_name, master_db_pod_ip)
        self.stress_db_pod_cpu(master_db_pod_name)

        logging.info("Checking that all opened connections are closed")
        for conn in conns:
            retry_call(self.assert_conn_is_closed, fargs=(conn,), tries=5, delay=3)

        logging.info("Checking that no new connections can be opened to the failed master")
        with self.assertRaises(OperationalError):
            self.open_db_conn(master_db_pod_ip)

        logging.info("Checking that the master service is pointing to a new db pod")
        retry_call(self.assert_master_service_changed, fargs=(master_db_pod_name,), tries=10, delay=3)

        logging.info("Checking that the read service excludes the old master db pod")
        retry_call(self.assert_read_service_excludes_pod, fargs=(master_db_pod_name,), tries=5, delay=1)

    def assert_conn_is_closed(self, conn):
        with self.assertRaises(OperationalError) as cm:
            conn.cursor().execute('SELECT 1')

        self.assertTrue(str(cm.exception).startswith("server closed the connection unexpectedly"),
                        "OperationalError message not as expected")

    def assert_master_service_changed(self, old_master_db_pod_name):
        self.assertNotEqual(self.get_master_db_pod()[0], old_master_db_pod_name)

    def assert_read_service_excludes_pod(self, excluded_pod):
        self.assertNotIn(excluded_pod, self.get_read_db_pods().keys())

    def test3_replication_after_failover(self):
        table_name, table_row_count = self.create_table()
        for db_pod_name, db_pod_ip in self.get_read_db_pods().items():
            logging.info("Checking table size on %s", db_pod_name)
            retry_call(self.assert_table_size, fargs=(db_pod_ip, table_name, table_row_count), tries=5, delay=1)

    def create_table(self):
        table_name = 't' + str(random.randint(0, 100000))
        table_row_count = 10000
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
    def stress_db_pod_cpu(pod_name):
        exec_command = [
            '/bin/bash', '-c',
            'apt-get update; apt-get install -y stress; stress --cpu 1000 -t 20s']

        output = stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, pod_name, 'default',
                               container='postgres', command=exec_command, stderr=True, stdin=False,
                               stdout=True, tty=False)

        logging.info("Executed stress command for pod %s output:\n %s", pod_name, output)
