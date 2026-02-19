#!/bin/bash
# Run SSH setup
./containers/setup-ssh.sh
# Change to kraken directory

# Execute the main command
exec python3 run_kraken.py "$@"
