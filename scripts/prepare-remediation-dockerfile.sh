#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
containers_dir="$repo_root/containers"
export KRKNCTL_INPUT
KRKNCTL_INPUT=$(tr -d '\n' < "$containers_dir/krknctl-input.json")
envsubst '${KRKNCTL_INPUT}' \
    < "$containers_dir/Dockerfile.remediation.template" \
    > "$containers_dir/Dockerfile.remediation"

