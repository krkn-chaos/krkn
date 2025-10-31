#!/bin/bash
# Run SSH setup
setup-ssh.sh
# Change to kraken directory

# Execute the main command
exec python3.9 run_kraken.py "$@"
