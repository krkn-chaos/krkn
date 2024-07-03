# azure-client
FROM mcr.microsoft.com/azure-cli:latest as azure-cli
# oc build
FROM golang:1.22.4 AS oc-build
RUN apt-get update && apt-get install -y libkrb5-dev
WORKDIR /tmp
RUN git clone --branch release-4.18 https://github.com/openshift/oc.git
WORKDIR /tmp/oc
RUN go mod edit -go 1.22.3 &&\
    go get github.com/moby/buildkit@v0.12.5 &&\
    go get github.com/containerd/containerd@v1.7.11&&\
    go get github.com/docker/docker@v25.0.5&&\
    go mod tidy && go mod vendor
RUN make GO_REQUIRED_MIN_VERSION:= oc

FROM fedora:40
ARG PR_NUMBER
RUN groupadd -g 1001 krkn && useradd -m -u 1001 -g krkn krkn
RUN dnf update -y

# krkn version that will be built
ENV KRKN_VERSION v1.6.2

ENV KUBECONFIG /home/krkn/.kube/config

# install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" &&\
    cp kubectl /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl &&\
    cp kubectl /usr/bin/kubectl && chmod +x /usr/bin/kubectl

# This overwrites any existing configuration in /etc/yum.repos.d/kubernetes.repo
RUN dnf update && dnf install -y git python39 jq yq gettext wget which
# copy azure client binary from azure-cli image
COPY --from=azure-cli /usr/local/bin/az /usr/bin/az

# copy oc client binary from oc-build image
COPY --from=oc-build /tmp/oc/oc /usr/bin/oc

# krkn build
RUN git clone https://github.com/krkn-chaos/krkn.git /home/krkn/kraken && \
    mkdir -p /home/krkn/.kube

WORKDIR /home/krkn/kraken
# if is an event on main the variable $PR_NUMBER has no value so the latest tag is checked out else
# if is a PR event the PR itself will be checked out
RUN if [ -z "$PR_NUMBER" ]; then git checkout $KRKN_VERSION;\
    else git fetch origin pull/${PR_NUMBER}/head:pr-${PR_NUMBER} && git checkout pr-${PR_NUMBER}; fi

RUN python3.9 -m ensurepip
RUN pip3.9 install -r requirements.txt
RUN pip3.9 install jsonschema

RUN chown -R krkn:krkn /home/krkn && chmod 755 /home/krkn
USER krkn
ENTRYPOINT ["python3.9", "run_kraken.py"]
CMD ["--config=config/config.yaml"]
