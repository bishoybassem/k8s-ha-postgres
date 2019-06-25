#!/bin/bash -e

echo "Configuring replication for initial master..."
echo 'host replication replication all md5' >> ${PGDATA}/pg_hba.conf
psql -c "CREATE ROLE replication WITH REPLICATION LOGIN PASSWORD '$REPLICATION_PASSWORD'"
psql -c "CREATE ROLE monitoring LOGIN"