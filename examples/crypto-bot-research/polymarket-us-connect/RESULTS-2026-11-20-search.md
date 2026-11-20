# Variation Search: Results (public Polymarket US data, 2026-11-20)

The goal was to find strategy variations that are profitable without luck, and to see what it would take to make **$100–200 a day**.

**Command:** `python -m pmus_recorder search` (`pmus_recorder/search.py`).

**Data:** 45,932 resolved Up/Down markets over 45 days (BTC, ETH, SOL and XRP; 5m, 15m and 1h windows).

## 1. The price delay is 60 s, not 90 s

The paper trader logs live best bid and ask with exact clock times. I downloaded `/v1/price-history` for 31 of the same markets and lined the two up. A history point equals the live quote **exactly 60 s after its timestamp**: the mean gap is 0.015, and the next best offset has a mean gap of 0.028.

| History point compared with the live quote at timestamp + | 0 s | 30 s | 55 s | **60 s** | 65 s | 90 s | 120 s |
|---|---|---|---|---|---|---|---|
| Mean price gap | 0.138 | 0.068 | 0.028 | **0.015** | 0.041 | 0.089 | 0.127 |
| Exact match | 12% | 23% | 30% | **44%** | 20% | 21% | 7% |

**Why the earlier 90 s was wrong:** it came from a lead-lag test against the public 1-second index candles, and those candles themselves run about 30 s behind the market.

**What that broke:** with 90 s, the backtest bought quotes that were about 30 s staler than the index it compared them with. That is an edge a live bot cannot get.

**Consequence:** the per-coin results in [RESULTS-2026-11-20-all-strategies.md](RESULTS-2026-11-20-all-strategies.md), which used 90 s, are **too optimistic**. At 60 s, the late-window bots (favourite, model_edge and model_edge_strict) lose about $216 in total over the test period. Only the 1-hour SOL and XRP windows stay clearly positive.

## 2. The search

- **The space:** 11,880 variations per coin and window, over 12 segments, for **142,560 tries** in all. Each variation combines:
  - a decision time: 60, 120 or 180 s before close
  - a side: the index leader or the other side
  - a price band: any $0.02–0.98 range
  - a minimum index lead: 0–20 bps
  - a minimum model edge: none, or 0–10¢
- **Rules against luck**, all decided before the holdout was looked at:
  1. **Dates are split** into A (the first 50%), B (the next 25%) and a **holdout** (the last 25%, 8.6 days). The model is fitted on A only. The holdout is used once, at the end.
  2. **Profitable in A and in B separately**, with at least 100 trades.
  3. **Still profitable at a pessimistic 50 s delay**, where prices look fresher and index-following looks worse.
  4. **A z-score of at least 4.96.** That is the Bonferroni bar for 142,560 tries at 5% family-wise error.
     - The z-score is tested against the no-edge win rate, price + fee. A plain t-statistic gives false passes on 95–98¢ favourites, because with no loss yet their spread is about 0.
     - A first run with the t-statistic "passed" many 95–98¢ variations. Counting their losses shows none is significant once you allow for 142,560 tries: the best had p = 5×10⁻⁵ against a bar of about 3.5×10⁻⁷.

## 3. Result: two variations pass everything

| Coin / window | Rule (decide 60 s before close) | Dev (36.5 days) | **Holdout (8.6 days)** | At 50 s delay |
|---|---|---|---|---|
| **SOL 1h** | Buy the index leader if it leads by ≥ 5 bps, at any price $0.02–0.98 | 304 trades, 1 loss, +7.4¢, z 5.3 | **86 trades, 0 losses, +8.8¢, z 3.3** | +8.8¢ |
| **XRP 1h** | The same, plus model edge ≥ 0 | 357 trades, 1 loss, +7.4¢, z 5.8 | **154 trades, 0 losses, +8.3¢, z 4.1** | +8.4¢ |

The other 10 segments have no passing variation. Their best dev z-scores were 2.0–4.4, below the bar.

**Both together on the holdout, 1 contract per trade:** **$2.27 a day**. All 9 holdout days were positive; the worst day made $1.13.

## 4. What $100–200 a day would take

At $2.27 a day per contract, $100–200 a day needs **about 44–88 contracts per trade**. That is $40–80 at risk per trade, since the average price is about $0.91.

- **The win rate isn't certain.** 0 losses in 240 holdout trades gives a 95% upper bound of about 1.2% on the loss rate.
- **A loss is expensive.** One loss costs about $40–80, which is about 10 trades' profit.
- **Unknown: can that many contracts be bought?** The price history has no sizes, and hourly SOL/XRP books near the close are likely thin.
- **How to find out:** the paper trader now runs these as **`hourly_leader`** (SOL 1h, XRP 1h). At every paper buy, it logs how many contracts the public book offered at that price or better. The book is up to 30 s old, so this is a rough size check.

## Verdict

- **No variation is good for $100–200 a day at 1 contract.**
- **The only luck-resistant edge is small:** hourly SOL/XRP leaders 60 s before close, about +8¢ per contract and about 28 trades a day.
- **It scales to that target only if 44–88 contracts are actually available** at the quoted price each time. That is unproven.
- **Next step:** let the paper trader run for a week or more, and read the logged book sizes before risking money.

> Research only. Not financial advice. Nothing in this folder trades.
