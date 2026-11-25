# Bot 7 guide

Everything you need to run bot 7, check it and understand its results.

**Bot 7 is a paper bot.** It reads public prices from Polymarket US and Coinbase. It places no orders, holds no money, and needs no keys or passwords. Only run it where Polymarket US is legally available to you.

---

## 1. What bot 7 does

Polymarket US lists crypto **Up/Down** markets for BTC, ETH, SOL and XRP. Each one lasts 5 minutes, 15 minutes or 1 hour.

- Each market asks one question: will the price at the end be at or above the start price? If yes, it settles **Up**; otherwise **Down**.
- A winning share pays $1 and a losing share pays $0. The price of a share is roughly the market's guess at the chance of winning.
- The settlement uses the CF Benchmarks index. Polymarket publishes the start price ("price to beat").

Bot 7 trades only in the **last minute** of a market:

1. It reads the Coinbase price every second for all 4 coins.
2. With **45, 30 and 15 seconds left**, it estimates the final price. It uses the price so far, how much the coin has been moving, and a small learned correction between Coinbase and Polymarket's index.
3. It turns that estimate into a chance of Up (for example 91%) and a chance of Down (9%).
4. It reads Polymarket's real order book. If Up or Down is for sale at least **3¢ below** the bot's chance after the fee, it records a paper buy of up to **100 shares** at the real asking price.
5. **Only the first trade in each market counts.** It never buys the other side later.
6. When the market ends, the result comes from **Polymarket's own official outcome**.

The fee used is 0.095 × 0.3 × p × (1 − p) per share, where p is the price paid.

## 2. Results so far (paper)

All results are checked against Polymarket's official outcomes.

| Measure | Value |
|---|---|
| All-time (Nov 22–25, 2026) | 944 markets, **+$7,816** |
| Best full day (Nov 24, 22 hours running) | 420 trades, 312 won, **+$3,287** |
| Last 24-hour test | 449 markets, 74% won, +13.2¢ per share, **+$3,460**, 1 losing hour of 25 |
| Average win / average loss | +$16.13 / −$16.36 |
| Win rate | about 75% |
| Profit kept per share, after fees | about 14¢ |
| Trades per day | about 370–420 |
| Shares per trade | about 59 on average (capped at 100; fewer when fewer are for sale) |
| Money spent per trade | about $36 |

**Compared with faster versions:**
- A live price stream (7S2) and a 4-exchange price (7M) did **not** beat bot 7. 7M did worse.
- A version that buys only what is still for sale 1 second later (7R) made about **0.6% less** than bot 7. This means very few other traders are taking these prices right now.

**What to expect with real money:** plan for roughly **half the paper number**. Real orders can miss, fees may be higher, and nights and market pauses earn less. Profit does not grow much with a bigger budget, because the limit is how many cheap shares are for sale.

## 3. What's in the package

| File | What it is |
|---|---|
| `lab/finalmin.py` | **Bot 7 itself.** A byte-for-byte copy of the tested bot. |
| `xvenue/xscan.py`, `xvenue/paperbot.py` | The only two helpers bot 7 uses: read a web page, and read a Polymarket order book. Copied unchanged. No Kalshi code. |
| `xvenue/pmres.py` | Gets each market's official result from Polymarket US. |
| `lab/report.py` | Prints results per day and in total. |
| `run.sh` | Keeps bot 7 running, restarts it if it stops, and backs up the trade log daily. |
| `verify.sh` | Checks that the code is exactly the tested version. |
| `SHA256SUMS` | The fingerprints `verify.sh` checks against. |
| `install.sh`, `uninstall.sh` | Mac only: start bot 7 automatically at login, or remove that. |
| `status.sh` | Shows whether bot 7 is running, whether the code is intact, and its latest trade. |
| `README.md` | Short version of this guide. |

Files created while it runs, which are never part of the code:
- `lab/finalmin.jsonl`: the trade log, only ever added to.
- `logs/`: what the bot printed while running.
- `backups/`: a daily copy of the trade log.

## 4. How bot 7 is protected from changes or damage

