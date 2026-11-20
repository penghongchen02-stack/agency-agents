# Both-Sides / Paired-Cost Bots: Comparative Teardown and Strategy Spec

*Analyst persona: Pairwise (Crypto Up/Down Spread-Capture Strategist). Sources: the PR&R catalogue and dossiers A/B/C, with raw reports checked where noted. Every figure is as the report states it. **[inf]** marks my inference. **[judgment]** marks a parameter I chose. **[rpt-inf]** marks something the report itself calls an inference. Not financial advice. Prediction-market access is restricted in some jurisdictions, so confirm it is legal for your jurisdiction and account before running anything.*

Short version: in this sample the spread rarely pays. The tilt pays when the dominance curve is steep, and incentives decide whether the weakest books survive at all.

---

## 1. Comparative table

Abbreviations: BS% = both-sides rate. Lag = median second-leg lag. Clip = median fill. Dom WR = dominant-side win rate in the 1.0–1.5x bucket and the 3x+ bucket. Spread = spread P/L. Trading = trading (non-incentive) P&L. Inc = incentives. ROI = trading ROI on buy notional. n/r = not reported.

| Bot (window) | Universe | BS% | Med. paired | Lag | Clip | Dom WR 1–1.5x / 3x+ | Spread | Trading | Inc | ROI | Sells |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FlippingSharks (12 d) | BTC 5m | 98.3 | $0.9996 | 7 s | $4.21 | 62.7 / 95.8 | **−$1.9K** | +$4.1K (PM says +$17.8K) | n/r | +0.30% | 6 ($273) |
| Bonereaper Apr (22 d) | BTC/ETH (SOL) 5m/15m | 96.7 | $1.006 | 10 s | $5.56 | 59.0 / 91.2 (3–5x), 97.7 (5x+) | n/r | +$443.8K | not discussed | +1.53% | 2,866 (0.08% of flow) |
| Bonereaper Jun (45 d) | BTC/ETH/SOL 5m, plus 15m/4h/daily | 89.2 | $1.0163 | 21 s | $3.94 | 57.0 / 87.6 | **−$685K** | +$88.6K | **+$369.9K** LP | +0.20% | 0 |
| Doggystyie (29 d) | BTC 5m (+15m) | 99.5 | $1.0135 | 4 s | $17.81 | 60.4 / 96.8 | −$40.7K | **−$34.9K** | **+$93.7K** LP (2.69% of vol) | −1.0% | 0 |
| Gabigol (34 d) | BTC/ETH/SOL 5m | 59.7 | $0.969 | 81 s | $1.38 | 53.2 / 82.9 | +$34.8K (theoretical) | +$30.2K | +$6.6K LP | +2.09% | 0 |
| NeverSmiling (16 d) | BTC/ETH/SOL/XRP 5m/15m | 79.2 | $0.9836 | 50 s | $3.51 | 53.7 / 78.8 | +$0.16K | +$4.3K (PM says +$21.0K) | n/r | +0.42% | 0 |
| PBot-6 (14 d) | 4 coins, 5m/15m/1h | 45.2 | $0.9707 | 128 s | $3.69 | 49.4 / 60.4 | +$1.0K | +$23.6K | n/r | **+4.71%** | 0 |
| X-MoneyForWhiskas (26 d) | BTC/ETH 5m | 97.6 | $0.9925 | 6 s | $8.20 | 62.6 / 92.6 | +$33.1K (est.) | +$38.8K | **+$43.5K** (taker $37.6K, maker $5.3K, LP $0.6K), plus $51.9K unexplained | +0.94% | 0 |
| VidarX (32 d) | BTC 5m | 93.3 | $0.9917 | 10 s | $5.80 | 57.9 / 84.2 | +$58.5K (theoretical) | +$103.9K (crypto only +$125.5K) | n/r | +0.87% | 8 |
| sixx7 (21 d) | BTC/XRP/SOL 5m/15m | 99.2 | $0.9902 | 20 s | $2.54 | 66.7 / 97.3 | +$42.9K (theoretical) | +$19.2K (tables say $16.7K) | n/r | +0.87% | 0 |
| 080BEc / B1C58 (29 d, same wallet) | BTC 5m | 99.0 | $0.9907 / $0.9893 | 10 s | $10.13 | 61.9 / 95.8 | +$15.7K / +$18.4K | +$25.5K / +$28.0K | n/r | +1.46% / +1.59% | 0 |
| 0x04b6d7 (20 active d) | 4 coins, 5m/15m/1h, sleeps 21–03 UTC | 98.2 | $0.9679 | 16 s | $3.45 | 55.6 / 92.9 | +$189.7K | +$36.1K | n/r | +0.72% | 0 |
| Ratue (28 d) | BTC/ETH/SOL 15m | 88.3 | $0.9999 (mean $0.945) | 256 s | $1.43 | 55.5 / 85.2 | +$20.6K | +$19.0K | n/r | +1.92% | 0 |
| ohanism (27 d), active-exit hybrid | 4 coins, 5m/15m | 33.3 | $1.059 | 140 s | $5.42 | 53.9 / 77.7 | **−$142K** | +$258.7K | n/r | +3.02% | **105,866 (15.2%)** |

