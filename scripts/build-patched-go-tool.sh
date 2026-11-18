#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 TOOL ARCH BINARY_OUTPUT METADATA_DIR REPORT_DIR" >&2
  echo "Tools: oc, virtctl, yq; architectures: amd64, arm64" >&2
}

if [[ $# -ne 5 ]]; then usage; exit 2; fi

tool=$1
arch=$2
binary_output=$3
metadata_dir=$4
report_dir=$5
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
source_dir="$work_dir/source"
context_dir="$work_dir/context"
mkdir -p "$context_dir/source" "$binary_output" "$metadata_dir/baseline" "$metadata_dir/patched" "$report_dir"
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/scripts/go-tools-versions.env"

case "$arch" in amd64|arm64) ;; *) echo "unsupported architecture: $arch" >&2; exit 2 ;; esac

clone_pinned_repo() {
  local url=$1 ref=$2 destination=$3
  git init --quiet "$destination"
  git -C "$destination" remote add origin "$url"
  git -C "$destination" fetch --quiet --depth 1 origin "$ref"
  git -C "$destination" checkout --quiet --detach FETCH_HEAD
  local actual
  actual=$(git -C "$destination" rev-parse HEAD)
  [[ "$actual" == "$ref" ]] || { echo "error: expected $url@$ref, checked out $actual" >&2; exit 1; }
}

case "$tool" in
  oc)
    source_url=https://github.com/openshift/oc.git
    source_ref=$OC_SOURCE_REF
    source_version=$OC_SOURCE_LABEL
    clone_pinned_repo "$source_url" "$source_ref" "$source_dir"
    pattern='./cmd/oc'
    build_tags='include_gcs,include_oss,containers_image_openpgp,gssapi'
    build_command='cd /workspace && go mod tidy && go mod vendor && make GO_REQUIRED_MIN_VERSION:= oc && install -m 0755 /workspace/oc /out/oc'
    exclude_modules=(github.com/distribution/distribution/v3 github.com/moby/buildkit github.com/moby/go-archive golang.org/x/crypto)
    ;;
  virtctl)
    source_url=https://github.com/kubevirt/kubevirt.git
    source_ref=$VIRTCTL_SOURCE_REF
    source_version=$VIRTCTL_SOURCE_LABEL
    clone_pinned_repo "$source_url" "$source_ref" "$source_dir"
    pattern='./cmd/virtctl/'
    build_tags=''
    build_command='cd /workspace && go mod tidy && go work vendor && go build -o /out/virtctl ./cmd/virtctl/'
    exclude_modules=()
    ;;
  yq)
    source_url=https://github.com/mikefarah/yq.git
    source_ref=$YQ_SOURCE_REF
    source_version=$YQ_SOURCE_LABEL
    clone_pinned_repo "$source_url" "$source_ref" "$source_dir"
    pattern='.'
    build_tags=''
    build_command='cd /workspace && go mod tidy && go mod vendor && go build -ldflags="-s -w" -o /out/yq .'
    exclude_modules=()
    ;;
  *) echo "unsupported Go tool: $tool" >&2; usage; exit 2 ;;
esac

source_commit=$(git -C "$source_dir" rev-parse HEAD)
printf '%s\n' "$source_url" > "$metadata_dir/source-url.txt"
printf '%s\n' "$source_version" > "$metadata_dir/source-version.txt"
printf '%s\n' "$source_commit" > "$metadata_dir/source-commit.txt"
printf '%s\n' "$GOVULNCHECK_VERSION" > "$metadata_dir/govulncheck-version.txt"
(
  cd "$source_dir"
  find . -type d \( -name .git -o -name vendor \) -prune -o \
    -type f \( -name go.mod -o -name go.sum -o -name go.work -o -name go.work.sum \) -print0 \
    | tar --null --files-from=- --create --file=-
) | tar --extract --file=- --directory "$metadata_dir/baseline"

