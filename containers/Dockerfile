FROM mcr.microsoft.com/azure-cli:latest as azure-cli

FROM registry.access.redhat.com/ubi9/ubi:latest

ENV KUBECONFIG /root/.kube/config

# Copy azure client binary from azure-cli image
COPY --from=azure-cli /usr/local/bin/az /usr/bin/az
RUN yum update -y glibc glibc-common glibc-minimal-langpack runc
RUN rpm -e --allmatches --nodeps --noscripts --notriggers python3-requests
# Install dependencies
RUN yum install -y git python39 python3-pip jq gettext wget
RUN python3.9 -m pip install -U pip
RUN git clone https://github.com/krkn-chaos/krkn.git --branch v1.5.14 /root/kraken && \
    mkdir -p /root/.kube
WORKDIR /root/kraken
RUN pip3.9 install -r requirements.txt
RUN pip3.9 install virtualenv
RUN wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/bin/yq && chmod +x /usr/bin/yq

# Get Kubernetes and OpenShift clients from stable releases
WORKDIR /tmp
RUN wget https://krkn-mirror.s3.us-west-2.amazonaws.com/oc/oc-krkn.tar.gz &&\
    tar xfvz oc-krkn.tar.gz && cp oc /usr/bin/oc && cp oc /usr/local/bin/oc
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" &&\
    cp kubectl /usr/local/bin/kubectl && cp kubectl /usr/bin/kubectl

WORKDIR /root/kraken

ENTRYPOINT ["python3.9", "run_kraken.py"]
CMD ["--config=config/config.yaml"]