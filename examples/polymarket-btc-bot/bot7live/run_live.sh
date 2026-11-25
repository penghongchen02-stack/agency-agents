#!/bin/bash
# Keeps bot 7 LIVE running; restarts it 10 s after any stop. Stop for good with Ctrl-C (or create a STOP file to pause orders).
cd "$(dirname "$0")"
while true; do python3 -I bot7live.py 2>&1 | tee -a live_run.log; [ -f STOP ] && echo "STOP file present - not restarting." && exit 0; sleep 10; done
