#!/bin/bash
set -e
# Run SSH setup
./containers/setup-ssh.sh
# Change to kraken directory

# Execute the main command
exec python3.9 run_kraken.py "$@"
