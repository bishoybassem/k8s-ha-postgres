#!/bin/bash -e

if [ -n "$SEED_DB_HOST" ]; then
	echo "Creating a subscription for the seed database..."
	seed_db_port=${SEED_DB_PORT:-$POSTGRES_MASTER_PORT}
	seed_db_name=${SEED_DB_NAME:-$POSTGRES_DB}
	seed_db_user=${SEED_DB_USER:-$POSTGRES_USER}
	seed_db_password="${PASSWORD_SEED_DB_USER:-$PASSWORD_SUPER_USER}"
	seed_db_conn_url="host=$SEED_DB_HOST port=$seed_db_port dbname=$seed_db_name user=$seed_db_user password=$seed_db_password"
	seed_db_publication=${SEED_DB_PUBLICATION:-seed}
	psql -U $POSTGRES_USER -d $POSTGRES_DB \
		-c "CREATE SUBSCRIPTION seed_from CONNECTION '$seed_db_conn_url' PUBLICATION $seed_db_publication"
fi