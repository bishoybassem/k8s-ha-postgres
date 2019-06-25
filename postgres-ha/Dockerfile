FROM postgres:11.3

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl \
	&& apt-get clean

COPY entrypoint-wrapper.sh /
COPY liveness-probe.sh /
COPY master-init.sh /docker-entrypoint-initdb.d

ENTRYPOINT ["/entrypoint-wrapper.sh"]