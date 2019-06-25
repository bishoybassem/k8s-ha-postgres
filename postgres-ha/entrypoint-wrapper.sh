#!/bin/bash -e

controller_management_port=${CONTROLLER_MANAGEMENT_PORT:-80}

function get_role() {
	curl -fs http://localhost:${controller_management_port}/controller/role
}

function role_decided() {
	role=$(get_role)
	if [ "$role" != "Master" ] && [ "$role" != "Slave" ]; then
		return 1
	fi
	return 0
}

until role_decided; do
    echo "Waiting for the role to be decided by the controller!"
    sleep 5s
done

if [ "$(get_role)" == "Slave" ]; then
    echo "Starting as a slave..."
    export PGPASSWORD=${REPLICATION_PASSWORD}
    pg_basebackup -h postgres -U replication -D ${PGDATA} -PRv
fi

exec docker-entrypoint.sh postgres