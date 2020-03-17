ARG base_image_tag=12.2
FROM postgres:${base_image_tag}

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl \
	&& apt-get clean

COPY entrypoint-wrapper.sh master-init.sh master-init-seed.sh /

ENTRYPOINT ["/entrypoint-wrapper.sh"]