**Comparability warnings:**
- "Spread P/L" is not computed the same way everywhere. 080BEc defines it per market as (1 − paired cost) × paired shares. X-MoneyForWhiskas estimates it from mean paired cost × deployed capital. Gabigol, VidarX and sixx7 label theirs "theoretical". Some figures are therefore net of above-$1 pairs and some are not **[inf]**.
- Hedge tax and spread do not reconcile in several reports (Ratue, 0x04b6d7).
- Polymarket's own P&L disagrees with the computed figure for FlippingSharks, NeverSmiling, X-MoneyForWhiskas and sixx7.
- Every window is 12–45 days long.

---

## 2. Which design elements go with positive *trading* P&L

Trading P&L is positive in 13 of 14 books. Only Doggystyie is negative. "Positive" therefore barely discriminates, so the useful question is which elements go with *higher* trading ROI. The ranges are wide, from −1.0% to +4.71%.

### Consistently associated with better trading results

1. **A steep dominance curve, meaning the tilt is informed.** The books whose dominant leg wins 92–98% at 3x+ all made money on trading: FlippingSharks, Bonereaper Apr, X-MoneyForWhiskas, sixx7, 080BEc and 0x04b6d7. Doggystyie is the exception at 96.8%, and its spread losses outran the tilt. The "dominant leg ≥2x" filter is positive in every report that runs it: VidarX +22.5%, sixx7 +29.7%, PBot-6 +22.8%, 080BEc +19.6%, 0x04b6d7 +18.1%, Ratue +12.5%, ohanism +6.4%, X-MoneyForWhiskas +3.26%. It is retrospective, though, so it proves the tilt has information. It does not prove you can capture it.
2. **Profit decomposes as tilt, not spread.** Among the hold-to-settle books, the highest-ROI ones (PBot-6 4.71%, Gabigol 2.09%, Ratue 1.92%) have spread P/L that is small relative to their directional residual. PBot-6's spread was +$1.0K against +$23.6K trading. The books that rely mainly on spread (X-MoneyForWhiskas, sixx7) sit at 0.87–0.94%.
3. **Keeping both legs rather than stripping the hedge.** Several reports test "dominant-leg only" and find it worse than the full book: Gabigol 1.81% against 2.09%, and Bonereaper's April filters kept hedges. Gabigol recommends 3x+ focus *while keeping both legs*, and X-MoneyForWhiskas says the hedge is never zero.
4. **No price-band "sweet spot".** The $0.30–0.70 filter is destructive in FlippingSharks (−$1,763), Bonereaper Jun (−$116.8K), Gabigol (−$18.9K), PBot-6, sixx7, X-MoneyForWhiskas, Ratue and ohanism (−$140K). NeverSmiling is the one exception, at +$2.5K over 16 days.
5. **Hold to settlement.** Twelve of thirteen wallets never sell meaningfully. ohanism is the only seller (see below).

### Mixed or not associated