- **Fingerprint check.** Every code file has a SHA-256 fingerprint in `SHA256SUMS`. `run.sh` checks them before starting and **refuses to start** if even one character has changed. Run `./verify.sh` anytime; it should say `OK`.
- **Read-only on a Mac.** `install.sh` locks the code files so they can't be edited by accident.
- **Original kept in your repo.** The tested copy is saved in your GitHub repo `penghongchen02-stack/agency-agents`, branch `claude/magical-gauss-2jzelh`, folder `examples/polymarket-btc-bot/bot7`. If anything is ever damaged, download it again from there.
- **Trade log is protected too.** It is only ever added to, and a backup is made every day.

If `./verify.sh` ever says **STOP**, don't edit anything. Replace the folder with a fresh copy from the repo.

## 5. How to run it

### Option A: a Claude Code cloud session (already set up)
A session named **"Bot 7 paper runner (Polymarket US)"** runs bot 7 for you:
- It checks the code, starts bot 7, and restarts it every hour if it has stopped.
- It reports one line each hour and a full report every 6 hours.
- Open that session in Claude Code to see its reports, or ask it "report".

Limits:
- A cloud session can be restarted by the system. Bot 7 then waits until the next hourly check.
- After each start, bot 7 needs about 40 minutes before its first trade.

### Option B: your Mac
1. Download the package and put the `bot7` folder in your **home folder** (not Desktop, Documents or Downloads, where macOS blocks background apps). In Terminal:
   ```
   cp -R ~/Downloads/bot7 ~/bot7
   cd ~/bot7
   ```
2. Make the scripts runnable (needed after unzipping) and install:
   ```
   chmod +x *.sh
   ./install.sh
   ```
   This checks that Python works and that Polymarket US data is reachable, locks the code, and starts bot 7. Bot 7 then starts again by itself after every restart or login.
   - If it says `python3 not found`, run `xcode-select --install`, then `./install.sh` again.
   - If it can't reach Polymarket and you installed Python from python.org, run that Python's `Install Certificates.command`, then try again.
3. Keep the Mac **plugged in with the lid open**. Bot 7 keeps it awake while it runs, but closing the lid puts it to sleep.
4. Check it anytime:
   ```
   ./status.sh
   python3 -I lab/report.py
   ```
5. To stop it for good: `./uninstall.sh` (your trade log is kept).

### Option C: a small Linux server ($5–10 a month)
1. Rent a basic Ubuntu server from any provider. Choose a region where Polymarket US is legally available to you.
2. Copy the `bot7` folder onto it and `cd` into it.
3. Run `./verify.sh`. It should say OK.
4. To start it, and to keep it running after reboots, add this to crontab (`crontab -e`):
   ```
   @reboot cd ~/bot7 && nohup ./run.sh >/dev/null 2>&1 &
   ```
   Then start it once by hand: `nohup ./run.sh >/dev/null 2>&1 &`
5. Check it with `./status.sh` and `python3 -I lab/report.py`.

No extra software is needed. Bot 7 uses only Python 3's standard library.

## 6. Reading the results

`python3 -I lab/report.py` prints something like:
```
Bot 7 paper results (results from Polymarket US; times UTC)
  2026-11-24:  420 markets,  312 won ( 74%), +13.5c/share, paper $ +3287.00
  TOTAL     :  420 markets,  312 won ( 74%), +13.5c/share, paper $ +3287.00
  waiting for Polymarket to settle: 2
```
- **c/share** is the profit per share after fees. Around 12–15¢ is normal.
- **Waiting** trades are markets that haven't settled yet. They are counted on the next run.

## 7. Normal things that aren't problems

- **No trades for the first ~40 minutes after a start.** Bot 7 is learning the price difference between Coinbase and Polymarket.
- **Quiet hours.** If Polymarket pauses its 5-minute markets (it did once, 11:05–12:10 UTC on Nov 24), there is nothing to trade.
- **Losing hours happen.** About 1 hour in 20 loses a little, usually under $15.

## 8. Warning signs to watch for

- **c/share falling below about 5¢** for a full day. The gap may be closing because other traders found it, or fees changed.
- **`verify.sh` says STOP.** The code changed. Re-download it; don't edit it.
- **Many hours with no trades** while Polymarket markets are open. Check `./status.sh` and `logs/bot7.log`.

## 9. Before using real money

This is a paper test. It shows what the bot would have done at real Polymarket prices, but it has never placed a real order. If you decide to try real trading, do it yourself on your own Polymarket US account, only if it is legally available to you, and start with a handful of small ($5–10) trades. That shows whether your real fills and fees match the paper results. Never paste account keys or passwords into a chat or into this folder.
