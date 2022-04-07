# Dockerfile for kraken

FROM quay.io/openshift/origin-tests:latest as origintests

FROM quay.io/centos/centos:stream9

LABEL org.opencontainers.image.authors="Red Hat OpenShift Chaos Engineering"

ENV KUBECONFIG /root/.kube/config

# Copy OpenShift CLI, Kubernetes CLI from origin-tests image
COPY --from=origintests /usr/bin/oc /usr/bin/oc
COPY --from=origintests /usr/bin/kubectl /usr/bin/kubectl

# Install dependencies
RUN yum install epel-release -y && \
    yum install -y git python python3-pip jq gettext && \
    python3 -m pip install -U pip && \
    rpm --import https://packages.microsoft.com/keys/microsoft.asc && \
    echo -e "[azure-cli]\nname=Azure CLI\nbaseurl=https://packages.microsoft.com/yumrepos/azure-cli\nenabled=1\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" > /etc/yum.repos.d/azure-cli.repo && yum install -y azure-cli && \
    git clone https://github.com/openshift-scale/kraken /root/kraken && \
    mkdir -p /root/.kube && cd /root/kraken && \
    pip3 install -r requirements.txt

WORKDIR /root/kraken

ENTRYPOINT ["python3", "run_kraken.py"]
CMD ["--config=config/config.yaml"]
