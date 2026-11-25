# Bot 7 LIVE guide

Bot 7 LIVE places **real orders with real money** on Polymarket US. It uses exactly bot 7's paper rules. Read this whole guide before you start.

> **Important**
> - Paper results don't guarantee real results. Real orders can miss, and every loss is real money.
> - Only use it if Polymarket US is legally available to you and your account is verified.
> - Run it **on your own computer**. Never paste your API keys into a chat, an AI session, an email or a file in this folder.
> - Start small. The default limits are **$5 per trade, $100 spent per day, and a $50 daily loss limit**.

---

## How it trades the same as bot 7

- It **imports bot 7's own code unchanged** (`../bot7/lab/finalmin.py`) for the price reading, the odds math and the fee rule.
- Its decision loop is a **line-for-line copy** of bot 7's. The only change is that it runs until you stop it, where the paper bot runs for a set time.
- **Before starting, it checks bot 7's fingerprints.** If bot 7's code was changed or damaged, it refuses to run.
- On a signal, bot 7 wrote a paper trade. Bot 7 LIVE instead sends a **limit, immediate-or-cancel** order at the same price.
  - It can never pay more than the price bot 7 saw.
  - Whatever isn't available right away is cancelled by the exchange.
- Same signals: 45, 30 and 15 seconds left, a gap of at least 3¢, at least 10 shares for sale, and one trade per market.

The only differences from paper are your safety limits: dollars per trade, shares per trade, daily spend and daily loss.

## Fees (from Polymarket US, Nov 2026)

API taker trades are charged `0.0695 × shares × price × (1 − price)`, with a **70% rebate paid weekly** through Dec 31, 2026.
- **Net, that's lower than the fee bot 7 assumed on paper.**
- **Up front you pay the full fee.** The rebate arrives later.

## What you need

- A **verified Polymarket US account** with money deposited (the app, then identity verification).
- A computer that stays on (Mac, Windows with WSL, or Linux) with **Python 3**.
- The two folders **side by side**: `bot7/` and `bot7live/`. They're in your repo under `examples/polymarket-btc-bot/`.

---

## Step by step

### 1. Get your API key
1. Go to **polymarket.us/developer** and sign in the same way you sign into the app (Apple, Google or email).
2. Create an API key. You get a **Key ID** and a **Secret Key**.
3. The secret is shown only once. Keep it private.

### 2. Put the folders on your computer
For example, both in your home folder:
```
~/polybot/bot7
~/polybot/bot7live
```
Then check bot 7 is intact:
```
cd ~/polybot/bot7 && chmod +x *.sh && ./verify.sh
```
It must print `OK`.

### 3. Install the one extra package (for signing orders)
```
python3 -m pip install --user cryptography
```

### 4. Save your keys, outside the bot folder
```
mkdir -p ~/.bot7live
nano ~/.bot7live/keys.json
```
Type this, with your own values:
```
{"key_id": "YOUR-KEY-ID", "secret_key": "YOUR-SECRET-KEY"}
```
Save, then lock the file so only you can read it:
```
chmod 600 ~/.bot7live/keys.json
```

### 5. Run the offline tests
```
cd ~/polybot/bot7live && python3 -I test_bot7live.py
```
These use a fake server on your computer; no real orders are placed. It must end with `ALL PASSED`.

Then prove LIVE decides and orders exactly like paper bot 7:
```
python3 -I test_same_as_paper.py 24
```
This feeds both bots the same simulated 24 hours of prices and order books and compares every trade and every order. It must print three PASS lines.

### 6. Dry run for at least a few hours (no orders)
```
cp config.example.json config.json
./run_live.sh
```
- In dry run, it signs in, shows your buying power, and for every signal asks Polymarket to **preview** the order. Nothing is bought.
- Each signal is written to `live_trades.jsonl`.
- Stop it with **Ctrl-C**.

### 7. Confirm Down orders are priced right
Polymarket prices every order on the **YES** side. To buy Down at 14¢, the bot sends "buy NO" with YES price 0.86. That is what Polymarket's docs describe, but check it before going live:
- Open `live_trades.jsonl` and find a line with `"side": "DOWN"` and `"status": "previewed"`.
- Look at its `preview` section. The cost should match **the Down price × shares** (for example about $0.70 for 5 shares at 14¢), **not** (1 − price) × shares.
- If you're unsure, send just those `preview` lines to someone you trust to check. They contain no keys.
- Only when it's correct, set `"down_price_confirmed": true` in `config.json`. Until then, live mode buys **Up only**.

