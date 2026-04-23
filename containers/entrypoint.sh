#!/bin/bash
set -e
# Run SSH setup
./containers/setup-ssh.sh
# Change to kraken directory

# Execute the main command
exec "${PYTHON_CMD:-python3}" run_kraken.py "$@"
