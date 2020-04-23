import logging
import random
import re
import socket
import sys

import psycopg2
from kubernetes import client, config, stream

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s: %(message)s')

config.load_kube_config()

MAIN_NAMESPACE = 'main'
SEED_NAMESPACE = 'seed'
API_INSTANCE = client.CoreV1Api()
LB_SVC_IP = API_INSTANCE.read_namespaced_service('postgres-test', MAIN_NAMESPACE).spec.cluster_ip
LB_STATS_PORT = 8999
MASTER_DB_PORT = 6432
STANDBY_DB_PORT = 6433
PG_USER = "test_user"
PG_PASS = "test1234"
PG_DB = "test_db"


def create_table():
    table_name = 't' + str(random.randint(0, 100000))
    table_row_count = 1000
    row_data = 'X' * 1000
    query = 'CREATE TABLE ' + table_name + ' AS select generate_series(1, %s) AS id, %s AS data'

    logging.info("Creating new table %s with %d records", table_name, table_row_count)
    execute_query(LB_SVC_IP, MASTER_DB_PORT, query, (table_row_count, row_data))
    return table_name, table_row_count


def create_table_in_seed_db():
    table_name = 't' + str(random.randint(0, 100000))
    table_row_count = 1000
    row_data = 'X' * 1000
    create_table_query = 'CREATE TABLE ' + table_name + ' (id INT PRIMARY KEY, data TEXT)'
    insert_data_query = 'INSERT INTO ' + table_name + ' values (generate_series(1, %s), %s)'

    logging.info("Creating new table '%s' in the main db cluster (without records)", table_name)
    execute_query(LB_SVC_IP, MASTER_DB_PORT, create_table_query)

    logging.info("Creating new table '%s' in the seed db cluster with %d records", table_name, table_row_count)
    seed_lb_svc_ip = API_INSTANCE.read_namespaced_service('postgres-test', SEED_NAMESPACE).spec.cluster_ip
    execute_query(seed_lb_svc_ip, MASTER_DB_PORT, create_table_query)
    execute_query(seed_lb_svc_ip, MASTER_DB_PORT, insert_data_query, (table_row_count, row_data))

    logging.info("Refreshing the subscription in the main db cluster")
    execute_query(LB_SVC_IP, MASTER_DB_PORT, 'ALTER SUBSCRIPTION seed_from REFRESH PUBLICATION')

    return table_name, table_row_count


def execute_query(db_host_ip, port, query, *query_params):
    conn = None
    try:
        conn = open_db_conn(db_host_ip, port)[0]
        cursor = conn.cursor()
        cursor.execute(query, *query_params)
        if re.match('^(insert|create|alter)', query, re.IGNORECASE):
            conn.commit()
        else:
            return cursor.fetchall()
    finally:
        if conn:
            conn.close()


def open_db_conn(db_host_ip, port=MASTER_DB_PORT):
    conn = psycopg2.connect(user=PG_USER, password=PG_PASS, database=PG_DB,
                            host=db_host_ip, port=port)
    cursor = conn.cursor()
    cursor.execute("select inet_server_addr()")
    return conn, cursor.fetchone()[0]


def get_lb_backend_servers(backend):
    response = send_cmd_stats_socket("show servers state " + backend)
    lines = response.splitlines()[1:]
    headers = lines.pop(0)[2:].split()
    extract_columns = ["srv_name", "srv_addr", "srv_op_state"]
    extract_columns_indices = [headers.index(column) for column in extract_columns]
    pods = map(lambda line: [line.split()[i] for i in extract_columns_indices], lines)
    return list(pods)


def send_cmd_stats_socket(command):
    lb_host = get_pods("postgres-lb").popitem()[1]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((lb_host, LB_STATS_PORT))
    s.sendall(bytes(command + "\n", 'utf8'))
    response = s.recv(8192)
    s.close()
    return response.decode('utf8').strip()


def get_pods(app_label_value):
    return {item.metadata.name: item.status.pod_ip
            for item in API_INSTANCE.list_namespaced_pod(MAIN_NAMESPACE).items
            if item.metadata.labels.get('app') == app_label_value}


def get_pod_name_by_ip(ip):
    for item in API_INSTANCE.list_namespaced_pod(MAIN_NAMESPACE).items:
        if item.status.pod_ip == ip:
            return item.metadata.name

    raise AssertionError("Could not find pod for given ip!")


def start_db_pod_stress(pod_name):
    stress_commands = [
        ['apt-get', 'update'],
        ['apt-get', 'install', '-y', 'stress'],
        ['bash', '-c', 'stress --cpu 1000 -t 15s &']
    ]

    full_output = ''
    for cmd in stress_commands:
        full_output += stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, pod_name, MAIN_NAMESPACE,
                                     container='postgres', command=cmd, stderr=True, stdin=False,
                                     stdout=True, tty=False)

    logging.info("Started stress command for pod %s, output:\n %s", pod_name, full_output)


def kill_wal_receiver_continuously(db_pod_name):
    stress_commands = [
        ['bash', '-c', "echo 'while true; do pkill -f walreceiver; done' > kill_wal.sh"],
        ['bash', '-c', 'timeout 45s bash kill_wal.sh &'],
    ]

    full_output = ''
    for cmd in stress_commands:
        full_output += stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, db_pod_name, MAIN_NAMESPACE,
                                     container='postgres', command=cmd, stderr=True, stdin=False,
                                     stdout=True, tty=False)

    logging.info("Started killing wal receiver continuously for pod %s, output:\n %s", db_pod_name, full_output)


def clean_pgdata(db_pod_name):
    cleanup_command = [
        '/bin/sh', '-c',
        'rm -rf /pgdata/*; touch /proceed']

    output = stream.stream(client.CoreV1Api().connect_get_namespaced_pod_exec, db_pod_name, MAIN_NAMESPACE,
                           container='clean-data', command=cleanup_command, stderr=True, stdin=False,
                           stdout=True, tty=False)

    logging.info("Executed cleanup command for pod %s, output: %s", db_pod_name, output)