- **Median paired cost below $1.00.** Among hold-to-settle books, a median above $1.00 goes with weak results: Doggystyie −1.0%, Bonereaper Jun 0.20%, FlippingSharks 0.30%. The exception is Bonereaper Apr at $1.006 and 1.53%, which also had the steepest curve. A low median does not guarantee a good result either: 0x04b6d7 had the lowest median ($0.9679) and only 0.72%, with its hedge tax nearly cancelling the spread. **[inf]** The paired-cost gate is necessary but not sufficient.
- **Second-leg lag.** The short-lag books (4–10 s: Doggystyie, X-MoneyForWhiskas, FlippingSharks, VidarX, 080BEc) range from −1.0% to +1.59%. The long-lag books (50–256 s: NeverSmiling, Gabigol, Ratue, ohanism, PBot-6) range from 0.42% to 4.71%. **[inf]** A conditional, information-waiting hedge may beat atomic pairing, but this rests on 5 vs 5 books and is confounded with asset mix.
- **Late or near-certainty buying at $0.90 or more.** The $0.90+ band made +$125K for Bonereaper Jun and +2.57% for VidarX. It lost for Gabigol (−0.38%), NeverSmiling (−$4.5K at 95.4% WR) and X-MoneyForWhiskas (−1.4%), and was about flat for FlippingSharks. The evidence does not support it as a default.
- **Cheap hedge band ($0.00–0.10).** It is the drag for 080BEc (−15.6%), B1C58 (−16.7%) and sixx7 (−12.9%), but strongly positive for ohanism (+53.4%) and NeverSmiling (+7.2%). There is no consistent sign.
- **Hour and day filters.** FlippingSharks is the only book where an hour filter improved both P/L and ROI (+$367). Elsewhere they are no-ops or destructive (Bonereaper Jun, Doggystyie, PBot-6, sixx7). Gabigol's case is only a "small genuine lift". The hours named differ between the tables and the prose in several reports. These look like noise.
- **Multi-asset vs BTC-only.** Both groups contain strong and weak books. No association.
- **Active exits (ohanism).** ohanism made +3.02% despite −$142K spread P/L. That is one wallet, and the report does not isolate how much of the result comes from the sell ladder rather than the tilt.

### Associated with *worse* trading results

- **Heavy incentive dependence.** The three books with the largest measured incentives have trading ROI of −1.0% (Doggystyie), 0.20% (Bonereaper Jun) and 0.94% (X-MoneyForWhiskas). **[inf]** Rewards let a book stay alive with a poor spread. The direction of cause is unknown.
- **Time.** Edges decayed within every window that was long enough to show it:
  - Bonereaper's trading ROI fell from 1.53% to 0.20%.
  - 080BEc's rolling 7-day P/L went from +$13.1K to −$3.3K.
  - FlippingSharks' W22 was +$631 against +$3,488 the week before.
  - Ratue's W19 was negative.
  - sixx7's late weeks were weaker.

---

## 3. Strategy spec

### Base variant: "paired-open, conditional causal tilt"

Design rationale **[inf]**: the core is the 080BEc and X-MoneyForWhiskas pairing discipline, which gave the most stable trading results without incentives. On top of that sits a causal spot-implied tilt, in the style of PBot-6, 0x04b6d7 and Bonereaper Jun Mode B, plus Gabigol's rule of keeping both legs. It does not assume any incentive income.

