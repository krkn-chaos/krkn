# Dockerfile for kraken

FROM quay.io/openshift/origin-tests:latest as origintests

FROM mcr.microsoft.com/azure-cli:latest as azure-cli

FROM quay.io/centos/centos:stream9

LABEL org.opencontainers.image.authors="Red Hat OpenShift Chaos Engineering"

ENV KUBECONFIG /root/.kube/config

# Copy OpenShift CLI, Kubernetes CLI from origin-tests image
COPY --from=origintests /usr/bin/oc /usr/bin/oc
COPY --from=origintests /usr/bin/kubectl /usr/bin/kubectl

# Copy azure client binary from azure-cli image
COPY --from=azure-cli /usr/local/bin/az /usr/bin/az

# Install dependencies
RUN yum install epel-release -y && \
    yum install -y git python39 python3-pip jq gettext && \
    python3.9 -m pip install -U pip && \
    git clone https://github.com/redhat-chaos/krkn.git --branch v1.1.0 /root/kraken && \
    mkdir -p /root/.kube && cd /root/kraken && \
    pip3.9 install -r requirements.txt

WORKDIR /root/kraken

ENTRYPOINT ["python3.9", "run_kraken.py"]
CMD ["--config=config/config.yaml"]
