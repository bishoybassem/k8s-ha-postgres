#!/bin/bash -e

echo "Configuring initial master..."

echo 'host replication replication all md5' >> ${PGDATA}/pg_hba.conf

psql <<-EOF 
	CREATE ROLE replication WITH REPLICATION LOGIN PASSWORD '$REPLICATION_PASSWORD';
	CREATE ROLE monitoring LOGIN;
EOF