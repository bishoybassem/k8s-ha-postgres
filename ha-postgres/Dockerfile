FROM postgres:11.3

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl \
	&& apt-get clean

COPY entrypoint-wrapper.sh master-init.sh /

ENTRYPOINT ["/entrypoint-wrapper.sh"]