```yaml
strategy: crypto-updown-paired-tilt-base
mode: trading_only               # incentives booked separately, never in the go/no-go
universe:
  slugs: ["btc-updown-5m-*", "eth-updown-5m-*"]
    # BTC 5m traded by all but Ratue; ETH 5m in Bonereaper, Gabigol, X-MoneyForWhiskas,
    # 0x04b6d7. X-MoneyForWhiskas playbook: "do not extend to 15m or 1h".
  phase_2_candidates: ["sol-updown-5m-*", "btc-updown-15m-*"]
    # add only after a per-asset backtest [judgment]. NeverSmiling flags SOL/XRP capacity of
    # about $25K per wallet. Ratue is the only 15m-only book (+1.92%).
  avoid: ["*-1h-*", "*-4h-*", "daily", "non-crypto"]
    # VidarX lost -$22K on one crude-oil bet. Bonereaper's 4h/daily share was tiny.
entry:
  discovery: market-creation event over the CLOB WebSocket, entry within 30 s of open
    # FlippingSharks, X-MoneyForWhiskas (first 30-60 s), 0x04b6d7 (2-8 s)
  window: {start_after_open_s: 15, stop_before_close_s: 30}
    # 080BEc playbook (15 s / 30 s). X-MoneyForWhiskas, PBot-6 and Doggystyie also skip
    # the final 30 s.
  paired_cost_gate:
    basis: best_ask_up + best_ask_down, after walking to clip size   # Ratue, ohanism
    target: 0.97      # Gabigol, NeverSmiling, 0x04b6d7, Ratue
    max: 0.98         # X-MoneyForWhiskas, PBot-6 ("hedge only if combined <= 0.98")
    hard_stop_vwap: 1.03   # Bonereaper Apr max <$1.03. Doggystyie: >1.03 is a HIGH risk.
                           # 0x04b6d7 uses 1.05. 1.03 is [judgment], the stricter end.
  min_top_of_book_depth_usdc: 50   # [judgment] Persona template. No report measures depth.
  max_book_spread: 0.15            # NeverSmiling playbook
  second_leg_max_lag_s: 10         # X-MoneyForWhiskas 6-10 s, FlippingSharks <10 s, 080BEc 10 s
  unpaired_timeout_s: 30           # FlippingSharks: cancel the unpaired leg after 30 s
  max_entry_price_tilt_adds: 0.90  # X-MoneyForWhiskas: avoid >=0.90 entries. Mixed $0.90+
                                   # band evidence (Sec. 2). [judgment] to apply to tilt adds only.
  price_band_filter: none          # $0.30-0.70 filter is destructive in 8+ reports
tilt:
  signal: spot_fair_prob_gap       # p_up(spot, window_open, secs_left, sigma) - CLOB mid
    # PBot-6, 0x04b6d7, Bonereaper Jun, Doggystyie and 080BEc all propose spot vs window
    # open [rpt-inf]. The real signals are unobserved.
  sigma: realized_vol_30m          # PBot-6 (30-min realized vol input)
  spot_feeds: [coinbase_ws, binance_ws]   # most reports. Reference price must match the
                                          # market's resolution source (persona Phase 1).
  tiers:                           # 0x04b6d7 gaps 3/6/10% -> 1.5-4x. PBot-6 0.03/0.08.
    - {gap: 0.03, ratio: 1.5}      # Bonereaper Jun conviction tiers 1.5/2.5/4.0
    - {gap: 0.06, ratio: 2.5}
    - {gap: 0.10, ratio: 4.0}
  max_ratio: 4.0                   # [judgment]. 080BEc allows 5x. Below 0x04b6d7's 15% tier.
  hedge_floor_ratio: 0.25          # FlippingSharks: subordinate leg 10-40% of dominant.
                                   # X-MoneyForWhiskas: hedge never zero. 0.25 is [judgment].
  tilt_adds_require_gate: true     # added dominant shares keep blended paired VWAP <= hard_stop
sizing:
  clip_usdc: "min(10, 0.2% bankroll)"   # Bonereaper Jun Mode A. 080BEc $5-15. X-MoneyForWhiskas ~$8.
  fill_hard_cap_usdc: 50                # [judgment]. 080BEc max $54, Doggystyie $84.
  per_market_cap: "1% bankroll"         # Bonereaper Jun. FlippingSharks $220-500/market.
  max_open_exposure: "50% bankroll"     # Bonereaper Jun
  bankroll_ceiling_per_wallet_usd: 25000  # FlippingSharks capacity ~$25-50K (BTC 5m). [judgment] low end.
exit:
  policy: hold_to_settlement       # 12 of 13 wallets
  stale_position_cleanup_h: 48     # Bonereaper Jun
schedule:
  hours_utc: all                   # hour filters are mostly no-ops or destructive (Sec. 2)
  skip_hours_utc: []               # add only hours that fail out of sample
risk:
  daily_loss_breaker: "5% bankroll"   # [judgment]. 0x04b6d7 proposes 12%, which is too loose
                                      # for a ~1% ROI book.
  per_market_max_loss_alert_usd: "per_market_cap"   # ohanism's stated cap was breached 10x
                                                    # (-$3,332), so verify live
infra:
  clob: websocket L2 + market events; REST polling is insufficient   # FlippingSharks, Bonereaper Jun
  latency_target_ms: 500           # Gabigol <500 ms, X-MoneyForWhiskas <1 s, 080BEc <2 s.
                                   # 0x04b6d7: +200 ms may wipe out the margin.
  wallet: single Polygon EOA, nonce manager for concurrent pairs   # all playbooks
kill_switches: see Section 5
```

### Incentive-mode variant (diff). INCENTIVE-DEPENDENT.