### 8. Go live, small
In `config.json`:
```
"mode": "live"
```
`config.json` is set to **paper size**: up to $100 per trade, $15,000 spent per day, and a $300 daily loss limit. To start smaller, lower `max_usd_per_trade` (for example to 5). Start it with `./run_live.sh`. It prints each fill:
```
filled: BTC 5m UP at 0.86 filled 5.0 for $4.30
```

### 9. Check results
```
python3 -I live_report.py
```
This shows real fills per day, with wins, losses and profit from Polymarket's official results. Compare it with bot 7's paper results for the same days. If real profit per share is far below paper (bot 7 paper: about 14¢ per share), stop and look into it.

### 10. Stop
- **Pause new orders immediately:** create a file named `STOP` in the `bot7live` folder (`touch STOP`). Delete it to resume.
- **Stop completely:** Ctrl-C in the terminal running `run_live.sh`.
- Orders are immediate-or-cancel, so there are never resting orders left behind.
- Positions settle by themselves when each market ends, within minutes.

---

## Settings (`config.json`)

The `config.json` in this package uses paper-size limits: $100 per trade, $15,000 spent per day, $300 daily loss. The defaults below apply only if `config.json` is missing.

| Setting | Default | Meaning |
|---|---|---|
| `mode` | `dry_run` | `dry_run` = preview only, no orders. `live` = real orders. |
| `max_usd_per_trade` | 5 | Most dollars spent on one trade |
| `max_shares_per_trade` | 100 | Most shares in one trade (bot 7 used 100) |
| `daily_max_spend_usd` | 100 | Stops new orders once this much is spent in a UTC day |
| `daily_max_loss_usd` | 50 | Stops new orders when today's settled losses reach this |
| `down_price_confirmed` | false | Lets live mode buy Down. Set to true only after step 7. |

Raise limits slowly, only after several days of real results that look like the paper results.

**Paper bot 7 had no money limits.** For comparison, on paper it:
- spent up to **$96 on one trade** (average $37, up to 100 shares);
- spent about **$8,000–15,000 in total per day**. The same few hundred dollars was reused all day, since each market settles within minutes. At most about $321 was in use at once.
- had a worst drop of **$180** within a day, and no losing day.

To trade exactly like paper you would set `max_usd_per_trade` 100, `daily_max_spend_usd` about 15000 and `daily_max_loss_usd` about 300. Only do that after the small test matches paper.

## Files

| File | What it is |
|---|---|
| `bot7live.py` | The live bot |
| `run_live.sh` | Keeps it running and restarts it if it stops |
| `config.example.json` | Settings template; copy it to `config.json` |
| `live_report.py` | Real results per day |
| `test_bot7live.py` | Offline tests against a fake server |
| `test_same_as_paper.py` | Proves LIVE makes the same trades and orders as paper bot 7 |
| `why_not_filled.py` | Explains missed orders in plain words (shows no keys) |
| `live_trades.jsonl` | Every signal: previewed, filled, not filled, skipped, with the reason |
| `live_errors.log`, `live_run.log` | What happened while running |

## Troubleshooting

| Message | Fix |
|---|---|
| `No API keys found` | Do step 4 |
| `keys.json can be read by other users` | `chmod 600 ~/.bot7live/keys.json` |
| `Could not sign in (HTTP 401)` | Wrong key, or your computer's clock is more than 30 seconds off. Turn on automatic time. |
| `bot 7's code does not match its fingerprints` | Re-download the `bot7` folder from the repo; don't edit it |
| `Missing package` | Do step 3 |
| Many `not_filled` | Others are taking the cheap prices first. That's real competition; compare with bot 7R's paper results. |
| HTTP 429 | Too many requests. The bot sends very few, so check nothing else is using your key. |

No trades for about 40 minutes after each start is normal. Bot 7 first learns the small price difference between Coinbase and Polymarket.

Polymarket's official API documentation is at docs.polymarket.us.
