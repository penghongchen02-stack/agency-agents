# Polymarket BTC Up/Down Bot: our own, transparent version

A small TypeScript bot for Polymarket's **"Bitcoin Up or Down"** 5- and 15-minute markets.
It's a clean rewrite inspired by a GitHub repo that turned out to be a
wallet-key stealer. This version keeps the legitimate idea and drops everything else.

> ⚠️ **No promised edge.** Short-horizon BTC direction is close to a coin flip, and
> these markets are competitive. Expect the bot to trade rarely and to lose money
> unless your own testing shows otherwise. It starts in **paper mode**, and you
> should leave it there until `npm run report` says the model beats the market.

## What we dropped from the original (the "weird part")

| Original repo | This version |
|---|---|
| Closed-source `.exe` that asked for your private key and **sent it to a Telegram bot** | No binaries. Every line is TypeScript you can read |
| Dependencies `twapfetch` / `fetchrtds` (one taken down by npm, one unpublished) | Only official `@polymarket/*` packages plus `viem`, with exact versions and a committed lockfile |
| "Private calibrated signal, 61% win rate" | The model is ~10 lines in [`src/model.ts`](src/model.ts) with no claims attached |
| 2-day trial, "contact me on Telegram" | MIT-licensed example code, like the rest of this repo. No licence server, no phoning home |
| Scratch exits that made the "win rate" look better | Scratches are optional, and the report counts their P&L separately so they can't hide losses |
| Winner-lock: blindly buying the 90–96¢ favourite | Only buys if our own model also says the favourite is underpriced |

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

## Run it

Requires Node.js ≥ 20.12.

```bash
cd examples/polymarket-btc-bot
npm ci --ignore-scripts      # exact versions from the lockfile, no install scripts
cp .env.example .env         # defaults to paper mode
npm test                     # unit + engine tests
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

### Going live (only if paper results justify it)
1. Use a **brand-new, dedicated wallet** holding only what you can afford to lose.
2. Fill `PRIVATE_KEY`, `FUNDER_ADDRESS` and `SIGNATURE_TYPE` in `.env`, then set
   `MODE=live` and `LIVE_CONFIRM=I accept the risk of losing this money`.
3. Start with `STAKE_USD=1` to `5`.
4. Winning shares show up as redeemable positions on Polymarket. Redeem them there.
   The bot doesn't move funds on-chain.

Check that automated trading on Polymarket is allowed where you live before going live.

## Files

| File | Role |
|---|---|
| `src/config.ts` | Validated settings and live-mode gate |
| `src/priceFeed.ts` | Chainlink BTC/USD via the official RTDS client, open price, TWAP and volatility |
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
- The feed is Polymarket's Chainlink stream. If it lags the settlement oracle, the open price can be slightly off.
- Not financial advice.

## Agency agents behind this
Built with the approach of [Senior Developer](../../engineering/engineering-senior-developer.md),
[Secrets & Credential Hygiene Engineer](../../security/security-secrets-credential-engineer.md),
[Blockchain Security Auditor](../../security/security-blockchain-security-auditor.md) and
[Reality Checker](../../testing/testing-reality-checker.md) (no claims without evidence: hence paper mode and the Brier score).
