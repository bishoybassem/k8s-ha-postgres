#!/bin/bash -e

echo "Configuring initial master..."

psql <<-EOF
	ALTER SYSTEM SET listen_addresses = '127.0.0.1';
	ALTER SYSTEM SET recovery_target_timeline = 'latest';

	CREATE ROLE replication WITH REPLICATION LOGIN PASSWORD '$REPLICATION_USER_PASSWORD';
	CREATE ROLE controller WITH LOGIN PASSWORD '$CONTROLLER_USER_PASSWORD';

	GRANT EXECUTE ON FUNCTION pg_promote TO controller;

	CREATE FUNCTION public.wal_receiver_status() RETURNS text AS '
	  SELECT status FROM pg_catalog.pg_stat_wal_receiver;
	' LANGUAGE sql SECURITY DEFINER;

	REVOKE EXECUTE ON FUNCTION public.wal_receiver_status FROM PUBLIC;
	GRANT EXECUTE ON FUNCTION public.wal_receiver_status TO controller;
EOF

tee ${PGDATA}/pg_hba.conf <<-EOF
	# TYPE  DATABASE        USER            ADDRESS                 METHOD
	host    all             all             all                     md5
	host    replication     all             all                     md5
EOF
