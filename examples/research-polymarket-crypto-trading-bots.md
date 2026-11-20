# Research: Every Crypto-Trading Bot in the PR&R Trader Reports

**Source:** [Poly Research & Robotics — Trader Reports](https://www.polyresearchrobotics.com/reports) (38 reports, read in full, November 2026).
**Scope:** The 21 reports that cover a wallet trading **crypto** markets on Polymarket. The other 17 reports cover sports, esports, weather, soccer, or tennis, and are listed at the end for completeness.
**Method:** Each report is an on-chain reconstruction of one Polymarket wallet. The figures below are what the reports state. Where a report marks something as an inference, or contradicts itself, it is flagged here as well. None of this is investment advice, and past wallet P&L tells you nothing certain about future results.

> **Agents built from this research** (see the [Finance division](../finance/)):
> - 🔬 [Prediction Market Wallet Forensics Analyst](../finance/finance-prediction-market-wallet-forensics-analyst.md): reverse-engineers any wallet the way these reports do.
> - ⚖️ [Crypto Up/Down Spread-Capture Strategist](../finance/finance-crypto-updown-spread-capture-strategist.md): the both-sides "paired cost under $1" family, with a directional tilt and reward farming.
> - ⚡ [Crypto Up/Down Latency & Late-Window Strategist](../finance/finance-crypto-updown-latency-strategist.md): spot-tape latency, late-window certainty buying, and penny-floor harvesting.
> - 🚀 [Token Launch Event Market Strategist](../finance/finance-token-launch-event-market-strategist.md): FDV threshold ladders and public-sale markets.
>
> **All four agents applied to this research:** [crypto-bot-research/](crypto-bot-research/README.md), covering the forensic audit, spread-capture spec, latency playbooks, and token-launch playbook.

---

## 1. The vocabulary these reports use

| Term | Meaning |
|---|---|
| **Up/Down market** | A Polymarket binary on whether a coin closes the window above its opening price. Slugs look like `btc-updown-5m-<unix_ts>`. Cycles are 5m, 15m, 1h, 4h, and 1d. Coins are BTC, ETH, SOL, XRP, DOGE, and BNB. Settlement uses a Chainlink price. |
| **Both-sides rate** | The share of markets where the wallet bought both Up and Down. |
| **Paired cost** | Up VWAP + Down VWAP. If it is below $1.00, the paired shares lock in a profit whichever side wins. |
| **Dominance ratio** | Capital on the larger side divided by capital on the smaller side. It measures how much the bot tilts. |
| **Dominant-side WR** | How often the larger side wins, by dominance bucket. This is the most diagnostic number in every report. |
| **Hedge tax** | USDC spent on the losing leg of both-sides markets. |
| **Spread P/L** | (1 − paired cost) × paired shares. It separates the "market-making" edge from the "directional" edge. |
| **Cash-flow P&L** | −buys + sells + settlement payouts. It is often different from the figure Polymarket reports, because of open positions and rewards. |
| **Archetypes** | A = both-sides spread capture. B = directional. C = latency or stale-price exploitation. |

---

## 2. Master table: all crypto bots

| # | Bot (report) | Markets | Archetype | Both-sides | Window | Net P&L | ROI | What it actually does |
|---|---|---|---|---|---|---|---|---|
| 1 | [FlippingSharks](https://www.polyresearchrobotics.com/reports/flippingsharks) | BTC 5m only | A + B tilt | 98.3% | 12 d | +$4,121 (PM says +$17,755) | +0.30% | Buys both sides of every 5-minute BTC window, with a 7 s second-leg lag, and tilts toward one side. The spread itself nets −$1.9K, so all of the profit comes from the tilt. |
| 2 | [Bonereaper (Apr)](https://www.polyresearchrobotics.com/reports/bonereaper) | BTC/ETH (SOL) 5m/15m | A + fair-value B | 96.7% | 22 d | +$443,754 | +1.53% | A fair-value market maker making about 1.34M trades. The dominant side wins 97.7% at 5x or more, and the 1.0–1.5x bucket loses money. The report infers, but cannot prove, an external fair-value feed. |
| 3 | [Bonereaper (Jun update)](https://www.polyresearchrobotics.com/reports/bonereaper-update) | BTC/ETH/SOL 5m, 15m, 4h, daily | A + liquidity farming | 89.2% | 45 d | +$458,493 account (trading only +$88,606) | +0.20% trading | About 80% of income is liquidity rewards ($369,887). It loads the leading side late in the window at $0.90 or more. Trading ROI decayed from 1.53% to 0.20%. |
| 4 | [BTC5MScour](https://www.polyresearchrobotics.com/reports/btc5mscour) | BTC 5m only | C (near-certainty) | 0.26% | 27 d | +$26,520 | +1.77% | In the last seconds of a window, it sweeps stale asks at $0.96–$0.99 on the side BTC spot has already settled. 99.3% WR in the $0.90+ band. One unexplained June 21 cluster made more than $13K. |
| 5 | [Doggystyie](https://www.polyresearchrobotics.com/reports/doggystyie) | BTC 5m (+15m) | A (reward farmer) | 99.5% | 29 d | +$58,792 account (trading −$34,877) | −1.0% trading | Loses on trading by design and earns $93,668 in liquidity rewards (2.69% of volume). It breaks even only while rewards stay above about 1% of volume. |
| 6 | [Gabigol](https://www.polyresearchrobotics.com/reports/gabigol) | BTC/ETH/SOL 5m | A + strong B | 59.7% | 34 d | +$36,798 (incl. $6.6K LP rewards) | +2.09% trading | Buys a side that is already at $0.70–0.95 heavily, plus a $0.05–0.25 longshot hedge. 82.9% dominant WR at 3x or more. Runs three parallel coin books. |
| 7 | [NeverSmiling](https://www.polyresearchrobotics.com/reports/neversmiling) | BTC/ETH/SOL/XRP 5m/15m | A + B | 79.2% | 16 d | +$4,337 (PM says +$20,977) | +0.42% | Takes liquidity rather than quoting (report inference), using small clips. The $0.90+ band lost money despite a 95% WR. A $0.30–0.70 filter plus an hour filter lifts ROI to 1.59%. |
| 8 | [PBot-6](https://www.polyresearchrobotics.com/reports/pbot-6b) | BTC/ETH/SOL/XRP 5m, 15m, 1h | B in an MM "costume" | 45.2% | 14 d | +$23,564 | +4.71% | Bids near mid ($0.49–$0.51), then hedges about 128 s later. The dominant leg at 2x or more returned +22.8%. Below 3x there is no edge. |
| 9 | [X-MoneyForWhiskas](https://www.polyresearchrobotics.com/reports/x-moneyforwhiskas) | BTC/ETH 5m | A + taker-rebate engine | 97.6% | 26 d | +$134,180 account (trading +$38,776) | +0.94% trading | Pairs within 6 s at uniform $8 clips. $37.6K in taker rebates roughly equals its trading P&L. $51.9K of the total is unexplained. |
| 10 | [VidarX](https://www.polyresearchrobotics.com/reports/vidarx) | BTC 5m (crypto) | A + B | 93.3% | 32 d | +$103,949 | +0.87% | About 1.03M BUYs and 8 SELLs. The dominant leg at 2x or more made +$821K (+22.5%). Its odds-feed hypothesis contradicts its own all-crypto data, and one stray crude-oil bet lost $22K. |
| 11 | [sixx7](https://www.polyresearchrobotics.com/reports/sixx7) | BTC/XRP/SOL 5m/15m | A ("classical MM") | 99.2% | 21 d | +$19,190 (tables say $16,663) | +0.87% | Tiny clips (median $2.54). The dominant leg at 2x or more made +29.7%. Fills below $0.40 lose money. A template-only report. |
| 12 | [080BEc](https://www.polyresearchrobotics.com/reports/080bec) | BTC 5m only | A + B | 99.0% | 29 d | +$25,483 | +1.46% | Buys both sides of every window with near-uniform $10 clips, 24/7. P&L was decaying at the end of the window (rolling 7-day went from +$13K to −$3.3K). |
| 13 | [B1C58](https://www.polyresearchrobotics.com/reports/b1c58) | BTC 5m only | A | 99.0% | 29 d | +$27,984 | +1.59% | **The same wallet as 080BEc** (`0x60889af…080bec32f361`), analysed one day offset. A thin auto-generated report. |
| 14 | [0x04b6d7](https://www.polyresearchrobotics.com/reports/0x04b6d7) | BTC/ETH/SOL/XRP 5m/15m, 1h | B using A mechanics | 98.2% | 20 active d | +$36,132 | +0.72% | Sweeps both sides at market open (median paired cost $0.968) and sleeps 21:00–03:00 UTC. The profit is really directional: 92.9% WR at 3x or more. One cluster on May 1 lost $6.4K. |
| 15 | [ohanism](https://www.polyresearchrobotics.com/reports/ohanism) | BTC/ETH/SOL/XRP 5m/15m | B + active exits | 33.3% | 27 d | +$258,687 | +3.02% | The only up/down bot here that **sells**, on 15% of trades. It cuts losing legs at $0.20–0.35 and takes profit on winners in 25% tranches. Spread P/L is −$142K, so the edge is directional. |
| 16 | [Ratue](https://www.polyresearchrobotics.com/reports/ratue) | BTC/ETH/SOL 15m only | A + B | 88.3% | 28 d | +$18,952 | +1.92% | Accumulates through the whole 15-minute window and loads the leading side in minutes 12–14. Power-law, conviction-scaled fill sizes. |
| 17 | [SLIP-ME](https://www.polyresearchrobotics.com/reports/slip-me) | BTC 5m | B + C, "MM costume" | 98.6% | 23 d | +$111,822 | +2.59% | Opens both legs early, trend-follows the tape, and loads the leader in the final 90 s. The spread leg lost $97.5K and the directional leg made $204K. Blocking underdog buys once skew reaches 2x gives +12.7% ROI. |
| 18 | [SIRMARTINGALE](https://www.polyresearchrobotics.com/reports/sirmartingale) | BTC 5m/15m, ETH 5m | C latency arb | 0% | 28 d | +$119,586 cash-flow (+$54K resolved) | +82.95% | Buys when Coinbase/Binance/Kraken spot moves before the CLOB requotes, then **sells into the catch-up** within 15–60 s. About 61% of its alpha comes from exits. No martingale, despite the name. |
| 19 | [LIL222](https://www.polyresearchrobotics.com/reports/lil222) | BTC 5m | Penny-floor harvester | 1.6% | 25 d | +$6,267 | +56% | Buys at exactly $0.01 and immediately offers at $0.02. Whatever doesn't sell rides to settlement as a 99× lottery ticket. Win rate 1.36%. *The page header describes a different trader.* |
| 20 | [Sharky6999](https://www.polyresearchrobotics.com/reports/sharky6999) | Crypto 34% (BTC/ETH/SOL/HYPE) + sports | Favorite buyer | 1.0% | 31 d | +$59,615 | +0.29% | About 97% of capital sits in the $0.90–$1.00 band, with a 98.9% WR. Its worst losses are all 5-minute BTC/ETH Up/Down markets. No filter helps. |
| 21 | [ExitLiquidty](https://www.polyresearchrobotics.com/reports/exitliquidty) | Token-launch FDV & public-sale markets | B (event specialist) | 0% | 34 active d | +$330,940 cash-flow (+$185,765 resolved) | ~62–86% | Builds Yes ladders across MegaETH/EdgeX FDV thresholds, uses DEX price discovery while the CLOB lags, sells actively (1.37× sell/buy), and buys "No" on unreachable sale thresholds. |

**Unique wallets: 19.** 080BEc and B1C58 share one address, and so do the two Bonereaper reports. VidarX's address is only given truncated.

KCH123 (a sports bettor) and a few others place occasional crypto bets. Those are incidental and not included.

---

## 3. The strategy families, and what the evidence says

### Family A: Both-sides "paired cost" market makers
*FlippingSharks, Bonereaper, Doggystyie, Gabigol, NeverSmiling, X-MoneyForWhiskas, VidarX, sixx7, 080BEc/B1C58, 0x04b6d7, Ratue, PBot-6.*

How they work:
1. Discover each new up/down market within seconds of its creation.
2. Buy Up and Down in small clips, usually walking the ask book (taker-style), with a second leg 4–256 s after the first.
3. Tilt capital toward one side.
4. Hold to settlement. Almost all of them never sell.

The reports keep finding the same things:
- **The spread alone rarely pays.** FlippingSharks (−$1.9K), Bonereaper Jun (−$685K), SLIP-ME (−$97.5K), and ohanism (−$142K) all lose on spread P/L. The money comes from the **tilt**: the dominant-side WR climbs from about 55–65% at 1.0–1.5x to 83–98% at 3x or more.
- **"Dominant leg at ≥2x only" is the most productive filter in almost every report:** VidarX +22.5%, sixx7 +29.7%, PBot-6 +22.8%, 080BEc +19.6%, 0x04b6d7 +18.1%, Ratue +12.5%. The catch is that the filter is computed **after the fact**, because final dominance is known only at the close.
- **The $0.30–0.70 "sweet spot" price filter is destructive** in most reports. It breaks the pairs and throws away the near-certainty fills.
- **Rewards and rebates can be the whole business.** Doggystyie loses on trading and wins on rewards. About 80% of Bonereaper's June income is rewards. X-MoneyForWhiskas's taker rebates roughly equal its trading P&L. Every report rates a reward-program change as a critical risk.
- **Edges decay.** Bonereaper's trading ROI fell from 1.53% to 0.20%, 080BEc's rolling 7-day P&L went negative, and FlippingSharks faded late. Rising paired cost is the warning sign.

### Family C: Latency, late-window, and microstructure
*SIRMARTINGALE, BTC5MScour, SLIP-ME (hybrid), LIL222, Sharky6999 (crypto leg).*

- **Spot-to-CLOB lag (SIRMARTINGALE):** exchange spot moves in milliseconds, while the CLOB requotes 1–30 s later. It buys the stale side and sells into the requote. The report says a residential connection on REST "loses the race".
- **Near-certainty sweeping (BTC5MScour):** once BTC spot has clearly settled the window, it buys $0.96–$0.99 asks that resolve at a 99.3% realized rate against roughly 97% implied. The main risks are a spot-feed outage and a reversal in the last seconds.
- **Penny floor (LIL222):** buy at $0.01, offer at $0.02. The edge is about $0.025 EV per ticket, but it disappears when other bots compete and caps out at roughly $50–75K bankroll.
- **Favorite buying (Sharky6999):** a 98.9% WR at a +0.29% ROI. One $0.9x loss wipes out many wins. The tail risk is hidden.

### Family B: Event specialists
*ExitLiquidty.*
FDV threshold ladders on token launches (e.g. `megaeth-market-cap-fdv-1pt5b-one-day-after-launch`). The edge is real-time DEX price data plus thin, lazily priced books. The big risk is that every threshold on one launch is 100% correlated: rolling 15-day P&L swung from +$141K to −$22K.

---

## 4. Shared infrastructure the reports describe
- A persistent **Polymarket CLOB WebSocket** (L2 book, market-creation and resolution events). Most reports say REST polling is too slow.
- **Spot feeds** from Coinbase, Binance, or Kraken WebSockets at sub-second cadence, used to compute fair probability against the window's opening price.
- A **USDC EOA on Polygon** with a nonce manager for concurrent fan-out bursts. Gas is negligible (about $0.02 per trade or less).
- Latency targets from under 2 s (spread capture) down to colocated, sub-500 ms (latency arb and penny floor).
- Kill switches for feed or RPC loss, plus daily loss circuit breakers.

## 5. Data-quality caveats found while reading
- Several reports disagree with Polymarket's own P&L (FlippingSharks, NeverSmiling, X-MoneyForWhiskas, sixx7, ExitLiquidty).
- B1C58 and 080BEc are the same wallet, and so are Bonereaper April and June.
- 0x04b6d7 and ohanism split spread and directional P&L as "spread + hedge tax + directional = net", which counts the losing leg twice. Under the "net − spread" rule the other reports use, 0x04b6d7's directional result is about −$154K, not +$1.79M (see the [forensic audit](crypto-bot-research/01-forensic-audit.md)).
- ExitLiquidty's "86.4% ROI" is total cash flow over all buys. On resolved buys it is 62.0%.
- LIL222's header block describes a different trader.
- VidarX proposes a sportsbook feed for an all-crypto book.
- Rolling-window counts and day counts are inconsistent in several reports.
- Windows are short, 12–45 days, so one volatile session can dominate the results (PBot-6 on May 18, BTC5MScour on June 21).

Treat every number above as one reconstruction of a short window, not a durable edge.

---

## 6. Non-crypto reports (not covered above)
| Report | Focus |
|---|---|
| Humbleboy | CS2 esports, directional (−$14.2K) |
| 88M | Tennis live-betting accumulation |
| Vito3Corleone | Concentrated soccer bets (+$1.17M on 8 markets) |
| Michi1, HondaCivic, GGHFF | Weather temperature markets |
| LBTrading | Sports both-sides maker (rebate earner) |
| Aaa298 | CS2 map-level live trading |
| Geiyecapixie | Live League of Legends directional plus early exit |
| RandomGameBet | Esports both-sides market maker |
| SineNooneEI | Tennis/MLB directional |
| FerrariChampions2026 | Sports both-sides engine (+$1.14M) |
| KCH123 | NFL/college sports |
| SWISSTONY, GAMBLINGISALLYOURNEED | Always-on sports makers |
| BillBenter2026 | Tennis/NBA/esports both-sides plus tilt |
| RN1 | Sports-heavy both-sides inventory dossier |
