#!/bin/bash -e

if [ -f init_completed ]; then
	pg_isready -U monitoring -d ${POSTGRES_DB}
fi
