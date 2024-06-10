# create a non-root user
RUN useradd -u 10001 -g 10001 --create-home --shell /bin/bash dev
USER dev
WORKDIR /home/dev

# azure-client
FROM mcr.microsoft.com/azure-cli:latest as azure-cli

# oc build
FROM golang:1.22.2 AS oc-build
RUN apt-get update && apt-get install -y libkrb5-dev
WORKDIR /tmp
RUN git clone --branch release-4.18 https://github.com/openshift/oc.git
WORKDIR /tmp/oc
RUN make GO_REQUIRED_MIN_VERSION:= oc

FROM registry.access.redhat.com/ubi9/ubi:latest

# krkn version that will be built
ENV KRKN_VERSION v1.6.0
ENV HOME /home/dev
ENV KUBECONFIG /root/.kube/config

# update yum and install dependencies
RUN yum update -y glibc glibc-common glibc-minimal-langpack runc libnghttp2
RUN rpm -e --allmatches --nodeps --noscripts --notriggers python3-requests
RUN yum install -y git python39 python3-pip jq gettext wget

# get yq
RUN wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/bin/yq && chmod +x /usr/bin/yq

# get kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" &&\
    cp kubectl /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl &&\
    cp kubectl /usr/bin/kubectl && chmod +x /usr/bin/kubectl

# copy azure client binary from azure-cli image
COPY --from=azure-cli /usr/local/bin/az /usr/bin/az

# copy oc client binary from oc-build image
COPY --from=oc-build /tmp/oc/oc /usr/bin/oc
COPY --from=oc-build /tmp/oc/oc /usr/local/bin/oc

# krkn build
RUN python3.9 -m pip install -U pip
RUN git clone https://github.com/krkn-chaos/krkn.git --branch $KRKN_VERSION $HOME/kraken && \
    mkdir -p $HOME/.kube
WORKDIR $HOME/kraken
RUN pip3.9 install -r requirements.txt
RUN pip3.9 install virtualenv

ENTRYPOINT ["python3.9", "run_kraken.py"]
CMD ["--config=config/config.yaml"]
