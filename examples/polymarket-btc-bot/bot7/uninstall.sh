#!/bin/bash
# Stops bot 7 and removes the auto-start. Keeps the code, trade log and backups.
PL="$HOME/Library/LaunchAgents/com.paper.bot7.plist"
launchctl bootout "gui/$(id -u)" "$PL" 2>/dev/null || true
rm -f "$PL"; pkill -f "lab/finalmin.py" 2>/dev/null || true
echo "Bot 7 stopped and will not start again. Your trade log is still in lab/finalmin.jsonl."
