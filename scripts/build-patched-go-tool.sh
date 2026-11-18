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

image_vendor_command=
download_command='go mod download'
case "$tool" in
  oc)
    source_url=https://github.com/openshift/oc.git
    git clone --depth 1 --branch release-5.1 --single-branch "$source_url" "$source_dir"
    vendor_command='go mod vendor'
    build_command='cd /workspace && go mod vendor && make GO_REQUIRED_MIN_VERSION:= oc && install -m 0755 /workspace/oc /out/oc'
    ;;
  virtctl)
    source_url=https://github.com/kubevirt/kubevirt.git
    git clone --depth 1 "$source_url" "$source_dir"
    vendor_command='go work vendor'
    image_vendor_command='GOWORK=off go mod vendor'
    download_command='GOWORK=off go mod download'
    build_command='cd /workspace && go work vendor && go build -o /out/virtctl ./cmd/virtctl/'
    ;;
  yq)
    source_url=https://github.com/mikefarah/yq.git
    git clone --depth 1 --branch v4.44.6 "$source_url" "$source_dir"
    vendor_command='go mod vendor'
    build_command='cd /workspace && go mod vendor && go build -ldflags="-s -w" -o /out/yq .'
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
if [[ "$tool" == virtctl ]]; then
  # Copa currently runs `go mod vendor` after patching. Hide workspace files
  # from its builder image, then restore them from the source checkout when
  # compiling the patched workspace below.
  rm -f "$context_dir/source/go.work" "$context_dir/source/go.work.sum"
fi
printf '**/.git\n**/.git/**\n' > "$context_dir/.dockerignore"
cat > "$context_dir/Dockerfile" <<'DOCKERFILE'
FROM golang:1.26
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git make gcc pkg-config libkrb5-dev libgpgme-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY source/ /workspace/
DOCKERFILE
image_vendor_command=${image_vendor_command:-$vendor_command}
printf 'RUN %s\n' "$image_vendor_command" >> "$context_dir/Dockerfile"

run_id=${GITHUB_RUN_ID:-local}
image="localhost/krkn-go-tool:${tool}-${run_id}-${arch}"
patched_image="localhost/krkn-go-tool:${tool}-${run_id}-${arch}-patched"

docker build --pull --platform "linux/$arch" -t "$image" "$context_dir"

before_report="$report_dir/grype-${tool}-${arch}-before.json"
after_report="$report_dir/grype-${tool}-${arch}-after.json"
exclude_modules=()
if [[ "$tool" == oc ]]; then
  # These updates are incompatible with the source versions used by oc:
  # distribution/v3 removed imported packages, and BuildKit/go-archive changes
  # removed archive.Compression still used by Docker's archive package.
  exclude_modules=(
    github.com/distribution/distribution/v3
    github.com/moby/buildkit
    github.com/moby/go-archive
  )
