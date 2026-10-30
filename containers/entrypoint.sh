#!/bin/bash
set -e

# Run a non-destructive dependency and CLI startup check when requested.
if [[ "${KRKN_DEPENDENCY_CHECK:-}" == "1" ]]; then
    python_cmd="${PYTHON_CMD:-python3}"
    echo "Checking Python dependency consistency..."
    "${python_cmd}" -m pip check
    echo "Checking Krkn CLI startup..."
    exec "${python_cmd}" run_kraken.py --help
fi
# Run SSH setup
./containers/setup-ssh.sh
# Change to kraken directory

# Execute the main command
exec "${PYTHON_CMD:-python3}" run_kraken.py "$@"
