# Bot 7Q guide (maker bot)

Bot 7Q **posts its own buy prices early and waits for others to sell to it.** In live mode it places **real orders with real money** on Polymarket US.

> **Important**
> - This is an experiment. Nobody knows yet whether it makes money. That is what the tiny live test is for.
> - Only use it if Polymarket US is legally available to you and your account is verified.
> - Run it **only on your own computer**. Never paste your API keys into a chat, an AI session or a file in this folder.
> - Keep the tiny default limits: **$2 per order, $50 spent per day, $10 daily loss limit.**

---

## How it works

1. Every second it reads the live Coinbase price for BTC, ETH, SOL and XRP. Bot 7's own math (unchanged) estimates the chance of **Up** in each Polymarket Up/Down market.
2. From **90 to 8 seconds before a market ends**, it keeps two orders waiting on the book. Example with an estimated 80% chance of Up:
   - **buy Up at 74¢** (6¢ under 80%)
   - **buy Down at 14¢** (6¢ under 20%)
3. If someone sells to it at those prices, it's filled at a good price. Then it cancels the other side and stops trading that market.
4. When its estimate moves by **2¢** or more, it cancels and re-posts. It re-posts at most every 3 seconds, unless the estimate jumps 4¢ or more.
5. It skips markets that are nearly decided (below 8% or above 92%).

**Protection for every order:**
- **Post-only.** If an order would buy someone else's price right away, Polymarket rejects it. The bot only ever waits for sellers, so it gets the maker rebate and never pays the taker fee.
- **It ends on its own.** Every order carries a time limit 5 seconds before the market ends. The bot also cancels everything itself at 8 seconds left.
- **Cleanup.** It cancels all its open orders when it starts, when you press **Ctrl-C**, and whenever a limit or the `STOP` file pauses it.

## The main risk

**You tend to get filled when you're wrong.** Traders who see a price move first sell to you just before your price becomes bad. The 6¢ margin and the fast re-posting are meant to cover this. The live test shows whether they do. Expect some losing fills.

---

## Step by step

You need what bot 7 LIVE needed: a verified Polymarket US account, an API key, Python 3, and the `cryptography` package. The `bot7`, `bot7live` and `bot7q` folders must sit **side by side**. Bot 7Q uses bot 7's math and bot 7 LIVE's sign-in code.

1. **Keys:** the same file as bot 7 LIVE, `~/.bot7live/keys.json` (chmod 600). Nothing new is needed.
2. **Check bot 7 is intact:** `cd bot7 && ./verify.sh` must print OK.
3. **Offline tests:** `cd bot7q && python3 -I test_bot7q.py` must end with `ALL PASSED`. These use a fake server; no real orders are placed.
4. **Dry run first (no orders):**
   ```
   cp config.example.json config.json
   caffeinate -i -s ./run_maker.sh
   ```
   It prints the prices it would post. Every planned order goes to `maker_events.jsonl` as `quote_dry`. Run it for a few market cycles, then stop with Ctrl-C.
5. **Tiny live test:** in `config.json` set `"mode": "live"` and keep the limits small. Start it the same way. Check that orders appear in your Polymarket app as open orders, and that they disappear by themselves when the market ends.
6. **Results:**
   ```
   python3 -I maker_report.py
   ```
   This shows real fills, wins, money spent and profit per day, from Polymarket's official results. Maker rebates are paid separately by Polymarket and aren't included.
7. **Stop:** Ctrl-C (it cancels its open orders first). Or `touch STOP` to pause, which also cancels open orders.

## What to look for after a few days
- **How many orders get filled?** If almost none, the margin is too big or others offer better prices.
- **Do filled orders win more often than their price says?** For example, Up bought at 74¢ should win more than 74% of the time. If they win **less**, you're being picked off, and the idea doesn't work.
- **Profit after rebates.**

Only consider bigger sizes if several days of real fills are clearly profitable.

## Settings (`config.json`)

| Setting | Default | Meaning |
|---|---|---|
| `mode` | `dry_run` | `dry_run` = plan only. `live` = real orders. |
| `usd_per_order` | 2 | Money per order |
| `margin` | 0.06 | How far under its estimate it bids (6¢) |
| `requote` | 0.02 | Re-post when its estimate moves this much |
| `min_requote_s` | 3 | Re-post at most every 3 s, unless the estimate moves twice `requote` |
| `quote_start_s` / `quote_end_s` | 90 / 8 | Quote between these many seconds before the end |
| `expire_before_end_s` | 5 | Orders end by themselves this long before the market ends |
| `fair_min` / `fair_max` | 0.08 / 0.92 | Skip nearly decided markets |
| `max_open_orders` | 16 | At most this many orders waiting at once |
| `max_new_orders_per_s` | 4 | Keeps requests far below Polymarket's 25 per second |
| `daily_max_spend_usd` | 50 | Pause new orders after spending this much in a UTC day |
| `daily_max_loss_usd` | 10 | Pause when today's settled losses reach this |

## Files
| File | What it is |
|---|---|
| `bot7q.py` | The maker bot |
| `run_maker.sh` | Keeps it running |
| `config.example.json` | Settings template |
| `test_bot7q.py` | Offline tests against a fake server |
| `maker_report.py` | Real results per day |
| `maker_events.jsonl` | Every planned, posted, cancelled or rejected order |
| `maker_fills.jsonl` | Every real fill |

## Things the first live run will confirm
These follow Polymarket's docs but couldn't be tested without your key:
- **The order time-limit format.** If Polymarket rejects it, you'll see `post_rejected` in `maker_events.jsonl`. Send me those lines; they contain no keys.
- **How Down orders are priced.** They're sent as "buy NO at YES price". Check one Down order in your app shows the expected price, for example 14¢.
