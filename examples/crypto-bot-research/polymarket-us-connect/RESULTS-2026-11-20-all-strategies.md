# Seven Strategy Families Compared (public Polymarket US data, 2026-11-20)

**Data:**
- 45,932 resolved Up/Down markets over 45 days: BTC, ETH, SOL and XRP, in 5m, 15m and 1h windows.
- 342,089 stored display-price points and 5.8 million one-second settlement-index candles.
- 7 of 78,277 download requests failed (HTTP 500).
- Command: `backfill --assets btc,eth,sol,xrp --horizons 5m,15m,1h --days 45`, then `compare`.

**Method:**
- **Walk-forward:** for each of the 12 coin/window segments, each family's settings are chosen on the first 2/3 of the dates. Results are reported only on the last 1/3.
- **Trades:** 1 contract each, at the stored display price, paying the Tier 1 taker fee (θ = 0.095). A price of $0.99 is unbuyable.

## Data problem found and fixed: price timestamps run about 90 s early

The first full run showed last-minute favourites winning 100% of 200+ trades at about $0.96. That is too good to be true.

- **The test:** a lead-lag check compared the changes between `/v1/price-history` points with moves in the 1 s settlement index. It used 400 random markets, each with a 12-minute index window.
- **The result:** price moves match index moves about **90 s after** the price's timestamp. There is no match at the stated time.

| Index shifted by | 0 s | +30 s | +60 s | +80 s | **+90 s** | +100 s | +120 s | +150 s |
|---|---|---|---|---|---|---|---|---|
| Correlation | −0.03 | 0.11 | 0.43 | 0.59 | **0.61** | 0.58 | 0.37 | 0.09 |

**Consequence:** with raw timestamps, a "T-60" decision was using the price from about T+30 s, after the result was known.

**The fix:** each point now counts as known at `timestamp + 90 s` (`--price-delay`). Each decision is made at that moment, using index data only up to then.

**The earlier BTC results ([RESULTS-2026-11-20.md](RESULTS-2026-11-20.md)) used raw timestamps and are superseded.**

## Results at the measured delay (90 s): total test-period P&L, all 12 segments

| Family | What it does | Segments with profit | Test P&L (1 contract per trade) |
|---|---|---|---|
| **model_edge** | Buy the index leader at T-90 s when a calibrated volatility model says it beats price + fee | 11 / 12 | **+$231** |
| **favourite** | Buy the index leader at T-90/T-150 s if priced $0.50–$0.98 | 8 / 12 | +$79 |
| **disagreement** | Buy the index leader when the market prices it below $0.50 | 7 / 12 | +$63 |
| longshot (LIL222 style) | Buy any side at $0.01–$0.10 near the close | 1 / 12 | −$24 |
| momentum (SLIP-ME style) | Buy the side whose price jumped in the last 2–5 min | 1 / 12 | −$44 |
| both_sides (FlippingSharks / Gabigol style) | Buy one side cheap, then the other side if the pair costs under $1 | **0 / 12** | **−$702** |
| neversmiling (NeverSmiling style) | Buy both sides at $0.30–$0.70 throughout the window | **0 / 12** | **−$1,939** |

model_edge per segment at the 90 s delay (EV is profit per contract after the fee):

| | 5m | 15m | 1h |
|---|---|---|---|
| BTC | +2.7¢ (1,394 trades) | +2.4¢ (265) | −4.1¢ (45) |
| ETH | +4.7¢ (1,299) | +0.6¢ (353) | +3.5¢ (99) |
| SOL | +5.5¢ (1,163) | +1.3¢ (362) | +7.8¢ (126) |
| XRP | +2.3¢ (1,077) | +1.0¢ (374) | +6.9¢ (227) |

## How sure is that? Sensitivity to the delay

| Delay assumed | favourite | model_edge | disagreement | both_sides | longshot | momentum | neversmiling |
|---|---|---|---|---|---|---|---|
| 60 s | $0 | −$33 | −$26 | −$702 | −$23 | −$48 | −$1,976 |
| 75 s | −$20 | +$18 | +$4 | −$702 | −$24 | −$44 | −$1,939 |
| **90 s** | **+$79** | **+$231** | **+$63** | −$702 | −$24 | −$44 | −$1,939 |
| 105 s | +$217 | +$491 | +$232 | −$641 | −$24 | −$44 | −$1,766 |
| 120 s | +$394 | +$720 | +$410 | −$641 | −$24 | −$44 | −$1,766 |

**Why the index-following families move with the delay:**
- **A longer delay makes the price staler than the index.** The test then "buys" a quote the real market had already moved, so it overstates profit.
- **A shorter delay makes the price fresher than the bot's information.** That understates profit.

**What that means for the three index-following families:**
- **The profit is about the same size as the timing uncertainty:** 15 s changes it from break-even to +$231.
- **disagreement is a warning sign.** It "wins" 60%+ of trades bought at about $0.40. That pattern is typical of stale quotes, not of a real edge.

**The price-only families do not depend on the timing.** They lose at every delay.

## Verdict

1. **Drop both_sides, NeverSmiling-style, long-shot and momentum.** They lose after fees in almost every coin and window, at every timing assumption.
   - The top-of-book Up and Down prices always sum to $1 or more, so buying both sides never locks in a profit for a taker.
   - Repeated buying in the middle of the window, NeverSmiling-style, just pays the fee again and again.
2. **The late-window index-leader bot (model_edge) is the only candidate left, but this data cannot prove it.**
   - The apparent +1¢ to +8¢ per contract depends on price timing to within about 15 s.
   - The display prices are one-minute samples with no size.
3. **The next step is live timing, not more history.**
   - **What is needed:** the authenticated market websocket (needs an API key) with `record --assets btc,eth,sol,xrp --horizons 5m,15m,1h` for 1–2 weeks. That gives real book times and sizes.
   - **The test to run:** rerun `report` with model_edge on those live books.
   - **The rule:** only if it still shows an edge after fees, at real sizes, is a tiny live test justified.

> Research only. Not financial advice. Nothing in this folder trades.
