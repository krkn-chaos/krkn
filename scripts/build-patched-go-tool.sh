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

download_command='go mod download'
case "$tool" in
  oc)
    source_url=https://github.com/openshift/oc.git
    git clone --depth 1 --branch release-5.1 --single-branch "$source_url" "$source_dir"
    build_command='cd /workspace && go mod vendor && make GO_REQUIRED_MIN_VERSION:= oc && install -m 0755 /workspace/oc /out/oc'
    ;;
  virtctl)
    source_url=https://github.com/kubevirt/kubevirt.git
    git clone --depth 1 "$source_url" "$source_dir"
    download_command='GOWORK=off go mod download'
    build_command='cd /workspace && go work vendor && go build -o /out/virtctl ./cmd/virtctl/'
    ;;
  yq)
    source_url=https://github.com/mikefarah/yq.git
    git clone --depth 1 --branch v4.44.6 "$source_url" "$source_dir"
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
# out source so the Copa Grype adapter receives module versions and manifest
# locations from every go.mod.
SYFT_GOLANG_USE_PACKAGES_LIB=false \
  grype "dir:$source_dir" --output json --file "$before_report"
before_copa_report="$report_dir/grype-${tool}-${arch}-copa.json"
filter_copa_report "$before_report" "$before_copa_report"
go_module_matches=$(jq '[.matches[]? | select(.artifact.type == "go-module")] | length' "$before_report")
eligible_go_module_matches=$(jq '[.matches[]? | select(.artifact.type == "go-module")] | length' "$before_copa_report")
echo "Grype Go module vulnerability matches for $tool ($arch): $go_module_matches"
if ((${#exclude_modules[@]})); then
  echo "Excluding module updates for $tool: ${exclude_modules[*]}"
fi

# Copa's Grype adapter selects a fix version for each finding, but Copa's Go
# patch command applies its generated `go get`s from one module root and in
# sequence. Split the report by the go.mod location, then apply all selected
# versions for that module in one `go get` invocation. This works for both
# single-module tools and repositories with Go workspaces without any
# tool-specific module-path rules.
copa_manifest="$report_dir/copa-${tool}-${arch}.json"
module_manifests=()
module_count=0
module_updates=0
module_updates_applied=0
module_updates_skipped=0
module_scan_matches=0
module_index=0
while IFS= read -r -d '' go_mod_path; do
  module_index=$((module_index + 1))
  module_dir=${go_mod_path%/go.mod}
  relative_go_mod=${go_mod_path#"$source_dir"/}
  report_go_mod="/$relative_go_mod"
  module_key=${relative_go_mod%/go.mod}
  module_key=${module_key//\//-}
  module_key=${module_key:-root}
  module_report="$report_dir/grype-${tool}-${arch}-module-${module_index}-${module_key}.json"
  module_copa_input="$report_dir/grype-${tool}-${arch}-module-${module_index}-${module_key}-copa.json"
  module_plan_raw="$work_dir/copa-${module_index}.json"
  module_plan="$report_dir/copa-${tool}-${arch}-module-${module_index}-${module_key}.json"

  jq --arg go_mod "$report_go_mod" '
    .matches |= map(select(
      .artifact.type == "go-module"
      and any(.artifact.locations[]?; .path == $go_mod or .accessPath == $go_mod)
    ))
  ' "$before_report" > "$module_report"
  filter_copa_report "$module_report" "$module_copa_input"
  module_scan_matches=$((module_scan_matches + $(jq '.matches | length' "$module_copa_input")))
  KRKN_COPA_ARCH="$arch" copa-grype "$module_copa_input" > "$module_plan_raw"
  jq --arg manifest "$relative_go_mod" \
    '.langupdates |= map(. + {manifestPath: $manifest})' \
    "$module_plan_raw" > "$module_plan"
  module_manifests+=("$module_plan")

  mapfile -t go_get_args < <(
    jq -r '
      [.langupdates[]?
       | select((.name | type) == "string" and (.fixedVersion | type) == "string")
       | "\(.name)@\(.fixedVersion)"]
      | unique[]
    ' "$module_plan_raw"
  )
  if ((${#go_get_args[@]} == 0)); then
    continue
  fi

  module_count=$((module_count + 1))
  module_updates=$((module_updates + ${#go_get_args[@]}))
  backup_dir="$work_dir/module-backup-$module_index"
  mkdir -p "$backup_dir"
  cp "$module_dir/go.mod" "$backup_dir/go.mod"
  had_go_sum=false
  if [[ -f "$module_dir/go.sum" ]]; then
    cp "$module_dir/go.sum" "$backup_dir/go.sum"
    had_go_sum=true
  fi

  printf 'Applying %d Copa-selected updates to %s\n' "${#go_get_args[@]}" "$relative_go_mod"
  if (cd "$module_dir" && GOWORK=off go get "${go_get_args[@]}"); then
    module_updates_applied=$((module_updates_applied + ${#go_get_args[@]}))
  else
    cp "$backup_dir/go.mod" "$module_dir/go.mod"
    if [[ "$had_go_sum" == true ]]; then
      cp "$backup_dir/go.sum" "$module_dir/go.sum"
    else
      rm -f "$module_dir/go.sum"
    fi
    module_updates_skipped=$((module_updates_skipped + ${#go_get_args[@]}))
    echo "warning: Go rejected the grouped updates for $relative_go_mod; keeping its original manifests" >&2
  fi
done < <(
  find "$source_dir" -type d \( -name .git -o -name vendor \) -prune -o \
    -type f -name go.mod -print0 | sort -z
)

if ((${#module_manifests[@]})); then
  jq -s --arg arch "$arch" '
    {
      apiVersion: "v1alpha2",
      metadata: (.[0].metadata // {config: {arch: $arch}}),
      osupdates: [],
      langupdates: ([.[].langupdates[]?]
        | unique_by([.manifestPath, .name, .installedVersion, .fixedVersion, .vulnerabilityID]))
    }
  ' "${module_manifests[@]}" > "$copa_manifest"
else
  echo "error: no Go module manifests found in $source_dir" >&2
  exit 1
fi

echo "Copa-selected Go updates for $tool ($arch): $module_updates across $module_count modules"
if ((module_scan_matches != eligible_go_module_matches)); then
  echo "warning: assigned $module_scan_matches of $eligible_go_module_matches eligible Grype Go module matches to discovered go.mod files" >&2
fi
if ((module_updates_skipped > 0)); then
  echo "warning: skipped $module_updates_skipped Copa-selected updates after Go rejected a module update" >&2
fi
patched_source_dir=$source_dir

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
  echo "warning: $remaining patch-level eligible Go module findings remain for $tool ($arch) after Go module updates" >&2
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
  "$image" -c "$build_command"

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
  echo "- Copa-selected Go updates: $module_updates across $module_count module(s)"
  echo "- Go updates applied: $module_updates_applied; skipped: $module_updates_skipped"
  jq -r '.langupdates[]? | "- \(.manifestPath): selected \(.name) \(.installedVersion) → \(.fixedVersion) (\(.vulnerabilityID))"' "$copa_manifest"
  echo "- Grype eligible module updates after Go module updates: $remaining"
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

