# Dockerfile for kraken

FROM quay.io/openshift/origin-tests:latest as origintests

FROM centos:7

MAINTAINER Red Hat OpenShift Performance and Scale

ENV KUBECONFIG /root/.kube/config

# Copy OpenShift CLI, Kubernetes CLI from origin-tests image
COPY --from=origintests /usr/bin/oc /usr/bin/oc
COPY --from=origintests /usr/bin/kubectl /usr/bin/kubectl

# Install dependencies
RUN yum install -y git python36 python3-pip && \
python3 -m pip install -U pip && \
git clone https://github.com/openshift-scale/kraken /root/kraken && \
mkdir -p /root/.kube && cd /root/kraken && \
pip3 install -r requirements.txt

WORKDIR /root/kraken

ENTRYPOINT python3 run_kraken.py --config=config/config.yaml
