#!/bin/bash -e

if [ -n "$(pgrep pg_basebackup)" ]; then
	exit 0
fi

pg_isready -U monitoring -d ${POSTGRES_DB}