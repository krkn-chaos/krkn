#!/bin/bash
# Run SSH setup
/home/krkn/setup-ssh.sh
# Change to kraken directory
cd /home/krkn/kraken
# Execute the main command
exec python3.9 run_kraken.py "$@"
