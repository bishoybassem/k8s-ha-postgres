#!/bin/bash -e

echo "Configuring initial master..."

psql <<-EOF
	ALTER SYSTEM SET listen_addresses = '127.0.0.1';

	CREATE ROLE replication WITH REPLICATION LOGIN PASSWORD '$REPLICATION_USER_PASSWORD';
	CREATE ROLE controller LOGIN PASSWORD '$CONTROLLER_USER_PASSWORD';
EOF

tee ${PGDATA}/pg_hba.conf <<-EOF
	# TYPE  DATABASE        USER            ADDRESS                 METHOD
	host    all             all             all                     md5
	host    replication     all             all                     md5
EOF
