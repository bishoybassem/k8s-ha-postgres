#!/bin/bash -e

echo "Configuring initial master..."

psql <<-EOF
	CREATE ROLE replication WITH REPLICATION LOGIN PASSWORD '$REPLICATION_PASSWORD';
	CREATE ROLE monitoring LOGIN;
	CREATE ROLE pgbouncer LOGIN;
EOF

psql <<-'EOF'
	CREATE OR REPLACE FUNCTION public.user_lookup(
	  INOUT in_username text, 
	  OUT out_password text
	) RETURNS record AS $$
	BEGIN
	  SELECT passwd FROM pg_catalog.pg_shadow
	  WHERE usename = in_username INTO out_password;
	  RETURN;
	END;
	$$ LANGUAGE plpgsql SECURITY DEFINER;

	REVOKE EXECUTE ON FUNCTION public.user_lookup FROM PUBLIC;
	GRANT EXECUTE ON FUNCTION public.user_lookup TO pgbouncer;
EOF

tee ${PGDATA}/pg_hba.conf <<-EOF
	# TYPE  DATABASE        USER            ADDRESS                 METHOD
	host    all             all             127.0.0.1/32            trust
	host    replication     all             all                     md5
	host    all             all             all                     reject
EOF