fi
if ((${#exclude_modules[@]})); then
  excluded_modules_json=$(printf '%s\n' "${exclude_modules[@]}" | jq -R . | jq -s .)
else
  excluded_modules_json='[]'
fi
filter_copa_report() {
  local input_report=$1
  local output_report=$2
  jq --argjson excluded "$excluded_modules_json" '
    .matches |= map(select(
      .artifact.type != "go-module"
      or (.artifact.name as $name | ($excluded | index($name)) == null)
    ))
  ' "$input_report" > "$output_report"
}
# Grype's image catalogers discover Go modules from compiled binaries; the
# Go module file cataloger is enabled for directory scans. Scan the checked
# out source so Copa receives vulnerable module versions from go.mod.
SYFT_GOLANG_USE_PACKAGES_LIB=false \
  grype "dir:$source_dir" --output json --file "$before_report"
before_copa_report="$report_dir/grype-${tool}-${arch}-copa.json"
filter_copa_report "$before_report" "$before_copa_report"
go_module_matches=$(jq '[.matches[]? | select(.artifact.type == "go-module")] | length' "$before_report")
echo "Grype Go module vulnerability matches for $tool ($arch): $go_module_matches"
if ((${#exclude_modules[@]})); then
  echo "Excluding module updates for $tool: ${exclude_modules[*]}"
fi

copa_manifest="$report_dir/copa-${tool}-${arch}.json"
KRKN_COPA_ARCH="$arch" copa-grype "$before_copa_report" > "$copa_manifest"
update_count=$(jq '.langupdates | length' "$copa_manifest")
echo "Grype language updates for $tool ($arch): $update_count"

if ((update_count > 0)); then
  KRKN_COPA_ARCH="$arch" COPA_EXPERIMENTAL=1 copa patch \
    -i "$image" \
    -r "$before_copa_report" \
    -t "$patched_image" \
    -a docker:// \
    --scanner grype \
    --pkg-types library \
    --library-patch-level "${KRKN_COPA_LIBRARY_PATCH_LEVEL:-minor}"
else
  docker tag "$image" "$patched_image"
fi

docker image inspect "$patched_image" >/dev/null
patched_source_dir="$work_dir/patched-source"
patched_manifests_archive="$work_dir/patched-manifests.tar"
mkdir -p "$patched_source_dir"
cp -R "$source_dir/." "$patched_source_dir/"
docker run --rm --entrypoint /bin/bash "$patched_image" -lc \
  'cd /workspace && find . -type d \( -name .git -o -name vendor \) -prune -o -type f \( -name go.mod -o -name go.sum -o -name go.work -o -name go.work.sum \) -print0 | tar --null --files-from=- --create --file=-' \
  > "$patched_manifests_archive"
tar --extract --file="$patched_manifests_archive" --directory "$patched_source_dir"

# Save the final patched Go module metadata for the build artifact and summary.
(
  cd "$patched_source_dir"
  find . -type d \( -name .git -o -name vendor \) -prune -o \
    -type f \( -name go.mod -o -name go.sum -o -name go.work -o -name go.work.sum \) -print0 \
    | tar --null --files-from=- --create --file=-
) | tar --extract --file=- --directory "$metadata_dir/patched"

# Rescan the final source manifests. The binary scan alone cannot show the
# module-file state Copa changed and may not catalog all Go dependency records.
SYFT_GOLANG_USE_PACKAGES_LIB=false \
  grype "dir:$patched_source_dir" --output json --file "$after_report"
after_copa_report="$report_dir/grype-${tool}-${arch}-after-copa.json"
filter_copa_report "$after_report" "$after_copa_report"
after_copa_manifest="$report_dir/copa-${tool}-${arch}-after.json"
KRKN_COPA_ARCH="$arch" copa-grype "$after_copa_report" > "$after_copa_manifest"
remaining=$(jq '.langupdates | length' "$after_copa_manifest")
if (( remaining > 0 )); then
  echo "warning: $remaining patch-level eligible Go module findings remain for $tool ($arch) after Copa" >&2
fi

build_command="set -Eeuo pipefail; mkdir -p /tmp/go-home /tmp/go-path /tmp/go-cache /tmp/go-mod-cache; cd /workspace; command -v go; go version; for attempt in 1 2 3; do if $download_command; then break; fi; if [ \"\$attempt\" -eq 3 ]; then exit 1; fi; sleep \$((1 << (attempt - 1))); done; $build_command"
runner_uid=$(id -u)
runner_gid=$(id -g)
docker run --rm --platform "linux/$arch" \
  --user "$runner_uid:$runner_gid" \
  -e HOME=/tmp/go-home \
  -e GOPATH=/tmp/go-path \
  -e GOCACHE=/tmp/go-cache \
  -e GOMODCACHE=/tmp/go-mod-cache \
  -e "GOMAXPROCS=${GOMAXPROCS:-2}" \
  -e "GOFLAGS=${GOFLAGS:--p=2}" \
  -v "$patched_source_dir:/workspace" \
  -v "$binary_output:/out" \
  --entrypoint /bin/bash \
  "$patched_image" -c "$build_command"

if [[ ! -s "$binary_output/$tool" ]]; then
  echo "error: build did not produce $binary_output/$tool" >&2
  exit 1
fi

binary_report="$report_dir/grype-${tool}-${arch}-binary.json"
binary_manifest="$report_dir/copa-${tool}-${arch}-binary.json"
grype "dir:$binary_output" --output json --file "$binary_report"
binary_copa_report="$report_dir/grype-${tool}-${arch}-binary-copa.json"
filter_copa_report "$binary_report" "$binary_copa_report"
KRKN_COPA_ARCH="$arch" copa-grype "$binary_copa_report" > "$binary_manifest"
binary_remaining=$(jq '.langupdates | length' "$binary_manifest")
if (( binary_remaining > 0 )); then
  echo "warning: $binary_remaining patch-level eligible Go module findings remain in rebuilt $tool ($arch)" >&2
fi

{
  echo "### Go dependency patch: $tool ($arch)"
  echo
  echo "- Source: $source_url@$source_commit"
  echo "- Grype Go module vulnerability matches before patch: $go_module_matches"
  echo "- Grype fixed module findings before patch: $(jq '[.matches[]? | select(.artifact.type == "go-module" and .vulnerability.fix.state == "fixed")] | length' "$before_report")"
  echo "- Copa update entries: $update_count"
  jq -r '.langupdates[]? | "- Updated: \(.name) \(.installedVersion) → \(.fixedVersion) (\(.vulnerabilityID))"' "$copa_manifest"
  echo "- Grype eligible module updates after Copa: $remaining"
  echo "- Grype eligible module updates in rebuilt binary: $binary_remaining"
  if jq -e '[.matches[]? | select(.artifact.type == "go-module")] | length > 0' "$after_report" >/dev/null; then
    echo "- Remaining Go module vulnerability findings (full list):"
    jq -r '
      [.matches[]?
       | select(.artifact.type == "go-module")
       | {
           module: .artifact.name,
           version: .artifact.version,
           id: .vulnerability.id,
           fixes: (.vulnerability.fix.versions // [])
         }]
      | unique_by([.module, .version, .id])[]
      | "  - \(.module)@\(.version): \(.id) (fixed versions: \(if (.fixes | length) > 0 then (.fixes | join(", ")) else "none reported" end))"
    ' "$after_report"
  fi
  if ((${#exclude_modules[@]})); then
    echo "- Copa-excluded modules (compile compatibility): ${exclude_modules[*]}"
  fi
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