> **Do not run** without a written, confirmed reward or rebate rate. Reward formulas are not public (Doggystyie, Gabigol, Bonereaper Jun). Below about $1M a month of volume, rewards are "≈ negligible" (Bonereaper Jun). The trading leg is expected to be negative.

```diff
- mode: trading_only
+ mode: incentive_dependent        # go/no-go = trading P&L + CONFIRMED incentives
+ preconditions:
+   confirmed_reward_rate_of_volume: ">= 1.5%"   # Doggystyie: wants >1.5% before running.
+                                                # Break-even about 1.0%.
+   confirmed_program_terms_date: required, re-confirmed monthly   # persona Phase 4
- universe.slugs: [btc-5m, eth-5m]
+ universe.slugs: ["btc-updown-5m-*"]           # Doggystyie: every BTC 5m window, 24/7
+ coverage_target: ">95% of windows"            # Doggystyie
- second_leg_max_lag_s: 10
+ second_leg_max_lag_s: 5                       # Doggystyie median 4 s
- tilt.hedge_floor_ratio: 0.25
+ tilt.hedge_floor_ratio: 0.5                   # never skip the hedge. Two-sided volume is
+                                               # likely what is rewarded [rpt-inf, Doggystyie].
+                                               # X-MoneyForWhiskas hedge 0.5-1x.
- tilt.max_ratio: 4.0
+ tilt.max_ratio: 3.0                           # Doggystyie tilt tiers 1.5x/2x/3x
- sizing.clip_usdc: "min(10, 0.2% bankroll)"
+ sizing.clip_usdc: "15-30 uniform"             # Doggystyie base $30/side. Uniform clips.
+ sizing.per_market_cap_usd: 200                # Doggystyie
  paired_cost_gate.hard_stop_vwap: 1.03         # unchanged. Doggystyie: HIGH risk above 1.03.
+ expected_trading_pnl: "-0.5% to -1.0% of volume"   # Doggystyie -1.0%. Budgeted as the
+                                                   # cost of generating volume.
+ kill_switches_add:
+   - reward_to_volume_7d < 1.2%                # Doggystyie pause rule
+   - any program-terms change -> halt and re-underwrite
```

---

## 4. Causal replacements for "dominant leg ≥2x", and a backtest plan

The ≥2x filter is computed from *final* capital ratios, which exist only after the bot has finished reacting to the window. Using it as a live rule is look-ahead.

| Replacement (causal at decision time t) | Source | How to use |
|---|---|---|
| **Spot fair-probability gap**, p_up(spot_t, open, secs_left, σ) − CLOB mid_t | PBot-6 (0.03 / 0.08), 0x04b6d7 (3/6/10/15%), 080BEc (≥5% → up to 5x), Bonereaper Jun (>0.3% move, conviction tiers) | Primary tilt driver (spec tiers) |
| **Elapsed time × move size**, e.g. \|spot/open − 1\| scaled by √(secs_left) | Gabigol proxies (time elapsed, spot trend); Bonereaper Jun, Ratue (late loading) | A gap means more late in the window. Already embedded in p_up. Test it as a separate feature. |
| **Orderbook imbalance**, depth ratio at the top N levels of Up and Down | Gabigol, Ratue [rpt-inf] | Secondary confirm. Do not tilt on imbalance alone [judgment]. |
| **Market-price follow**, mid_t ≥ 0.85 on one side | Gabigol proxy | Baseline to beat. If it matches the model, keep the simpler rule. |
| **Realized-vol regime**, 5-min vol vs trailing 60-min | BTC5MScour, PBot-6 | Scales σ. Possibly gates tilt off in very low vol (FlippingSharks low-vol fade [rpt-inf]). |

Acceptance for a proxy: decisions made at t using only data up to t must reproduce at least **50% of the retrospective ≥2x lift**, measured as the tilt residual in $, with the steep shape intact (3x+ bucket WR ≥ 85% when bucketed by *intended* ratio) **[judgment]**. The persona's warning applies here: "That +22% filter is retrospective. Here is the causal version, and it returns 4%." Expect most of the lift to disappear.

### Backtest plan

