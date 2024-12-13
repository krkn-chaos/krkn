SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export KRKNCTL_INPUT=$(cat krknctl-input.json|tr -d "\n")

envsubst '${KRKNCTL_INPUT}' < Dockerfile.template > Dockerfile