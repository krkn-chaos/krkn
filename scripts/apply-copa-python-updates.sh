#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 SOURCE_IMAGE COPA_REPORT TARGET_IMAGE ARCH" >&2
}

if [[ $# -ne 4 ]]; then
  usage
  exit 2
fi

source_image=$1
report=$2
target_image=$3
arch=$4
: "${KRKN_COPA_LIBRARY_PATCH_LEVEL:?KRKN_COPA_LIBRARY_PATCH_LEVEL must be set}"

if [[ ! -s "$report" ]]; then
  echo "error: Copa update manifest is missing or empty: $report" >&2
  exit 1
fi

tmp_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/copa-python-updates.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT

packages=()
while IFS= read -r package; do
  packages+=("$package")
done < <(jq -r '[.langupdates[]?.name | select(type == "string" and length > 0)] | unique[]' "$report")
current_image=$source_image
applied=0
skipped=0
index=0
image_repository=${target_image%:*}
target_tag=${target_image##*:}

for package in "${packages[@]}"; do
  index=$((index + 1))
  package_report="$tmp_dir/package-${index}.json"
  candidate_image="${image_repository}:candidate-${target_tag}-${index}"
  jq --arg package "$package" '.langupdates |= map(select(.name == $package))' \
    "$report" > "$package_report"

  echo "Applying Copa update for Python package $package ($arch)"
  if ! copa patch \
    --image "$current_image" \
    --report "$package_report" \
    --tag "$candidate_image" \
    --addr docker:// \
    --scanner native \
    --pkg-types library \
    --library-patch-level "$KRKN_COPA_LIBRARY_PATCH_LEVEL"; then
    echo "warning: Copa could not update $package; keeping the previous image" >&2
    skipped=$((skipped + 1))
    continue
  fi

  if ! docker image inspect "$candidate_image" >/dev/null 2>&1; then
    echo "warning: Copa produced no candidate image for $package; keeping the previous image" >&2
    skipped=$((skipped + 1))
    continue
  fi

  if docker run --rm --entrypoint python3.11 "$candidate_image" -m pip check; then
    current_image=$candidate_image
    applied=$((applied + 1))
    echo "Accepted update for $package"
  else
    echo "warning: update for $package breaks Python dependency constraints; keeping the previous image" >&2
    skipped=$((skipped + 1))
  fi
done

docker tag "$current_image" "$target_image"
docker image inspect "$target_image" >/dev/null
docker run --rm --entrypoint python3.11 "$target_image" -m pip freeze --all \
  > "$RUNNER_TEMP/patched-python-freeze-${arch}.txt"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "image=$target_image"
    echo "eligible=${#packages[@]}"
    echo "applied=$applied"
    echo "skipped=$skipped"
  } >> "$GITHUB_OUTPUT"
fi

echo "Python dependency updates for linux/$arch: $applied accepted, $skipped skipped, ${#packages[@]} eligible"
