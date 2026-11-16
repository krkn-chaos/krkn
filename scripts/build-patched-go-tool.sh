#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 TOOL ARCH BINARY_OUTPUT METADATA_DIR REPORT_DIR" >&2
  echo "Tools: oc, virtctl, yq; architectures: amd64, arm64" >&2
}

if [[ $# -ne 5 ]]; then
  usage
  exit 2
fi

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

case "$arch" in
  amd64|arm64) ;;
  *) echo "unsupported architecture: $arch" >&2; exit 2 ;;
esac

case "$tool" in
  oc)
    source_url=https://github.com/openshift/oc.git
    git clone --depth 1 --branch release-5.1 --single-branch "$source_url" "$source_dir"
    build_command='cd /workspace && go mod vendor && make GO_REQUIRED_MIN_VERSION:= oc && install -m 0755 /workspace/oc /out/oc'
    ;;
  virtctl)
    source_url=https://github.com/kubevirt/kubevirt.git
    git clone --depth 1 "$source_url" "$source_dir"
    build_command='cd /workspace && go work vendor && go build -o /out/virtctl ./cmd/virtctl/'
    ;;
  yq)
    source_url=https://github.com/mikefarah/yq.git
    git clone --depth 1 --branch v4.44.6 "$source_url" "$source_dir"
    build_command='cd /workspace && go build -ldflags="-s -w" -o /out/yq .'
    ;;
  *)
    echo "unsupported Go tool: $tool" >&2
    usage
    exit 2
    ;;
esac

source_commit=$(git -C "$source_dir" rev-parse HEAD)
printf '%s\n' "$source_url" > "$metadata_dir/source-url.txt"
printf '%s\n' "$source_commit" > "$metadata_dir/source-commit.txt"
(
  cd "$source_dir"
  find . -type d \( -name .git -o -name vendor \) -prune -o \
    -type f \( -name go.mod -o -name go.sum -o -name go.work -o -name go.work.sum \) -print0 \
    | tar --null --files-from=- --create --file=-
) | tar --extract --file=- --directory "$metadata_dir/baseline"

cp -R "$source_dir/." "$context_dir/source/"
printf '**/.git\n**/.git/**\n' > "$context_dir/.dockerignore"
cat > "$context_dir/Dockerfile" <<'DOCKERFILE'
FROM golang:1.26
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git make gcc pkg-config libkrb5-dev libgpgme-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY source/ /workspace/
DOCKERFILE

run_id=${GITHUB_RUN_ID:-local}
image="localhost/krkn-go-tool:${tool}-${run_id}-${arch}"
patched_image="localhost/krkn-go-tool:${tool}-${run_id}-${arch}-patched"

docker build --pull --platform "linux/$arch" -t "$image" "$context_dir"

before_report="$report_dir/grype-${tool}-${arch}-before.json"
after_report="$report_dir/grype-${tool}-${arch}-after.json"
copa_manifest="$report_dir/copa-${tool}-${arch}.json"
grype "docker:$image" --output json --file "$before_report"
KRKN_COPA_ARCH="$arch" copa-grype "$before_report" > "$copa_manifest"
update_count=$(jq '.langupdates | length' "$copa_manifest")
echo "Grype language updates for $tool ($arch): $update_count"

if (( update_count > 0 )); then
  KRKN_COPA_ARCH="$arch" COPA_EXPERIMENTAL=1 copa patch \
    -i "$image" \
    -r "$before_report" \
    -t "$patched_image" \
    -a docker:// \
    --scanner grype \
    --pkg-types library \
    --library-patch-level "${KRKN_COPA_LIBRARY_PATCH_LEVEL:-minor}"
else
  docker tag "$image" "$patched_image"
fi

docker image inspect "$patched_image" >/dev/null
docker run --rm --entrypoint /bin/bash "$patched_image" -lc \
  'cd /workspace && find . -type d \( -name .git -o -name vendor \) -prune -o -type f \( -name go.mod -o -name go.sum -o -name go.work -o -name go.work.sum \) -print0 | tar --null --files-from=- --create --file=-' \
  | tar --extract --file=- --directory "$metadata_dir/patched"

grype "docker:$patched_image" --output json --file "$after_report"
KRKN_COPA_ARCH="$arch" copa-grype "$after_report" > "$report_dir/copa-${tool}-${arch}-after.json"
remaining=$(jq '.langupdates | length' "$report_dir/copa-${tool}-${arch}-after.json")
if (( remaining > 0 )); then
  echo "error: $remaining patch-level eligible Go module findings remain for $tool ($arch) after Copa" >&2
  exit 1
fi

build_command="set -Eeuo pipefail; cd /workspace; for attempt in 1 2 3; do if go mod download; then break; fi; if [ \"\$attempt\" -eq 3 ]; then exit 1; fi; sleep \$((1 << (attempt - 1))); done; $build_command"
docker run --rm --platform "linux/$arch" \
  -e "GOMAXPROCS=${GOMAXPROCS:-2}" \
  -e "GOFLAGS=${GOFLAGS:--p=2}" \
  -v "$binary_output:/out" \
  --entrypoint /bin/bash \
  "$patched_image" -lc "$build_command"

if [[ ! -s "$binary_output/$tool" ]]; then
  echo "error: build did not produce $binary_output/$tool" >&2
  exit 1
fi

binary_report="$report_dir/grype-${tool}-${arch}-binary.json"
binary_manifest="$report_dir/copa-${tool}-${arch}-binary.json"
grype "dir:$binary_output" --output json --file "$binary_report"
KRKN_COPA_ARCH="$arch" copa-grype "$binary_report" > "$binary_manifest"
binary_remaining=$(jq '.langupdates | length' "$binary_manifest")
if (( binary_remaining > 0 )); then
  echo "error: $binary_remaining patch-level eligible Go module findings remain in rebuilt $tool ($arch)" >&2
  exit 1
fi

{
  echo "### Go dependency patch: $tool ($arch)"
  echo
  echo "- Source: $source_url@$source_commit"
  echo "- Grype fixed module findings before patch: $(jq '[.matches[]? | select(.artifact.type == "go-module" and .vulnerability.fix.state == "fixed")] | length' "$before_report")"
  echo "- Copa update entries: $update_count"
  jq -r '.langupdates[]? | "- Updated: \(.name) \(.installedVersion) → \(.fixedVersion) (\(.vulnerabilityID))"' "$copa_manifest"
  echo "- Grype eligible module updates after Copa: $remaining"
  echo "- Grype eligible module updates in rebuilt binary: $binary_remaining"
  echo
  for manifest in go.mod go.work; do
    baseline="$metadata_dir/baseline/$manifest"
    patched="$metadata_dir/patched/$manifest"
    if [[ -f "$baseline" && -f "$patched" ]] && ! cmp -s "$baseline" "$patched"; then
      echo "<details><summary>$tool $manifest changes</summary>"
      echo
      echo "<pre>"
      diff -u "$baseline" "$patched" || true
      echo "</pre>"
      echo
      echo "</details>"
      echo
    fi
  done
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

echo "Built patched $tool for linux/$arch at $binary_output/$tool"

