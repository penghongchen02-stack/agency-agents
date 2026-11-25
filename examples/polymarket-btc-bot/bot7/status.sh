#!/bin/bash
# Shows whether bot 7 is running, whether its code is intact, and its latest activity.
cd "$(dirname "$0")"
./verify.sh
if pgrep -f "lab/finalmin.py" >/dev/null; then echo "RUNNING: bot 7 is running (paper)."; else echo "NOT RUNNING: bot 7 is not running right now."; fi
[ -f lab/finalmin.jsonl ] && python3 -I -c 'import json,time
l=open("lab/finalmin.jsonl").read().strip().splitlines()
print("Trades logged:",len(l)); print("Latest trade:",time.strftime("%Y-%m-%d %H:%M UTC",time.gmtime(json.loads(l[-1])["t"]))) if l else None'
echo "Last log lines:"; tail -n 3 logs/bot7.log 2>/dev/null
