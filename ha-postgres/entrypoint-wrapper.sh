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

export ROLE=$(get_role)
echo "Starting as $ROLE..."

if [ "$ROLE" == "Replica" ] && [ -z "$(find $PGDATA -type f -print -quit)" ]; then
	echo "Taking a base backup of the current master..."
	export PGPASSWORD="$PASSWORD_REPLICATION_USER"
	pg_basebackup -h $POSTGRES_MASTER_HOST -p $POSTGRES_MASTER_PORT -U replication -D $PGDATA -PRv
	unset PGPASSWORD
fi

cp /master-init.sh /docker-entrypoint-initdb.d/0-master-init.sh
for file in $(find /user-defined-init-scripts -type f); do
	cp $file /docker-entrypoint-initdb.d/1-user-defined-$(basename $file)
done
cp /master-init-seed.sh /docker-entrypoint-initdb.d/2-master-init-seed.sh

export POSTGRES_PASSWORD="$PASSWORD_SUPER_USER"

exec docker-entrypoint.sh postgres