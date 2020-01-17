FROM debian:buster-slim

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl gnupg \
	&& curl -k https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
	&& echo "deb http://apt.postgresql.org/pub/repos/apt/ buster-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
	&& apt-get clean

RUN apt-get update \
	&& apt-get install -y --no-install-recommends pgbouncer=1.12.0-* \
	&& apt-get clean \
	&& rm /etc/pgbouncer/*

COPY pgbouncer.ini pg_hba.conf /etc/pgbouncer/

ENTRYPOINT ["pgbouncer"]
CMD ["/etc/pgbouncer/pgbouncer.ini"]