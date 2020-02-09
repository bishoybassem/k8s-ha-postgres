#!/bin/bash -e

if [ -z "$MINIKUBE_VERSION" ] || [ -z "$K8S_VERSION" ] || [ -z "$HELM_VERSION" ]; then
	echo "Please set the tools' versions in the env: MINIKUBE_VERSION, K8S_VERSION & HELM_VERSION"
	exit 1
fi

curl -Lo minikube https://storage.googleapis.com/minikube/releases/v$MINIKUBE_VERSION/minikube-linux-amd64
chmod +x minikube
sudo mv minikube /usr/local/bin/

curl -LO https://storage.googleapis.com/kubernetes-release/release/v$K8S_VERSION/bin/linux/amd64/kubectl
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

curl -Lo helm.tar.gz https://get.helm.sh/helm-v$HELM_VERSION-linux-amd64.tar.gz
tar --strip-components=1 --wildcards -xvf helm.tar.gz */helm
sudo mv helm /usr/local/bin/

sudo minikube start --vm-driver=none --kubernetes-version=v$K8S_VERSION
sudo chown -R $USER:$GROUP ~/.kube ~/.minikube

kubectl version
helm version

kubectl scale --replicas=1 deploy/coredns -n kube-system