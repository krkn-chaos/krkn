#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/build-container-tool.sh TOOL [OUTPUT_DIR]

Build one of the Go tools shipped in the Krkn runtime image. Run on the target
architecture with the Go toolchain installed. The default output directory is
containers/tools/.

Tools: oc, virtctl, yq
USAGE
}

if [[ $# -lt 1 || $# -gt 2 || $1 == -h || $1 == --help ]]; then
  usage >&2
  exit 2
fi

tool=$1
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output_dir=${2:-"$repo_root/containers/tools"}
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$output_dir"

case "$tool" in
  oc)
    source_dir="$work_dir/oc"
    git clone --branch release-5.1 --single-branch https://github.com/openshift/oc.git "$source_dir"
    cd "$source_dir"
    go mod edit -go 1.26
    go mod edit -require github.com/go-git/go-git/v5@v5.19.0
    go mod edit -require github.com/go-git/go-billy/v5@v5.9.0
    go mod edit -require go.opentelemetry.io/otel@v1.41.0
    go mod edit -require github.com/moby/spdystream@v0.5.1
    go mod edit -require golang.org/x/net@v0.38.0
    go mod edit -require github.com/Azure/go-ntlmssp@v0.1.1
    go mod edit -require github.com/sigstore/fulcio@v1.8.5
    go mod edit -require github.com/sigstore/sigstore@v1.10.4
    go mod edit -replace golang.org/x/net=golang.org/x/net@v0.38.0
    go mod edit -replace github.com/moby/spdystream=github.com/moby/spdystream@v0.5.1
    go mod edit -replace github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream=github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream@v1.7.8
    go mod edit -replace github.com/aws/aws-sdk-go-v2/service/s3=github.com/aws/aws-sdk-go-v2/service/s3@v1.97.3
    go mod tidy
    rm -rf vendor
    go mod vendor
    make GO_REQUIRED_MIN_VERSION:= oc
    binary="$source_dir/oc"
    ;;
  virtctl)
    source_dir="$work_dir/kubevirt"
    git clone https://github.com/kubevirt/kubevirt.git "$source_dir"
    cd "$source_dir"
    go mod edit -go 1.26
    go mod edit -replace github.com/moby/spdystream=github.com/moby/spdystream@v0.5.1
    go mod edit -replace github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream=github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream@v1.7.8
    go mod edit -replace github.com/aws/aws-sdk-go-v2/service/s3=github.com/aws/aws-sdk-go-v2/service/s3@v1.97.3
    go work edit -go 1.26
    go mod tidy
    go work use
    go work vendor
    go build -o "$work_dir/virtctl" ./cmd/virtctl/
    binary="$work_dir/virtctl"
    ;;
  yq)
    source_dir="$work_dir/yq"
    git clone --depth 1 --branch v4.44.6 https://github.com/mikefarah/yq.git "$source_dir"
    cd "$source_dir"
    go mod edit -replace golang.org/x/net=golang.org/x/net@v0.38.0
    go mod edit -replace github.com/moby/spdystream=github.com/moby/spdystream@v0.5.1
    go mod tidy
    go build -ldflags='-s -w' -o "$work_dir/yq" .
    binary="$work_dir/yq"
    ;;
  *)
    echo "error: unsupported tool '$tool'" >&2
    usage >&2
    exit 2
    ;;
esac

if [[ ! -s "$binary" ]]; then
  echo "error: build did not produce $tool at $binary" >&2
  exit 1
fi
install -m 0755 "$binary" "$output_dir/$tool"
printf 'Built %s for %s/%s: %s\n' "$tool" "$(go env GOOS)" "$(go env GOARCH)" "$output_dir/$tool"