**Data needed:**
- Full-depth L2 snapshots and diffs for both outcome tokens of each target slug, plus market-creation and resolution events.
- The resolution reference price per window (Chainlink per the catalogue), aligned with Coinbase and Binance spot ticks at sub-second resolution.
- Per-window open prices, defined exactly as the market resolves.
- Ideally the trade history of one or more reference wallets (080BEc, X-MoneyForWhiskas) to validate the fill simulation against their paired-cost distributions.
- At least 60 days, covering at least one low-vol week (Bonereaper's June 1–7 was red) **[judgment]**.

**Fill model:**
- Taker fills only, walking the book at clip size, with a queue-position haircut **[judgment]**.
- Exclude incentive income entirely in the base run.

**Latency scenarios:**
- 0 ms (upper bound).
- 200 ms (0x04b6d7: "about 200 ms could make it break even or lose").
- 500 ms (Gabigol target).
- 1 s (X-MoneyForWhiskas).
- 2 s (080BEc and FlippingSharks tolerance).
- Report P&L at each. Second-leg lag scenarios: 5, 10 and 30 s, with the unpaired leg flattened at 30 s.

**Splits:**
- Walk-forward, training tiers on weeks 1–4 and testing on later weeks.
- Report the spread, tilt residual and hedge tax separately.
- Report the dominance curve by *intended* ratio, and hour and day tables. Use them for monitoring only, not as filters.
- Stress: the single worst session removed and duplicated (PBot-6 May 18, 0x04b6d7 May 1, BTC5MScour June 21).

**Acceptance criteria [judgment, anchored to the reports]:**
1. At 500 ms latency, trading ROI ≥ +0.5% of notional. That is a floor below the 0.72–1.59% non-incentive cluster.
2. The tilt residual is positive in ≥70% of rolling 7-day windows (persona success metric).
3. Simulated median paired cost on executed pairs is ≤ $0.985, and ≥45% of pairs are below $1.00 (FlippingSharks and X-MoneyForWhiskas alarm lines).
4. The intended-3x+ WR is ≥ 85% and the intended-1–1.5x bucket is not worse than break-even.
5. P&L does not depend on one session: no single day contributes more than 30% of the total.
6. The result is still positive at 1 s latency. If not, the margin is too thin for retail infrastructure.

After that: shadow for 2 weeks, then a 1% scale pilot, with the live paired cost within ±0.5¢ of the backtest median.

---

## 5. Kill switches and weekly health checklist

**Hard kill switches.** Halt new entries; no overrides.

| Trigger | Threshold | Evidence |
|---|---|---|
| Median paired cost (3-day) | > $0.995 | 080BEc and NeverSmiling playbooks |
| Executed VWAP pair | > $1.03 on any market → stop adds there | Doggystyie, Bonereaper Apr |
| 3x+ dominant WR (3-day, intended ratio) | < 70% | Gabigol (pause <70% for 3 d), 080BEc, persona Rule 4 |
| Hedge-tax break-even | 3x+ WR < 65% for 7 d → stop the strategy | ohanism (unprofitable below 65%), Ratue (<70% for 7 d → revert to equal sizing) |
| Rolling 7-day trading P&L | 3 consecutive negative windows | 080BEc playbook |
| Daily loss | ≥ 5% of bankroll | [judgment]; 0x04b6d7's 12% is the outer bound |
| Feed or CLOB outage | spot or CLOB stale > 30 s, or spot latency > 2 s | FlippingSharks, Doggystyie (30 s), BTC5MScour (2 s) |
| Unpaired legs | > 2% of markets one-sided in a day | X-MoneyForWhiskas treats 2.4% one-sided as operational failure [judgment threshold] |
| Incentive mode only | 7-day reward/volume < 1.2%, or any change to program terms | Doggystyie |

**Size-down rather than kill.** The persona says to cut size before you cut the strategy. Halve size if:
- the share of pairs below $1.00 drops below 40% (FlippingSharks alarm), or
- the 3x+ WR drifts below 85%.

Treat a share below 30% as "competed away" and stop.

**Weekly checklist (tuned to the evidence):**
- [ ] Share of paired markets below $1.00: 45–55% (FlippingSharks, X-MoneyForWhiskas). Alarm below 40%.
- [ ] Median paired cost trend over 4 weeks is flat or falling. A rise is the leading decay signal (Bonereaper Apr→Jun: $1.006→$1.016).
- [ ] 3x+ WR by intended ratio is 85–97%, and the 1–1.5x bucket is not the largest loss source (it was the only losing bucket for Bonereaper Apr).
- [ ] Median second-leg lag is 5–12 s. Both-sides rate is 96–99%. A falling rate is a warning sign: Bonereaper went 96.7%→89.2% as its ROI decayed.
- [ ] Spread, tilt residual and hedge tax as a share of notional are reported separately. The hedge tax was 17–42% of notional across these books by my computation **[inf]**. Watch for drift.
- [ ] No single session is above 30% of weekly P&L. Check against NeverSmiling (about 70% of profit from one week) and 0x04b6d7 (72% from Wednesdays).
- [ ] Coverage: markets per day are within ±15% of the plan **[judgment]**.
- [ ] Incentive income appears on its own line and is never in the go/no-go for the base variant.
- [ ] Spot-vs-resolution price alignment is spot-checked on 10 random windows.

---

## 6. Expected economics

**Trading-only ranges from the reports** (hold-to-settle, both-sides ≥88%, incentives excluded):

| Book | Trading ROI | Window |
|---|---|---|
| FlippingSharks | +0.30% | 12 d |
| Bonereaper Jun | +0.20% | 45 d |
| 0x04b6d7 | +0.72% | 20 d |
| VidarX | +0.87% | 32 d |
| sixx7 | +0.87% | 21 d |
| X-MoneyForWhiskas | +0.94% | 26 d |
| 080BEc | +1.46% | 29 d |
| Bonereaper Apr | +1.53% | 22 d |
| Ratue | +1.92% | 28 d |
| Doggystyie | −1.0% | 29 d |

Lower both-sides books (PBot-6 4.71%, Gabigol 2.09%) are higher, but PBot-6's result came from 14 days and depended on the May 18 session.

My central planning case **[inf]**: about 0.3–1.0% of buy notional before slippage from my own latency, with a realistic probability of breakeven or worse after the Section 4 latency haircuts. NeverSmiling's report already says its thin ROI "likely compresses toward zero" for smaller operators.

**What that means in dollars** **[inf, arithmetic]**: one wallet with a $25K bankroll turning over about $60–120K a day (NeverSmiling about $64K a day; Doggystyie about $120K a day) at 0.5% would make about $300–600 a day. That is in line with FlippingSharks' checklist band of +$150–600 a day. Hedge tax runs into the millions on these books (Bonereaper Jun $7.65M), so a 2–3 point drop in 3x+ WR can erase the margin.

**Incentives.** Never forecast them. These are reported facts, not projections:
- Doggystyie: rewards were 2.69% of volume.
- X-MoneyForWhiskas: taker rebates of $37.6K on $4.13M, about 0.9% of notional by my arithmetic **[inf]**.
- Bonereaper Jun: rewards were about 80% of income.
- Gabigol: rewards were 18% of its total.

All of these reports rate a program change as a critical or high risk, and Doggystyie says there is "no mitigation".

**Capacity:**
- BTC 5m spread books: about $25–50K per wallet (FlippingSharks).
- SOL/XRP: about $25K per wallet (NeverSmiling).
- Multi-asset: degrades above about $250K and needs fragmentation above about $500K (Gabigol, X-MoneyForWhiskas).

Fragmentation must not violate platform rules on wash trading or self-dealing.

**Decay risks, ranked [inf]:**
1. Competition compressing paired cost toward $1.00. This is already visible in Bonereaper (1.53%→0.20%), 080BEc (rolling 7-day going negative) and FlippingSharks' late fade.
2. Latency disadvantage against incumbent bots (0x04b6d7's 200 ms warning).
3. Signal decay in the tilt, which is where all the money is.
4. Low-vol regimes.
5. Correlated wrong-way moves across BTC, ETH and SOL in the same window (Ratue, Gabigol).
6. Changes to the market series or incentive programs.

**Data caveats.** The windows are short (12–45 days), and the reports contain internal inconsistencies: duplicate wallets (080BEc and B1C58), P&L that disagrees with Polymarket's, and hour lists that differ between tables and prose. Unexplained amounts are material, such as X-MoneyForWhiskas' $51.9K. Treat every number as one reconstruction, not a durable edge.

**Bottom line:** the base variant is worth a backtest and a 1% pilot, not capital. If the causal tilt does not reproduce at least half the retrospective lift at 500 ms, what you have is a hedge-tax machine, and you should walk away. Run the incentive variant only once a confirmed reward rate of at least 1.5% is in writing.

*Not financial advice. Check prediction-market legality in your jurisdiction and your account's terms before trading.*
