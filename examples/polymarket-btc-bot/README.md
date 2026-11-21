# Polymarket BTC 5-Minute Bot: our own, transparent version

A small TypeScript bot for Polymarket's **"Bitcoin Up or Down – 5 minute"** markets.
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
| Scratch trading at breakeven to inflate the win rate | Every position is held to resolution and scored honestly |

## How it works

```
Chainlink BTC/USD (Polymarket RTDS) ──► PriceTape ──► fair value P(up)
Gamma API ──► current btc-updown-5m-<ts> market            │
CLOB order books (Up & Down asks) ─────────────────────────┤
                                                           ▼
                        decide(): buy only if P − ask − fees ≥ MIN_EDGE
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
- Hard limits on stake, trades per slot, trades per day and daily loss. Open positions count as already lost.
- Create a file named `STOP` in this folder to halt new entries at once.
- Orders are Fill-And-Kill with a price cap: no resting orders, no paying above the priced ask.
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
npm run report               # win rate, P&L, and Brier score: model vs market
```

**Reading the report.** The *Brier score* measures how well-calibrated probabilities are
(lower is better). If `Brier model` is not clearly below `Brier market` after a few
hundred settled trades, there's no edge. Tweak the parameters or stop.

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
| `src/priceFeed.ts` | Chainlink BTC/USD via the official RTDS client, open price and volatility |
| `src/markets.ts` | Slot math, plus Gamma market lookup and resolution |
| `src/model.ts` | Fair-value model and trade decision (pure functions) |
| `src/risk.ts` | Hard limits and the STOP switch |
| `src/broker.ts` | Paper fills and live FAK orders via `@polymarket/clob-client-v2` |
| `src/engine.ts` | Decision loop, settlement and restart recovery |
| `src/report.ts` | Scorecard from the ledger |

## Known limitations
- `npm audit` reports low-severity advisories in `ethers` v5 and `elliptic`, which
  Polymarket's official SDK depends on. No upstream fix exists yet. `ws` is pinned to a patched version.
- Paper fills assume you get the displayed best ask (up to its size). Real fills can be worse.
- The feed is Polymarket's Chainlink stream. If it lags the settlement oracle, the open price can be slightly off.
- Not financial advice.

## Agency agents behind this
Built with the approach of [Senior Developer](../../engineering/engineering-senior-developer.md),
[Secrets & Credential Hygiene Engineer](../../security/security-secrets-credential-engineer.md),
[Blockchain Security Auditor](../../security/security-blockchain-security-auditor.md) and
[Reality Checker](../../testing/testing-reality-checker.md) (no claims without evidence: hence paper mode and the Brier score).
