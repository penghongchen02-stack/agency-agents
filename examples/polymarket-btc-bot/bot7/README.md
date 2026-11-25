# Bot 7: final-minute paper bot (Polymarket US)

**Paper only.** It reads public Polymarket US and Coinbase prices. It places no orders and needs no keys or passwords.

## What it does
Polymarket US crypto Up/Down markets (BTC, ETH, SOL, XRP; 5-minute, 15-minute, 1-hour) settle Up when the
price at the end is at or above the start price. With 45, 30 and 15 seconds left, bot 7 estimates the chance of Up
from the live Coinbase price and how much the coin has been moving. If Polymarket sells Up (or Down) at least
3¢ below that chance after the fee, it records a paper buy of up to 100 shares at the real asking price.
Only the first trade in each market counts. Results come from Polymarket's own official outcome.

## Protection against changes
- `SHA256SUMS` holds the fingerprint of every code file. `run.sh` checks it first and **refuses to start
  if any file was changed or damaged**. Check by hand with `./verify.sh`.
- `install.sh` (Mac) makes the code files read-only.
- `lab/finalmin.py` is byte-for-byte the bot that was tested. Only the three helpers it uses are included
  (`get`, `PM`, `pm_read`), copied unchanged.
- The trade log `lab/finalmin.jsonl` is only ever added to, and `run.sh` copies it to `backups/` each day.

## Run it in a Claude Code cloud session
1. Start a session on this repo and branch.
2. From this folder, run `./run.sh` as a tracked background task (2-hour limit), and restart it whenever
   it stops (an hourly scheduled check works).
3. See results: `python3 -I lab/report.py`. Check health: `./status.sh`.

## Run it on a Mac
1. Copy this folder to your home folder: `cp -R bot7 ~/bot7 && cd ~/bot7`
2. `./install.sh` (checks Python and Polymarket access, locks the code, starts bot 7 at every login)
3. `./status.sh` to check it. `python3 -I lab/report.py` for results. `./uninstall.sh` to stop it.
4. Keep the Mac plugged in with the lid open; it stays awake while bot 7 runs.

Only run it where Polymarket US is legally available to you.
