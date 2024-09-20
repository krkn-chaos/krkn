# oc build
FROM golang:1.22.5 AS oc-build
RUN apt-get update && apt-get install -y --no-install-recommends libkrb5-dev
WORKDIR /tmp
RUN git clone --branch release-4.18 https://github.com/openshift/oc.git
WORKDIR /tmp/oc
RUN go mod edit -go 1.22.5 &&\
    go get github.com/moby/buildkit@v0.12.5 &&\
    go get github.com/containerd/containerd@v1.7.11&&\
    go get github.com/docker/docker@v25.0.6&&\
    go get github.com/opencontainers/runc@v1.1.14&&\
    go mod tidy && go mod vendor
RUN make GO_REQUIRED_MIN_VERSION:= oc

FROM fedora:40
ARG PR_NUMBER
ARG TAG
RUN groupadd -g 1001 krkn && useradd -m -u 1001 -g krkn krkn
RUN dnf update -y

ENV KUBECONFIG /home/krkn/.kube/config

# install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" &&\
    cp kubectl /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl &&\
    cp kubectl /usr/bin/kubectl && chmod +x /usr/bin/kubectl

# This overwrites any existing configuration in /etc/yum.repos.d/kubernetes.repo
RUN dnf update && dnf install -y --setopt=install_weak_deps=False \
    git python39 jq yq gettext wget which &&\
    dnf clean all

# copy oc client binary from oc-build image
COPY --from=oc-build /tmp/oc/oc /usr/bin/oc

# krkn build
RUN git clone https://github.com/krkn-chaos/krkn.git /home/krkn/kraken && \
    mkdir -p /home/krkn/.kube

WORKDIR /home/krkn/kraken

# default behaviour will be to build main
# if it is a PR trigger the PR itself will be checked out
RUN if [ -n "$PR_NUMBER" ]; then git fetch origin pull/${PR_NUMBER}/head:pr-${PR_NUMBER} && git checkout pr-${PR_NUMBER};fi
# if it is a TAG trigger checkout the tag
RUN if [ -n "$TAG" ]; then git checkout "$TAG";fi

RUN python3.9 -m ensurepip
RUN pip3.9 install -r requirements.txt
RUN pip3.9 install jsonschema

RUN chown -R krkn:krkn /home/krkn && chmod 755 /home/krkn
USER krkn
ENTRYPOINT ["python3.9", "run_kraken.py"]
CMD ["--config=config/config.yaml"]
