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
