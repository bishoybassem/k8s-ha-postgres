#!/bin/bash -e

namespace=$1
if [ -z "$namespace" ]; then
	echo "Usage: $0 NAMESPACE [FILE]..."
	echo "Builds the docker images, creates the NAMESPACE (recreates if it exists), installs the helm chart there, and waits till the db pods become ready."
	echo "The FILE list would be passed to the helm install command as value files"
	exit 1
fi
shift

postgres_image_tag=${POSTGRES_IMAGE_TAG:-12.2}
docker build -t ha-postgres-controller:1.0.0 ha-postgres-controller/
docker build --build-arg base_image_tag=$postgres_image_tag -t ha-postgres:$postgres_image_tag ha-postgres/

if kubectl get ns $namespace; then
	kubectl delete ns $namespace --timeout 2m
fi

kubectl create ns $namespace

files=("$@")
helm -n $namespace install ${files[@]/#/-f } ha-postgres chart/

db_replicas=$(kubectl -n $namespace get sts ha-postgres -o jsonpath='{.spec.replicas}')
echo "Waiting for $db_replicas ready db replicas"
while [ "$(kubectl -n $namespace get sts ha-postgres -o jsonpath='{.status.readyReplicas}')" != "$db_replicas" ]; do 
	sleep 5s
done

kubectl -n $namespace get pods