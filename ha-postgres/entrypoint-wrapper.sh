#!/bin/bash -e

controller_management_port=${CONTROLLER_MANAGEMENT_PORT:-80}

function get_role() {
	curl -fs http://localhost:${controller_management_port}/controller/role
}

function role_decided() {
	role=$(get_role)
	if [ "$role" != "Master" ] && [ "$role" != "Replica" ]; then
		return 1
	fi
	return 0
}

until role_decided; do
    echo "Waiting for the role to be decided by the controller!"
    sleep 5s
done

if [ "$(get_role)" == "Replica" ] && [ ! -f ${PGDATA}/recovery.conf ]; then
    echo "Starting as a replica..."
    export PGPASSWORD=${REPLICATION_USER_PASSWORD}
    pg_basebackup -h ${POSTGRES_MASTER_HOST} -p ${POSTGRES_MASTER_PORT} -U replication -D ${PGDATA} -PRv
fi

touch init_completed

mv /master-init.sh /docker-entrypoint-initdb.d/0-master-init.sh
exec docker-entrypoint.sh postgres