#!/bin/bash
# Keeps bot 7Q running (restarts 10 s after any stop). Ctrl-C stops it and cancels its open orders.
cd "$(dirname "$0")"
while true; do python3 -I bot7q.py 2>&1 | tee -a maker_run.log; [ -f STOP ] && echo "STOP file present - not restarting." && exit 0; sleep 10; done
