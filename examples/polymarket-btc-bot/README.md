# Polymarket BTC Up/Down Bot: our own, transparent version

A small TypeScript bot for **"BTC Up or Down"** 5- and 15-minute markets on
**[Polymarket US](https://polymarket.us)** (the CFTC-regulated US exchange; the default),
or on the global polymarket.com.
It's a clean rewrite inspired by a GitHub repo that turned out to be a
wallet-key stealer. This version keeps the legitimate idea and drops everything else.

> ⚠️ **No promised edge.** Short-horizon BTC direction is close to a coin flip, and
> these markets are competitive. Expect the bot to trade rarely and to lose money
> unless your own testing shows otherwise. It starts in **paper mode**, and you
> should leave it there until `npm run report` says the model beats the market.
>
> **Our own 1000-market backtest on Polymarket US says it doesn't (yet).** See
> [Backtest results](#backtest-1000-real-polymarket-us-markets).

## What we dropped from the original (the "weird part")

| Original repo | This version |
|---|---|
| Closed-source `.exe` that asked for your private key and **sent it to a Telegram bot** | No binaries. Every line is TypeScript you can read |
| Dependencies `twapfetch` / `fetchrtds` (one taken down by npm, one unpublished) | Only Polymarket's official SDKs (`polymarket-us`, `@polymarket/*`) plus `viem`, with exact versions and a committed lockfile |
| "Private calibrated signal, 61% win rate" | The model is ~10 lines in [`src/model.ts`](src/model.ts) with no claims attached |
| 2-day trial, "contact me on Telegram" | MIT-licensed example code, like the rest of this repo. No licence server, no phoning home |
| Scratch exits that made the "win rate" look better | Scratches are optional, and the report counts their P&L separately so they can't hide losses |
| Winner-lock: blindly buying the 90–96¢ favourite | Only buys if our own model also says the favourite is underpriced |

## Polymarket US

`VENUE=us` (the default) trades Polymarket US. These facts were checked against the
official docs (docs.polymarket.us) **and** against live responses:

| | Polymarket US |
|---|---|
| Markets | `cpc-btc-updown-5m-YYYY-MM-DD-HHMMz` (and `-15m-`), with the window start in UTC |
| Shape | One instrument per market: **YES = Up** (long), **NO = Down** (short). The order book is the YES book, and NO = 1 − YES |
| Order price | Always the **YES** price. Buying Down at 0.33 is sent as `BUY_SHORT` at 0.67 |
| Settles on | CF Benchmarks **BRTI**, as the 60-second average before the open (`priceToBeat`) and before the close |
| Price feed | Public BRTI from `gateway.polymarket.us/v1/asset-prices/history`. **Measured:** the "1-second" series is already that 60s average (each value has `tickCount: 60`, and the value at T−1s equals `priceToBeat` exactly), so it lags the real price by about 30s. The model corrects for this (see `src/model.ts`) |
| Fees | API taker fee `0.0695 × contracts × p × (1 − p)`, modelled on every fill. The current 70% API rebate is ignored, which is conservative |
| Orders | Official `polymarket-us` SDK, Ed25519-signed locally. IOC limit orders flagged `MANUAL_ORDER_INDICATOR_AUTOMATIC` (required for API orders). Every order is **previewed first** and refused if the exchange's reading differs from ours |
| Eligibility | US residents with a verified Polymarket US account. API keys come from polymarket.us/developer |
| Limits | 25 requests/s per IP. The bot uses about 1.5/s |

## Backtest: 1000 real Polymarket US markets

```bash
npm run backtest -- --slots 1000 --bankroll 1000
```

This replays real history through the **real engine, strategies, risk limits, fees and
ledger**: each market's official open, settlement and winner, the 1-second BRTI feed, and
the market's own displayed prices (about one point a minute). Historical order books
aren't published, so the book is the displayed price ±1¢. The bot sees the feed 2s late,
and can only act at the minutes where the market price is known. Price-history points are
stamped at the start of their minute but show its end. We measured this and use the
corrected times: without the fix, the market "sees" up to 60s into the future.

**Result: 1000 markets, 2026-11-17 22:40 → 2026-11-21 12:00 UTC, $5 stake, $1000 paper bankroll**

| Strategy | Buys | Held to close | Wins | Scratches | Staked | P&L | ROI | Max drawdown |
|---|---|---|---|---|---|---|---|---|
| fair-value | 99 | 99 | 35 | 0 | $494.81 | **−$44.33** | −9.0% | $78.28 |
| twap-scratch | 54 | 5 | 3 | 49 | $269.91 | **−$33.07** | −12.3% | $36.60 |
| winner-lock | 0 | – | – | – | – | – | – | – |

Forecast quality on 3,996 decision points (Brier score, lower is better):
**model 0.1348 vs market 0.1243**. The market's own prices were the better forecast.

Robustness checks on the same data:
- No spread and no feed delay (best case): fair-value **−2.4%**, twap-scratch **−8.6%**.
- `MIN_EDGE=0.10`: fair-value −4.9%, twap-scratch −10.9%.
- winner-lock never fired. Late in the window, the market already prices the favourite
  at or above what our model thinks it's worth.

**What this means:** the strategies run correctly end to end, but on this data the
Polymarket US book prices BTC 5-minute windows better than this model. Every edge the
bot "found" was mostly the market knowing something the model didn't. Don't go live on
these settings. Improve the model and re-run the backtest until the model's Brier score
beats the market's, then paper trade live.

## Strategies (what we kept from the original)

Pick one with `STRATEGY=` in `.env`. All three share the same model, risk limits, paper
mode and ledger. The engine executes, and a strategy can only *suggest* an action.

| `STRATEGY` | Where it comes from | What it does |
|---|---|---|
| `fair-value` (default) | Ours | Once per slot, buys the side whose ask is below fair value by `MIN_EDGE` after fees |
| `twap-scratch` | The original **README** | Model input is a 30s TWAP of the Chainlink price. Buys only in the **45–55¢** band, in `STAKE_USD` clips up to `MAX_SLOT_USD`, during seconds **5–150**. Re-scores every **15s**. **Scratch-sells** at the bid if our probability drops below 50% or the bid exceeds our fair value. No re-entry after a scratch, and never holds both sides |
| `winner-lock` | The original **`.exe`** (found in its bundled code) | In the **last 60s**, buys the favourite at **90–96¢**, but only if our model's probability ≥ ask + `WL_FEE_BUFFER` + `WL_MIN_EDGE` |

Set `MARKET_WINDOW=15m` to trade the 15-minute markets instead (the `.exe` ran both).

**Know the risk of each.** *twap-scratch* pays the spread twice on every scratch
(about 1¢/share), and that cost adds up. *winner-lock* risks ~92¢ to make ~8¢. One late
reversal wipes out ~11 wins, so it looks great right up until it doesn't. The original's
"30-second TWAP settlement" claim is unverified. Here, TWAP is just a noise filter.

What we did **not** keep: CEX lead-lag feeds (Binance is geo-blocked in many places,
and the claim was unproven), and anything tied to the original's Telegram, trial
licence or binary.

## How it works

```
Chainlink BTC/USD (Polymarket RTDS) ──► PriceTape ──► fair value P(up)
Gamma API ──► current btc-updown-5m-<ts> market            │
CLOB order books (Up & Down, bids & asks) ─────────────────┤
                                                           ▼
              strategy.act(): buy a clip / scratch-sell / nothing
                                                           ▼
                        RiskManager hard limits ──► Paper or Live broker
                                                           ▼
                        state/ledger.jsonl ──► settle on Polymarket's resolution
```

**The model** ([`src/model.ts`](src/model.ts)). A slot resolves *Up* if BTC at the end
is ≥ BTC at the open. Treat price as a random walk with realized volatility σ. With a
move `d` since the open and `τ` seconds left:

```
P(up) = Φ( d / (σ·√τ) )
```

This is a *fair value*. The bot buys a side only when its ask is below that value by
`MIN_EDGE` after a `FEE_BUFFER`. If the market already prices this in, the bot does
nothing, and that's the right outcome.

**Safety rails**
- `MODE=paper` by default. Live mode needs `MODE=live` **and** the exact `LIVE_CONFIRM` phrase.
- In paper mode the private key is never even read.
- In live mode the key only signs orders locally (viem). Logs and the ledger redact anything key-shaped.
- Hard limits on clip size, trades and USD per slot, trades per day and daily loss. Open positions count as already lost.
- One side per slot. No hedging both outcomes, no martingale, no averaging into a loser.
- Create a file named `STOP` in this folder to halt new entries at once.
- Orders are Fill-And-Kill with a price limit: no resting orders, no buying above the priced ask, no selling below the priced bid.
- The bot skips a slot when the feed is stale or when it can't trust the open price (for example, it joined mid-slot).
- A restart restores open positions and today's risk counters from the ledger.

## Security audit (what to check, and what we checked)

You shouldn't trust this bot on our word, any more than the original. Here's what was checked, and how to re-check it:

| Check | Result | Re-check yourself |
|---|---|---|
| Network destinations in our code | Only `clob.polymarket.com`, `gamma-api.polymarket.com`, `gateway.polymarket.us` (plus `api.polymarket.us` and `ws-live-data.polymarket.com` inside Polymarket's SDKs) | `grep -rnoE "(https?\|wss?)://[a-zA-Z0-9.-]+" src node_modules/polymarket-us/dist node_modules/@polymarket/*/dist` |
| Host overrides (`CLOB_HOST`, ...) | Must be https on a Polymarket domain, so a planted `.env` can't redirect orders | `test/core.test.ts`: "host overrides…" |
| Where your key goes | Only read in live mode, only used to sign locally. The global signer's transport refuses every network call. Logs, ledger and the startup print redact keys | `grep -rn "privateKey\|usSecretKey" src` |
| Dynamic code, shell, obfuscation | No `eval`, `Function`, `child_process`, dynamic `import()`, hidden Unicode, or encoded blobs | `grep -rnE "eval\(\|child_process\|new Function" src` |
| Files written | Only `state/` (ledger, backtest cache). The backtest deletes only its own per-strategy folders | `grep -rn "writeFile\|rmSync\|appendFile" src` |
| Dependencies | 118 packages, all from registry.npmjs.org with integrity hashes. `polymarket-us` is the SDK Polymarket's docs name, and the rest are Polymarket's own or well-known. The only install scripts are esbuild (dev) and fsevents (macOS); install with `--ignore-scripts` | `npm ci --ignore-scripts && npm audit` |
| Binaries / original repo leftovers | None in the tree or the git history | `git log --all --name-only \| grep -iE "\.exe\|\.dll"` |

## Run it

Requires Node.js ≥ 20.12.

```bash
cd examples/polymarket-btc-bot
npm ci --ignore-scripts      # exact versions from the lockfile, no install scripts
cp .env.example .env         # paper mode on Polymarket US by default
npm test                     # unit + engine tests
npm run backtest             # 1000 real Polymarket US markets (downloads once, then cached)
npm start                    # paper-trade against live markets
npm run report               # per strategy: P&L, scratches, Brier score vs market
```

**Reading the report.** The *Brier score* measures how well-calibrated probabilities are
(lower is better). If `Brier model` is not clearly below `Brier market` after a few
hundred settled trades, there's no edge. Tweak the parameters or stop. To compare
strategies fairly, give each its own `STATE_DIR` and paper-trade them side by side:

```bash
STRATEGY=fair-value   STATE_DIR=state/fv npm start
STRATEGY=twap-scratch STATE_DIR=state/ts MAX_TRADES_PER_SLOT=3 npm start
STRATEGY=winner-lock  STATE_DIR=state/wl npm start
STATE_DIR=state/ts npm run report
```

### Going live (only if backtest *and* paper results justify it)
**Polymarket US** (`VENUE=us`):
1. Create an API key at polymarket.us/developer. Keep only what you can afford to lose in the account.
2. Set `US_KEY_ID` and `US_SECRET_KEY` in `.env`, then `MODE=live` and
   `LIVE_CONFIRM=I accept the risk of losing this money`.
3. Start with `STAKE_USD=1` to `5`. Settled positions return to your cash balance automatically.
4. Check your first fills in the Polymarket US app. The order preview guards the price
   convention, but verify it yourself.

**Global** (`VENUE=global`, not for US persons): use a dedicated wallet, and set
`PRIVATE_KEY`, `FUNDER_ADDRESS` and `SIGNATURE_TYPE`. Redeem winnings on Polymarket.

## Files

| File | Role |
|---|---|
| `src/config.ts` | Validated settings, venue choice, live-mode gate |
| `src/venue.ts` | Venue interface, plus the global (Gamma + CLOB) implementation |
| `src/usVenue.ts` | Polymarket US public data: markets, YES book → Up/Down quotes, BRTI, price history |
| `src/usBroker.ts` | Polymarket US live orders via the official SDK, preview-checked |
| `src/backtest.ts` | Real-data replay through the real engine |
| `src/priceFeed.ts` | Price tape, BRTI poller (US), Chainlink RTDS stream (global) |
| `src/markets.ts` | Slot math, plus Gamma market lookup and resolution |
| `src/model.ts` | Fair-value model and trade decision (pure functions) |
| `src/strategies.ts` | `fair-value`, `twap-scratch`, `winner-lock` |
| `src/risk.ts` | Hard limits and the STOP switch |
| `src/broker.ts` | Paper fills and live FAK orders via `@polymarket/clob-client-v2` |
| `src/engine.ts` | Decision loop, execution, settlement and restart recovery |
| `src/log.ts` | Redacting logger, ledger, and ledger replay |
| `src/report.ts` | Scorecard from the ledger |

## Known limitations
- `npm audit` reports low-severity advisories in `ethers` v5 and `elliptic`, which
  Polymarket's official SDK depends on. No upstream fix exists yet. `ws` is pinned to a patched version.
- Paper fills assume you get the displayed best ask or bid (up to its size). Real fills can be worse, especially for scratches.
- Live order responses are trusted for fill sizes. Check your first live trades against the Polymarket UI.
- The US live broker has not placed a real order: that needs your verified account and
  keys. Its pieces (pricing, order building, fill parsing) are unit-tested, and the
  preview check refuses any order the exchange reads differently.
- The backtest can only act once a minute and uses a synthetic ±1¢ book.
- The feed is Polymarket's Chainlink stream. If it lags the settlement oracle, the open price can be slightly off.
- Not financial advice.

## Agency agents behind this
Built with the approach of [Senior Developer](../../engineering/engineering-senior-developer.md),
[Secrets & Credential Hygiene Engineer](../../security/security-secrets-credential-engineer.md),
[Blockchain Security Auditor](../../security/security-blockchain-security-auditor.md) and
[Reality Checker](../../testing/testing-reality-checker.md) (no claims without evidence: hence paper mode and the Brier score).
