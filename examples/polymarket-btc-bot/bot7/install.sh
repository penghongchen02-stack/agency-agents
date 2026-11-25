#!/bin/bash
# One-time setup on a Mac: checks Python and Polymarket access, locks the code read-only,
# and tells macOS to start bot 7 at login and restart it if it ever stops.
set -e
cd "$(dirname "$0")"; DIR="$(pwd)"
case "$DIR" in "$HOME"/Desktop*|"$HOME"/Documents*|"$HOME"/Downloads*)
  echo "Move this folder to your home folder first (for example: mv \"$DIR\" ~/bot7), then run install.sh from there."; exit 1;; esac
command -v python3 >/dev/null || { echo "python3 not found. Run: xcode-select --install   then run install.sh again."; exit 1; }
python3 -I -c 'import json,urllib.request
r=urllib.request.urlopen(urllib.request.Request("https://gateway.polymarket.us/v1/markets?limit=1",headers={"User-Agent":"market-research/1.0"}),timeout=10)
json.load(r); print("OK: Polymarket US public data is reachable.")' || {
  echo "Could not read Polymarket US data. If you installed Python from python.org, run its 'Install Certificates.command' and try again."; exit 1; }
./verify.sh
chmod 444 lab/finalmin.py lab/report.py xvenue/*.py SHA256SUMS; chmod 555 run.sh verify.sh install.sh uninstall.sh status.sh
mkdir -p logs backups "$HOME/Library/LaunchAgents"
PL="$HOME/Library/LaunchAgents/com.paper.bot7.plist"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.paper.bot7</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StandardOutPath</key><string>$DIR/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.log</string>
</dict></plist>
PLIST
launchctl bootout "gui/$(id -u)" "$PL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PL"
echo "Installed. Bot 7 is running now and will start again after every restart or login."
echo "Check it with: ./status.sh     See results with: python3 -I lab/report.py"
