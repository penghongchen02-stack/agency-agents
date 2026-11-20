# Polymarket US Connectivity Check (read-only)

This is a pre-flight tool for a future Polymarket US crypto bot. It checks that **every connection a bot would need actually works**: public market data, the settlement index feed, the authenticated trading API, and both websocket streams. **It contains no strategy and cannot place, modify, or cancel orders.** A guard in `pmus_connect/safety.py` blocks every trading endpoint, and the tests enforce it.

Endpoints, signing, and message formats come from the official docs at [docs.polymarket.us](https://docs.polymarket.us) and the official `polymarket-us` SDK (v2.4.1).

## What gets checked

| # | Check | Endpoint | Needs key |
|---|---|---|---|
| 1 | Public gateway reachable | `GET gateway.polymarket.us/v1/markets` | No |
| 2 | Clock skew against the server (signatures fail beyond ±30 s) | `Date` header | No |
| 3 | Crypto market discovery: picks a live Up/Down window | `GET /v1/markets?categories=crypto` | No |
| 4 | Best bid/offer for that market | `GET /v1/markets/{slug}/bbo` | No |
| 5 | Full order book | `GET /v1/markets/{slug}/book` | No |
| 6 | Settlement index feed (CF Benchmarks **BRTI**) freshness | `GET /v1/asset-prices/history` | No |
| 7 | Trading host reachable (an unsigned request should get 401) | `api.polymarket.us` | No |
| 8 | Markets websocket reachable (an unsigned handshake should get 401) | `wss://api.polymarket.us/v1/ws/markets` | No |
| 9 | API key format (Ed25519 secret decodes) | n/a | Yes |
| 10 | Account balances | `GET /v1/account/balances` | Yes |
| 11 | Positions | `GET /v1/portfolio/positions` | Yes |
| 12 | Open orders | `GET /v1/orders/open` | Yes |
| 13 | Markets websocket stream: subscribe and get the first update | `/v1/ws/markets`, `MARKET_DATA_LITE` | Yes |
| 14 | Private websocket stream: subscribe and get a balance snapshot | `/v1/ws/private`, `ACCOUNT_BALANCE` | Yes |
| 15 | *Optional* `--preview-order`: validates a 1-contract $0.01 maker order **without submitting it** | `POST /v1/order/preview` | Yes |

## Setup

```bash
cd examples/crypto-bot-research/polymarket-us-connect
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pmus_connect            # public checks only
```

To run the authenticated checks:

1. Get a Polymarket US account approved (app plus identity verification).
2. Create a key at [polymarket.us/developer](https://polymarket.us/developer). The secret is shown **once**.
3. `cp .env.example .env` and fill in `POLYMARKET_KEY_ID` and `POLYMARKET_SECRET_KEY`. `.env` is git-ignored. Environment variables also work.
4. Run `python -m pmus_connect`, and add `--preview-order` to also validate an order without sending it.

Options:
- `--asset btc|eth|sol|xrp`
- `--horizon 5m|15m|1h|1d` (preferred Up/Down window)
- `--market <slug>` (probe a specific market)
- `--ws-wait 10`
- `--json` (CI-friendly output)

The exit code is `1` if any check fails.

Offline tests (signing and the read-only guard):

```bash
pip install -r requirements-dev.txt && python -m pytest -q tests
```

## Example run (no key, live production, 2026-11-20)

```
✅ Public gateway reachable [318 ms]
✅ Clock skew vs server: +0.5 s
✅ Crypto market discovery [331 ms]
     1101 live crypto markets. Probing cpc-btc-updown-15m-2026-11-20-1200z (15m window, priceToBeat=61750.81)
✅ Market BBO [43 ms]          state=MARKET_STATE_OPEN bid=None ask=0.0200 depth=0/97
✅ Market order book [42 ms]   0 bid levels, 97 offer levels
✅ Settlement index feed [758 ms]  crypto:btc close=61381.10 (candle age 16 s)
✅ Trading API host reachable  unsigned request -> HTTP 401 (expected)
✅ Markets websocket reachable unsigned handshake -> 401 (expected 401)
⏭️  Authenticated checks       set POLYMARKET_KEY_ID and POLYMARKET_SECRET_KEY to run them
```

With a dummy key the server answers `401 API key not found`. That confirms the signed headers are well-formed and only a real key is missing.

## Data recorder (`pmus_recorder`)

Records the data the [recommended late-window strategy](../README.md) needs to test itself. It never trades.

| Data | Source | Live? | Cadence |
|---|---|---|---|
| Up/Down windows (slug, window, `priceToBeat`) | `GET /v1/markets?categories=crypto` plus `/v1/market/slug/{slug}` | List is cached 30 s; per-market detail is live | Every 30 s |
| **Order book (top 10 levels) and trades** | `wss://api.polymarket.us/v1/ws/markets` (**API key**) | **Live** | Every update |
| Order book fallback | `GET /v1/markets/{slug}/book` | **No: CDN `max-age=30`** | 1–10 s |
| Settlement index (BRTI), 1-second candles | `GET /v1/asset-prices/history` | Live | Every 10 s, gaps backfilled |
| Settlement (index close plus contract payout) | `/v1/market/slug/{slug}`, `/v1/markets/{slug}/settlement` | Live | After close |

```bash
python -m pmus_recorder record                                 # BTC 15m + 1h, until Ctrl-C
python -m pmus_recorder record --assets btc,eth --horizons 5m,15m,1h --duration 86400
python -m pmus_recorder report                                 # coverage + late-window table
```

With `POLYMARKET_KEY_ID` and `POLYMARKET_SECRET_KEY` set, the recorder streams live books and trades over the websocket. It reconnects with backoff and keeps the REST book as a slow cross-check. Without a key it records cached REST books only, and the report labels that data unusable for late-window analysis.

Data goes to `data/pmus.sqlite` (git-ignored). Restarting resumes unsettled markets. Run it on a server with `nohup` or as a systemd service for 1–2 weeks.

The **report** shows:
- **Coverage:** markets, live versus cached snapshots, ticks, trades, errors, and latency.
- **Settlement reproduction:** the official close compared with the recorded 60-second index average.
- **Late-window leader study:** for each 30-second bucket before close:
  - how often the side leading on the projected 60-second average won
  - how often it could be bought at $0.98 or less
  - the average price
  - a naive EV per contract after the taker fee, assuming perfect fills, so it is an upper bound

### No-key historical study: `backfill` + `study`

Polymarket US keeps resolved markets, plus the exchange's **stored display prices** (`/v1/price-history`, about one point per minute; `longPrice` is the Up price from the best ask, `shortPrice` is the Down price from 1 minus the best bid), and the settlement index history. With that you can test the late-window strategy on **past** markets right away, with no key and no waiting:

```bash
python -m pmus_recorder backfill --days 45            # BTC 15m + 1h, about 5,400 markets, about 25 min at 12 req/s
python -m pmus_recorder study                          # availability, calibration, walk-forward test
```

`study` makes every decision using only data available at about T-180, T-120, or T-60 seconds, at the moment a price was really seen:
- **Projected close:** the elapsed part of the 60-second settlement average, with the latest price filling the rest.
- **Leader** and its displayed price.
- **P&L** after the Tier 1 taker fee.

It reports:
- how often there is anything to buy at all
- **calibration**: whether a leader priced at X actually wins more often than X
- a **walk-forward test**: parameters are chosen on the first 2/3 of the dates and reported on the last 1/3

A $0.99 display price is treated as **unbuyable**, because live books showed a $0.99 bid with no offer behind it.

Limits:
- Display prices carry **no size**, so fill size and slippage are unknown.
- There is about one point per minute.
- Index reconstruction is approximate.

Treat a positive result as a reason to test with live books and tiny size, not as proof of profit.

**Price timestamps run about 90 s early.** A lead-lag test against the settlement index shows that a `/v1/price-history` point reflects the market about 90 s after its timestamp. The tools therefore treat each point as known at `timestamp + --price-delay` (default 90) and decide at that moment.

**Results:** see [RESULTS-2026-11-20-all-strategies.md](RESULTS-2026-11-20-all-strategies.md), covering 45,932 markets, 4 coins, 3 window lengths and 7 strategy families.
- **Losers:** both-sides, NeverSmiling-style, long-shot and momentum lose after fees under every timing assumption.
- **Unproven:** the late-window index-leader bot looks positive, but only by about as much as the timing uncertainty, so it needs live websocket data to confirm or reject.

The first BTC-only run ([RESULTS-2026-11-20.md](RESULTS-2026-11-20.md)) used raw timestamps and is superseded.

```bash
python -m pmus_recorder compare                      # all 7 families, walk-forward, per coin/window
python -m pmus_recorder compare --price-delay 75     # check how much the result depends on timing
```

### Live paper trading: `paper` + `paper-report` (no key, no orders)

This runs all seven strategy bots forward on live data. **Each bot trades all four coins together** (BTC, ETH, SOL and XRP), which makes 28 bot-coin pairs. For each coin, a bot uses the window length and settings where it did best on that coin in the 45-day test. The rules are the same as in the backtest, so live results show whether the backtest holds.

| Bot | BTC | ETH | SOL | XRP | Backtest EV per contract (avg of 4 coins) |
|---|---|---|---|---|---|
| model_edge | 5m | 5m | 5m | 5m | +3.8¢ |
| favourite | 5m | 5m | 1h | 1h | +3.9¢ |
| disagreement | 5m | 5m | 5m | 5m | +15.6¢ (suspect: stale quotes) |
| momentum | 1h | 15m | 15m | 1h | −7.7¢ |
| longshot | 1h | 1h | 1h | 15m | −1.0¢ |
| both_sides | 1h | 1h | 1h | 1h | −3.1¢ |
| neversmiling | 1h | 1h | 1h | 1h | −9.7¢ |

`paper-report` shows each bot with all coins combined, then each coin separately.

```bash
nohup python -m pmus_recorder paper > paper.log 2>&1 &      # runs until stopped; resumes after restart
python -m pmus_recorder paper-report                         # per-bot results vs the backtest
```

**Where the live prices come from:**
- **Quotes:** `GET /v1/market/slug/{slug}`. Its `bestBidQuote` and `bestAskQuote` update every 1–2 s, unlike the CDN-cached `/book` and `/bbo`. In a check, the quote changed 50 times in 80 s; the cached BBO changed 3 times.
- **Settlement index:** published about 2 s behind real time.

**What gets recorded:** every buy, the live index lag at each decision, and every settlement, all in `data/paper.sqlite`. Fills are assumed at the quoted price with unknown size, so treat the results as an upper bound.

**How long to run it:** about 2 weeks on an always-on machine. That gives roughly 4,000 decisions per 5-minute bot, and 300 per 1-hour bot.

### What the first live test run found (2026-11-20, 25 min, BTC + ETH, 5m/15m/1h)

- **The public order book is cached up to 30 s.** It returned `cache-control: public, max-age=30` with the `Age` header counting up, and recorded snapshots were on average 14 s old (max 29 s). A last-two-minutes strategy **needs the authenticated websocket**.
- **The public 1-second index candles reproduce closes only approximately.** BTC was off by up to about $19 (around 0.03%), and ETH by less than $0.70. Shifting the alignment does not fix it, so the candles aggregate a faster feed. Treat closes within that distance of `priceToBeat` as coin-flips.
- **When the outcome is obvious, there is nothing to buy.** On 15m/1h windows where BTC was 0.5–0.7% above the open, the book showed a $0.99 bid and **no offers at all**. Any edge has to come from closer races.
- **Settlement is fast.** Markets resolved about 1 minute after close. The contract-settlement endpoint can lag the index close, which the recorder handles.
- 0 errors. API latency was about 41 ms from this host.

## Polymarket US facts that matter for any future bot

These differ from the international Polymarket that the [research](../README.md) studied:

- **Regulated US exchange (CFTC), with KYC.** The API is available only to approved accounts. Check your eligibility.
- **Settlement is CF Benchmarks BRTI**, a 60-second average before the settlement instant. It is not Chainlink, and it is not exchange spot. Model that basis.
- **Crypto families:**
  - Up/Down (15m and 1h listed; 5m, 1d, and 4h also appear)
  - Above/Below ladders
  - Price Range
  - One-Touch

  Identify markets with `assetPriceTerms`. Never parse the slug.
- **Auth:** Ed25519 signature over `timestamp + METHOD + path`, with the query string excluded, in the `X-PM-Access-Key`, `X-PM-Timestamp`, and `X-PM-Signature` headers. Timestamps must be within 30 s.
- **Rate limit:** 25 req/s per IP. Use the websockets instead of polling.
- **A 5-second latency stopgap** rejects stale orders with `Order Processing Max Delay Exceeded`. That is a transient reject, not a rate limit.
- **Fees, rebates, and incentive programs** have their own endpoints (`/fees`, the Incentives API). The research shows they can dominate P&L, so read them before designing a strategy.

> Connectivity only. Not financial advice. Nothing in this folder trades.