cp -R "$source_dir/." "$context_dir/source/"
cp "$repo_root/scripts/update-go-vulnerabilities.sh" "$context_dir/update-go-vulnerabilities.sh"
printf '**/.git\n**/.git/**\n' > "$context_dir/.dockerignore"
cat > "$context_dir/Dockerfile" <<'DOCKERFILE'
ARG GO_TOOLCHAIN_VERSION
ARG GOVULNCHECK_VERSION
FROM golang:${GO_TOOLCHAIN_VERSION}
ARG GOVULNCHECK_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git make gcc pkg-config libkrb5-dev libgpgme-dev python3 \
    && rm -rf /var/lib/apt/lists/* \
    && go install golang.org/x/vuln/cmd/govulncheck@${GOVULNCHECK_VERSION}
WORKDIR /workspace
COPY source/ /workspace/
COPY update-go-vulnerabilities.sh /pipeline/update-go-vulnerabilities.sh
RUN chmod 0755 /pipeline/update-go-vulnerabilities.sh
DOCKERFILE

run_id=${GITHUB_RUN_ID:-local}
image="localhost/krkn-go-tool:${tool}-${run_id}-${arch}"
docker build --pull --platform "linux/$arch" \
  --build-arg "GO_TOOLCHAIN_VERSION=$GO_TOOLCHAIN_VERSION" \
  --build-arg "GOVULNCHECK_VERSION=$GOVULNCHECK_VERSION" \
  -t "$image" "$context_dir"

update_args=(--max-passes 5 --report-dir /reports/govulncheck)
for module in "${exclude_modules[@]-}"; do
  [[ -z "$module" ]] || update_args+=(--exclude-module "$module")
done

runner_uid=$(id -u)
runner_gid=$(id -g)
docker run --rm --platform "linux/$arch" \
  --user "$runner_uid:$runner_gid" \
  -e HOME=/tmp/go-home -e GOPATH=/tmp/go-path -e GOCACHE=/tmp/go-cache -e GOMODCACHE=/tmp/go-mod-cache \
  -e "GOMAXPROCS=${GOMAXPROCS:-2}" -e "GOFLAGS=${GOFLAGS:--p=2}" \
  -v "$source_dir:/workspace" -v "$report_dir:/reports" \
  --entrypoint /bin/bash "$image" -c \
  'set -Eeuo pipefail; mkdir -p "$HOME" "$GOPATH" "$GOCACHE" "$GOMODCACHE"; /pipeline/update-go-vulnerabilities.sh "$@" /workspace' \
  bash "${update_args[@]}"

(
  cd "$source_dir"
  find . -type d \( -name .git -o -name vendor \) -prune -o \
    -type f \( -name go.mod -o -name go.sum -o -name go.work -o -name go.work.sum \) -print0 \
    | tar --null --files-from=- --create --file=-
) | tar --extract --file=- --directory "$metadata_dir/patched"

build_command="set -Eeuo pipefail; mkdir -p /tmp/go-home /tmp/go-path /tmp/go-cache /tmp/go-mod-cache; cd /workspace; go version; for attempt in 1 2 3; do if go mod download; then break; fi; if [ \"\$attempt\" -eq 3 ]; then exit 1; fi; sleep \$((1 << (attempt - 1))); done; $build_command; govulncheck -mode=binary -json /out/$tool > /reports/govulncheck-${tool}-${arch}-binary.jsonl 2> /reports/govulncheck-${tool}-${arch}-binary.stderr"
docker run --rm --platform "linux/$arch" \
  --user "$runner_uid:$runner_gid" \
  -e HOME=/tmp/go-home -e GOPATH=/tmp/go-path -e GOCACHE=/tmp/go-cache -e GOMODCACHE=/tmp/go-mod-cache \
  -e "GOMAXPROCS=${GOMAXPROCS:-2}" -e "GOFLAGS=${GOFLAGS:--p=2}" \
  -v "$source_dir:/workspace" -v "$binary_output:/out" -v "$report_dir:/reports" \
  --entrypoint /bin/bash "$image" -c "$build_command"

if [[ ! -s "$binary_output/$tool" ]]; then
  echo "error: build did not produce $binary_output/$tool" >&2
  exit 1
fi

applied_updates="$report_dir/govulncheck/applied-updates.tsv"
update_count=0
if [[ -f "$applied_updates" ]]; then update_count=$(wc -l < "$applied_updates" | tr -d ' '); fi
{
  echo "### Go dependency remediation: $tool ($arch)"
  echo
  echo "- Source: $source_url@$source_version ($source_commit)"
  echo "- Scanner: govulncheck $GOVULNCHECK_VERSION, module scan of the module dependency graph"
  echo "- Go build target: \`$pattern\`"
  [[ -z "$build_tags" ]] || echo "- Build tags: \`$build_tags\`"
  echo "- Go module updates applied: $update_count"
  if ((update_count > 0)); then
    sed 's/^/- `/' "$applied_updates" | sed 's/$/`/'
  else
    echo "- No module updates were applied."
  fi
  unresolved="$report_dir/govulncheck/unresolved-final.txt"
  if [[ -s "$unresolved" ]]; then
    echo "- Residual govulncheck findings (informational; build and tests are the gate):"
    sed 's/^/- /' "$unresolved"
  fi
  echo
  for manifest in go.mod go.work; do
    baseline="$metadata_dir/baseline/$manifest"
    patched="$metadata_dir/patched/$manifest"
    if [[ -f "$baseline" && -f "$patched" ]] && ! cmp -s "$baseline" "$patched"; then
      echo "<details><summary>$tool $manifest changes</summary>"
      echo
      echo '<pre>'
      diff -u "$baseline" "$patched" || true
      echo '</pre>'
      echo
      echo '</details>'
      echo
    fi
  done
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

echo "Built remediated $tool for linux/$arch at $binary_output/$tool"
