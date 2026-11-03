FROM docker:cli

ARG KIND_VERSION=v0.33.0
ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl \
    && curl --fail --location --silent --show-error \
        "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${TARGETARCH}" \
        --output /usr/local/bin/kind \
    && chmod 0755 /usr/local/bin/kind \
    && kind version
