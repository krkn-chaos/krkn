#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export KRKNCTL_INPUT
KRKNCTL_INPUT=$(tr -d '\n' < "$script_dir/krknctl-input.json")
envsubst '${KRKNCTL_INPUT}' < "$script_dir/Dockerfile.remediation.template" > "$script_dir/Dockerfile.remediation"

