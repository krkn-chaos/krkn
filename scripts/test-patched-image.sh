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

# setup-docker-action may expose its daemon on a runner-local Unix socket.
# Pass that socket through to the KinD service, which starts nested containers.
if [[ ${DOCKER_SOCKET:-} == unix://* ]]; then
  export DOCKER_SOCKET=${DOCKER_SOCKET#unix://}
elif [[ -z ${DOCKER_SOCKET:-} && ${DOCKER_HOST:-} == unix://* ]]; then
  export DOCKER_SOCKET=${DOCKER_HOST#unix://}
fi

if docker compose version >/dev/null 2>&1; then
  compose_command=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_command=(docker-compose)
else
  echo "error: Docker Compose was not found" >&2
  echo "install the Docker Compose plugin ('docker compose') or CLI ('docker-compose')" >&2
  exit 127
fi

compose_args=(
  -p "$project_name"
  -f "$repo_root/CI/tests_v2/compose.yaml"
)

if ! docker image inspect "$runtime_image" >/dev/null 2>&1; then
  echo "error: local patched image '$runtime_image' was not found" >&2
  echo "build or pull the patched image first, then pass its image reference" >&2
  exit 1
fi

cleanup() {
  status=$?
  trap - EXIT
  if ! "${compose_command[@]}" "${compose_args[@]}" down --volumes --remove-orphans; then
    echo "warning: Compose cleanup failed for project $project_name" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

"${compose_command[@]}" "${compose_args[@]}" build kind functional-tests

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

"${compose_command[@]}" "${compose_args[@]}" run --rm functional-tests "${pytest_args[@]}"
