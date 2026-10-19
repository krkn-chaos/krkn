#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/test-patched-image.sh PATCHED_IMAGE [PYTEST_ARGS...]

Build a test runner from a local patched Krkn image, run tests v2 against an
ephemeral KinD cluster, and remove the cluster when the run completes.

Example:
  scripts/test-patched-image.sh localhost/krkn:local-copa
  scripts/test-patched-image.sh localhost/krkn:local-copa -m pod_disruption -v
USAGE
}

if [[ $# -eq 1 && ( $1 == -h || $1 == --help ) ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runtime_image=$1
shift
project_name="krkn-tests-$$"

export COMPOSE_PROJECT_NAME=$project_name
export KIND_CLUSTER_NAME=$project_name
export KRKN_RUNTIME_IMAGE=$runtime_image

compose_args=(
  --project-name "$project_name"
  --file "$repo_root/CI/tests_v2/compose.yaml"
)

if ! docker image inspect "$runtime_image" >/dev/null 2>&1; then
  echo "error: local patched image '$runtime_image' was not found" >&2
  echo "build or pull the patched image first, then pass its image reference" >&2
  exit 1
fi

cleanup() {
  status=$?
  trap - EXIT
  if ! docker compose "${compose_args[@]}" down --volumes --remove-orphans; then
    echo "warning: Compose cleanup failed for project $project_name" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

docker compose "${compose_args[@]}" build kind functional-tests

pytest_args=(
  CI/tests_v2/
  -v
  --timeout=300
  --reruns=1
  --reruns-delay=5
  --html=CI/tests_v2/report.html
  -n auto
  --dist loadgroup
  --junitxml=CI/tests_v2/results.xml
)
pytest_args+=("$@")

docker compose "${compose_args[@]}" run --rm functional-tests "${pytest_args[@]}"
