import random
import re
import unittest

import psycopg2
from kubernetes import client, config
from retry.api import retry_call


class IntegrationTest(unittest.TestCase):

    def setUp(self):
        config.load_kube_config()
        self._api_instance = client.CoreV1Api()
        self._master_svc_ip = self._api_instance.read_namespaced_service("postgres-master", "default").spec.cluster_ip

    def test_replication(self):
        table_name = "t" + str(random.randint(0, 100000))
        table_row_count = 10000
        row_data = 'X' * 1000
        query = "CREATE TABLE " + table_name + " AS select generate_series(1, %s) AS id, %s AS data"
        self.execute_query(self._master_svc_ip, query, (table_row_count, row_data))

        for db_pod_ip in self.get_db_pods().values():
            retry_call(self.assert_table_size, fargs=(db_pod_ip, table_name, table_row_count), tries=5, delay=1)

    def assert_table_size(self, db_host_ip, table_name, expected_row_count):
        query = "SELECT count(*) FROM " + table_name
        row_count = self.execute_query(db_host_ip, query)[0][0]
        self.assertEqual(expected_row_count, row_count)

    def get_db_pods(self):
        return {item.metadata.name: item.status.pod_ip
                for item in self._api_instance.list_namespaced_pod("default").items
                if item.metadata.labels.get('app') == 'ha-postgres'}

    @staticmethod
    def execute_query(db_host_ip, query, *query_params):
        conn = None
        try:
            conn = psycopg2.connect(user="postgres", password="su123", database="postgres",
                                    host=db_host_ip, port=5433)
            cursor = conn.cursor()
            cursor.execute(query, *query_params)
            if re.match('^(insert|create)', query, re.IGNORECASE):
                conn.commit()
            else:
                return cursor.fetchall()
        finally:
            if conn:
                conn.close()
