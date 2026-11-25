#!/bin/bash
# Keeps bot 7 (PAPER only) running. Started by macOS at login (see install.sh).
# Refuses to run if the code is not the tested version. Backs up the trade log once a day.
cd "$(dirname "$0")"; mkdir -p logs backups
if ! ./verify.sh >> logs/bot7.log 2>&1; then date -u >> logs/bot7.log; sleep 3600; exit 1; fi
PY=$(command -v python3); KEEP=""; command -v caffeinate >/dev/null && KEEP="caffeinate -i -s"
while true; do
  [ -f lab/finalmin.jsonl ] && cp -p lab/finalmin.jsonl "backups/finalmin-$(date -u +%Y%m%d).jsonl"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') UTC starting bot 7 (paper)" >> logs/bot7.log
  $KEEP "$PY" -I lab/finalmin.py 86400 >> logs/bot7.log 2>&1
  sleep 5
done
