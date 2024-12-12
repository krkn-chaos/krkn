export KRKNCTL_INPUT=$(cat krknctl-input.json|tr -d "\n")
envsubst '${KRKNCTL_INPUT}' < Dockerfile.template > Dockerfile