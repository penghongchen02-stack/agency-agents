# Crypto Up/Down: Latency and Late-Window Playbook Review

*Tick (Crypto Up/Down Latency & Late-Window Strategist). This applies the agent's rules to SIRMARTINGALE, BTC5MScour, SLIP-ME, LIL222, the crypto leg of Sharky6999, and the late-window loading seen in Bonereaper (June update) and Ratue.*

> **Not financial advice.** Before doing anything else, confirm that trading Polymarket prediction markets is legal where you live and that your account is allowed to use them. Everything below comes from the PR&R reports and their dossiers. Tags: **[report inference]** means the report itself hedges the claim. **[inference]** is my own derivation or a threshold I am proposing. **[discrepancy]** marks a report that contradicts itself. No report mentions maker/taker status or Chainlink. The catalogue glossary says the markets settle on a Chainlink price.

The rule that governs everything here is to set the latency budget before choosing a strategy. If your p99 is longer than the stale window, the mode is off, however good the backtest looks.

---

## 1. Per-bot breakdown

| Bot | Mode | Entry trigger | Exit / holding time | Latency (stated / implied) | Edge per share / ROI | Key failure mode | What can't be copied (per report) |
|---|---|---|---|---|---|---|---|
| **SIRMARTINGALE** (Apr 1–28) | Spot-to-CLOB latency capture (C + B) | A Coinbase/Binance/Kraken spot move; the CLOB requotes 1–30 s later ("often 5 to 30 seconds"). Buys the side priced under fair value and averages down ($10→$12→$17), never doubling. | Sells into the requote within about 15–60 s and holds the residual to settlement. About 60–90 s per market. SELL/BUY is 1.32× on BTC 5m and 2.59× on ETH 5m. | Stated: a residential connection on the public REST API "loses the race". The report infers colocation or a private high-priority WebSocket. Median inter-fill gap 0.0 s; same-second fan-out. | Average buy about $0.43, average sell about $0.80, so roughly $0.37 gross per sold share **[inference]**. Cash-flow ROI +82.95% (+$119,586). The resolved-BUY view is +37.47% (+$54,020) **[discrepancy]**. About 61% of the alpha comes from exits. | A persistent move against the entry with no rally to sell into. Worst market −$404 ($569 in, BTC Apr 24). | "The latency. We tried." |
| **BTC5MScour** (Jun 10–Jul 6) | Near-certainty sweep (C) with episodic deep value | BTC spot clearly past the reference late in the window. Buys only that side and walks asks from $0.96–$0.97 to $0.99. The spec says the final 60–120 s, but fills skew to $0.99 with 2–3 min left **[discrepancy]**. | Holds to settlement (2 SELLs). The worked example is about 50 s of fills starting about 40 s before close. | Stated: "if spot feed latency > 2 seconds, halt all entries". Stale offers in the final 30 s "disappear quickly"; winning those races is "non-trivial". Median gap 1.0 s. | The report's EV is about +$0.023/share at $0.97 (99.3% realized vs about 97% implied). The $0.90–$1.00 band realized +1.26% (+$18,543 on $1.47M). Total +1.77%. | Spot-feed outage (rated High), a last-second reversal, and competition for stale offers. | The June 21 deep-value returns (signal unknown) and the race for stale offers in the last 30 s. |
| **SLIP-ME** (Apr 5–27) | Reactive late load wearing a both-sides "MM costume" (B + C) | Opens both legs at the open, trend-follows the tape and book in minutes 1–4, then loads the leader in the final 90 s (e.g. $0.92/$0.93/$0.95 with 72 s left). | Never sells; holds everything to resolution. | Implied: a polling loop of about 1 s, "medium-frequency, not HFT", no colocation **[report inference]**. The same report also says "infrastructure-bound… a colocated host" **[discrepancy]**. Median same-outcome gap 2.0 s. | +2.59% ROI overall. The spread leg lost −$97,523 and the directional leg made +$204,450. A late $0.95 load carries 5¢ gross. Gating underdog buys at ≥2× skew gives +12.69%. | Choppy, trendless BTC (the spread bleeds while the directional leg never fires) and paired cost ≥ $1.05. | Its capital and scale ($50K would make about $1,300 in 23 days), always-on infrastructure, and copy-trading the wallet (the depth is gone by the time you see the fill). |
| **LIL222** (Apr 5–29) | Penny-floor harvester | A $0.01 ask appears 5–180 s before close. Buys at exactly $0.01 (100% of BUYs). | Offers at $0.02 about 8 s later (98.55% of SELLs) and holds the rest as 99× lottery tickets. | Stated: "<500ms RPC round-trip", co-located or a low-latency RPC. "Every additional gating rule… adds latency." | The report's EV is about $0.0252 per $0.01 ticket. Cash-flow +56.22% ($6,267 on $11,146). The SELL engine made only +$563; settlement made +$5,661 from 296 wins. | Competition. The report says the edge "dies when other bots compete". Depth limits it to about $25/market and a bankroll of about $50–75K. | Scale (about $250/day). The header section describes a different trader **[discrepancy]**. |
| **Sharky6999** (crypto leg, Apr 1–May 1) | Favorite buying | About 97% of resolved BUYs are in $0.90–$1.00. The report gives no mechanism. | Mostly holds; 10.3% of trades are sells, worth only $389K. | Conditional: co-located RPC is needed only "if sub-second for a meaningful share" of fills. 0% of gaps are under 1 s and 89.4% are under 10 s. | +0.29% overall (+$59,615 on $20.74M). The $0.90–1 band is +0.24%. The crypto vertical is +0.43% (+$29,845). | Tail losses on $0.9x entries in BTC/ETH 5m. "No filter helps." | The off-platform signal and any latency edge. |
| **Bonereaper June / Ratue** (late-load component) | Late-window loading inside a both-sides book | Bonereaper's biggest adds come in the final 90 s at $0.89–$0.95; the playbook says $0.85–$0.97 in the final 60 s. Ratue loads the leader at $0.88–$0.89 in minutes 12–14 of 15m markets. | Both hold to settlement (0 SELLs). | Bonereaper: "colocated or near-colocated", a VPS in AWS us-east-1, persistent WebSockets. Ratue: under 2 s. | Bonereaper's $0.90–1 band made +$125,262 on $27.03M, about +0.46% **[inference]**. Trading ROI was only +0.20%; 80% of account P/L came from rewards. Ratue was +1.92%. Its ≥2× dominant-leg filter shows +12.51% (after the fact). | Bonereaper: rewards-program change, low-volatility weeks, and a 12.4% loss rate in the 3×+ bucket. Ratue: correlated BTC/ETH/SOL adverse moves. | Bonereaper: the rewards and colocated infrastructure. Ratue: the volume and the undisclosed signal. |

---

## 2. Latency-feasibility matrix

Infra tiers: **T1** is residential plus REST. **T2** is a VPS near the venue (the Bonereaper report names us-east-1) with persistent CLOB and spot WebSockets and redundant RPC. **T3** is colocated or private high-priority access. The p99 figures are the budgets I am proposing **[inference]**, anchored to the report evidence in the last column.

| Mode | Required end-to-end p99 (spot tick → CLOB ack) | Tier | Can a well-equipped independent compete? | Evidence |
|---|---|---|---|---|
| Latency capture (SIRMARTINGALE) | Under the short tail of a 1–30 s stale window, realistically ≤250–500 ms **[inference]**, plus a sell engine | T3 | **No.** On REST you lose most races. On T2 you win only the long, slow windows, which are the adversely selected ones. | "Residential… public REST API loses the race more often than not"; median gap 0.0 s; colocation inferred. |
| Near-certainty sweep, final 30 s (BTC5MScour) | ≤500 ms **[inference]** | T3 | **No.** | "Stale offer windows in a market's final 30 seconds disappear quickly"; infrastructure is "non-trivial". |
| Near-certainty sweep, 60–120 s band | ≤1 s; halt if a spot tick is >2 s old | T2 | **Conditionally yes, pending measurement.** | The report's own rule is "halt if spot latency > 2 s"; median fill gap 1.0 s; fills at $0.97 with 4+ min left show the race isn't always at the last second. |
| Reactive late load, dominant leg only (SLIP-ME / Bonereaper / Ratue) | About 1–2 s | T2 | **Yes, technically.** The edge is reading skew, not winning a race. Capital and scale cap the payoff. | SLIP-ME has a 1-s loop with no colocation **[report inference]**; Ratue states under 2 s; Bonereaper says "polling is insufficient for 2-second fill cycles". |
| Penny floor (LIL222) | <500 ms RPC round-trip (stated) | T2+/T3 | **Technically maybe. Economically no.** | The stated requirement; "dies when other bots compete"; about $250/day ceiling. |
| Favorite buying (Sharky6999 crypto) | Unknown; 0% of gaps are under 1 s | T2 | **No.** The edge is unexplained, so there is nothing to build. | The report names no mechanism and says "no filter helps". |

Rule check: win rate ≈ the share of stale windows longer than your p99. Measure both before committing to any mode (§4).

---

## 3. Playbooks for the two most feasible modes

### Playbook A: Near-certainty sweep, 60–120 s band (BTC5MScour-derived)

**Why it's feasible:** it doesn't need a prediction model. The 2-s staleness rule is achievable on T2. Weekly KPIs come straight from the report, so drift is easy to see.

**Universe:** `btc-updown-5m-*` only, 24/7. Add ETH 5m only after a separate measurement pass **[inference]**.

**Inputs:** at least two independent BTC spot WebSockets (Coinbase, Binance or Kraken, the exchanges named in the SIRMARTINGALE report), the CLOB L2 WebSocket, each market's reference/open price, and a model of the Chainlink settlement price (see §4).

**Entry:**
1. With 120 s or less to the close, compute the spot distance from the window open on the averaged fresh feeds.
2. Skip if spot is within 0.05% of the open (the report's rule).
3. Skip if fewer than two feeds have a tick ≤2 s old, or if the feeds diverge by more than 5 bps (the agent's `StaleQuoteDetector` defaults).
4. Buy only the settled side. Walk asks from $0.96 to $0.99, capping each fill at the clip. Skip anything in $0.40–$0.90 (the report's recommended exclusion: −$473, −5.5%).
5. Don't chase the final 30 s **[inference]**. Your T2 stack loses those races, and the fills you do win there are adversely selected.

**Exit:** hold to settlement. Never trade after the close. LIL222 bought 14 s post-close and SLIP-ME's 2,936 post-close fills lost −$528. Trading in the gap before the oracle fires is too close to exploiting settlement mechanics (Rule 6).

**Unit economics:** at a $0.975 average entry, break-even WR is 97.5%. The report realized 99.3% in the band. Each wrong-side market costs about 57× the average market profit ($546 average deployed vs +$9.58 average P/L) **[inference]**.

```yaml
near_certainty_sweep:
  universe: ["btc-updown-5m-*"]
  entry_window_secs_left: [30, 120]           # inference: cede final 30 s to T3 bots
  entry_price_band: [0.96, 0.99]
  skip_price_band: [0.40, 0.90]               # report-recommended
  skip_if_spot_within_pct_of_open: 0.05
  min_fresh_feeds: 2
  max_tick_age_s: 2.0                          # report hard rule
  max_feed_divergence_bps: 5
  clip: "0.3% bankroll (max 1.5%)"            # $10k -> $30-65/fill, $250 hard max
  per_market_cap: "5% bankroll"               # report: $1,200/market at $10k
  per_market_max_loss_usdc: 1200               # within report's $500-1,500
  halt_if_avg_entry_above: 0.985               # competition eating the edge
  reduce_clip_if_avg_entry_below: 0.962        # depth exhausted
  pause_after_losses: {count: 3, window_min: 30, pause_min: 30}
  daily_stop_usdc: -3000
  post_close_trading: false
  feed_outage: {halt_entries: true, max_recovery_min: 5}
  weekly_kpis: {markets_per_day: [80, 130], capital_in_band_pct: [97, 99],
                band_wr_pct: [98.5, 99.5], pnl_per_market_usdc: [5, 20]}
  deep_value_mode: disabled                    # June 21 signal unknown; see section 5
```

### Playbook B: Reactive late load, dominant leg only (SLIP-ME / Bonereaper / Ratue-derived)

**Why it's feasible:** every report in this family shows a monotonic dominance curve (SLIP-ME: 95.6% at 2–3×, 99.0% at 3–5×, 99.8% at ≥5×). The only speed it needs is a 1–2 s loop. Skipping the hedge leg removes the spread drag that cost SLIP-ME −$97.5K.

**Caveat:** the ≥2× dominant-leg results (SLIP-ME +12.69%, Ratue +12.51%, Bonereaper +0.73%) are computed after the fact on *final* dominance. A live version has to use dominance at decision time (around minute 4, or minute 12–14 for 15m), which will be weaker **[inference]**. Treat those ROIs as an upper bound, never a target.

**Universe:** `btc-updown-5m-*` first. Optionally `btc/eth-updown-15m-*` for Ratue-style minute-12–14 loads, which give a longer decision horizon and more tolerance of latency **[inference]**.

**Entry:**
1. From minute 4 (5m markets) or minute 12 (15m markets), compute the live leader from book skew: best-ask ratio and depth. SLIP-ME: "the signal is in the book."
2. Check that spot direction relative to the open agrees with the book, using the two-feed rule. If book and spot disagree, skip.
3. Load only the leader at $0.85–$0.97 (the Bonereaper playbook band), scaled up with live skew.
4. Never buy the underdog once skew is ≥2×. Buy no hedges at all: you are not farming rewards. At your volume the rewards are "negligible" (under $1M/month).

**Exit:** hold to settlement. Never sell. Bonereaper and Ratue both warn that adding a sell leg brings in latency and partial-fill risk.

```yaml
reactive_late_load:
  universe: ["btc-updown-5m-*"]                # optional: btc/eth-updown-15m-*
  decision_time: {m5_secs_left: [15, 90], m15_secs_left: [60, 180]}
  min_live_skew: 2.0                           # live, not final, dominance
  require_spot_agrees_with_book: true
  entry_price_band: [0.85, 0.97]
  underdog_buys: false
  clip: "min($50, 0.5% bankroll)"              # inference; between report clips
  per_market_cap: "1% bankroll"                # Bonereaper playbook
  max_open_exposure: "15% bankroll"            # inference; ~5 concurrent mkts (SLIP-ME)
  per_market_max_loss_usdc: 600                # ~SLIP-ME worst market -$614
  pause_after_losses: {count: 3, window_min: 30, pause_min: 30}
  chop_gate: {skip_if_5m_realized_vol_below: "0.5x trailing 60m", enabled: true}  # inference
  daily_stop_usdc: -1500
  post_close_trading: false
  feed_outage: {halt_entries: true, max_tick_age_s: 2.0}
  retire_if: {live_skew2x_wr_7d_below_pct: 90}   # inference; Ratue reverts at 3x+ WR <70%
```

### Do-not-attempt verdicts

- **Latency capture (SIRMARTINGALE): do not attempt.** The report's own authors tried and lost on REST. You need T3 to win the short windows. On T2 you'd win the slow windows, and those are where the move persists against you with no rally to sell into (the −$404 failure mode). Its best market, ETH 5m, has only about $580/day of capacity.
- **Final-30-s sweeping: do not attempt.** The report itself says the race is lost without "non-trivial" infrastructure.
- **Penny floor (LIL222): do not attempt as a business.** The report puts the ceiling at about $250/day and $25/market, and the <500 ms requirement is stated. The edge depends on being the only bot or close to it. 90% of P&L (+$5,661 of $6,267) came from 296 lottery wins, a small sample. At most run it as a $5/market measurement probe, and only to learn whether competitors are on the floor.
- **Favorite buying (Sharky6999): do not attempt.** The report gives no mechanism. "No filter helps". The economics are +0.24% on the band, and a single 0.25-point drop in WR wipes that out (§5).
- **Deep-value / June 21-style entries: do not attempt.** The report can't explain the signal ("either got lucky, or it has a secondary signal").

---

## 4. Measurement plan (1–2 weeks, zero capital)

**Record (timestamps synced to a common clock):**
1. Spot ticks from Coinbase, Binance and Kraken for BTC (and ETH if you are considering it), with exchange timestamps and local receive timestamps.
2. Every CLOB L2 update for each active `btc-updown-5m-*` market (and 15m if you plan Playbook B on 15m).
3. Each market's open/reference price and its resolved outcome. Where you can source it, the Chainlink reference price at close.
4. Your own round trip, measured with a non-marketable or minimum-size test order: signed order → ack, at p50 and p99, by hour.
5. Third-party fills in the $0.96–$0.99 and $0.85–$0.97 bands, with time-to-close.

**Metrics and acceptance thresholds** (every threshold is **[inference]** unless the report is cited):

| Metric | Definition | Accept if | Rationale / source |
|---|---|---|---|
| Stale-window distribution | Time from a ≥X bp spot move to the CLOB mid moving ≥Y ticks, by asset, hour and seconds-to-close | Median stale window in the 30–120 s band is > 2× your p99 | Rule 1. SIRMARTINGALE cites 1–30 s, "often 5 to 30". |
| Own latency | Spot receive → CLOB ack | p99 ≤ 1 s (A) or ≤ 2 s (B). Zero orders sent with a tick older than 2 s | BTC5MScour's 2-s halt; Ratue's under 2 s |
| Settlement basis | Sign agreement between the averaged spot-vs-open and the settled outcome, for windows where \|spot−open\| > 0.05% at T−60 s | ≥ 99.5% agreement (needed to clear a 97.5% break-even with margin) | Report band WR is 99.3%; the 0.05% skip rule |
| Basis magnitude | \|spot avg − Chainlink\| at close, in bps | p99 below the 0.05% skip threshold (5 bps). If not, widen the skip | Rule 3; catalogue says Chainlink settles |
| Opportunity count | Markets per day with ≥$100 of asks at ≤$0.97 on the settled side in the 30–120 s band | ≥ 80/day | Report KPI of 80–130 markets/day |
| Competitor drift | Rolling 3-day volume-weighted price of third-party fills in $0.96–$0.99 | Stays < $0.985. Halt the mode if above. Below $0.962 means depth is exhausted | Report alarms |
| Fill race | Share of qualifying asks still resting after your p99 delay | ≥ 50% | Win rate ≈ share of windows longer than p99 |
| Live-skew calibration (B) | WR of the side leading at ≥2× live skew at T−90 s | ≥ 95% (5m) | SLIP-ME 2–3× final = 95.6% |
| Feed health | Share of minutes with <2 fresh feeds or >5 bp divergence | < 1% of minutes | Rule 2 |

**Go / no-go:** the replay simulation with your measured latency injected must show realized edge ≥ 1¢/share after slippage in both weeks separately. Then pilot at 10% of the YAML clip and require realized edge ≥ 70% of simulated (agent success metric).

---

## 5. Tail-risk analysis

### Sharky6999: 98.9% WR, +0.29% ROI
- **Margin:** the $0.90–$1.00 band ran at 99.4% WR and +0.24% ROI. That implies an average entry around $0.99, so break-even WR is about 99.2% **[inference: 0.994 / 1.0024]**. A **0.25-point drop in band WR erases the whole book's edge**.
- **Loss multiple:** at a $0.99 entry, one loss erases about 99 wins. At $0.97 it erases 32.
- **Concentration:** the five worst markets (−$3,942, −$3,481, −$3,141, −$2,898, −$2,585) total **−$16,047**. That is 27% of total P&L (+$59,615) and **54% of crypto-vertical P&L** (+$29,845) **[inference: arithmetic]**. All five are BTC/ETH 5m Up/Down windows.
- **Size skew:** the top 5% of fills carry 94% of capital (P99 $3,302, max $431,971). A single wrong-side large fill can exceed a week's P&L. Week 4 made only +$3.1K.
- **Hours:** WR fell to 72.4% at 08 UTC and 89.7% at 19 UTC. 09 UTC lost −$3,222. Excluding those hours still costs −$6.9K, so the tail can't be scheduled away.
- **Lesson:** "100% of rolling windows green" over 31 days says nothing about a tail that fires about 1 in 87 resolved buys (640 / 55,783).

### BTC5MScour: the June 21 cluster
- About 9 markets between 2:25 and 3:40 AM ET produced **more than +$13,000, about 49% of the +$26,520 total**. The single best market (+$9,523 on $1,464, 285 trades) is **36%**.
- The same 75 minutes also held the worst market (−$2,460) and more losers (−$1,932, −$924, −$852), **−$6,168 combined** **[inference: sum]**. The cluster was a high-variance regime, not free money.
- Its footprint distorts every filter. The 06 UTC +$10,440 and 07 UTC −$3,316 hours, the "dom ≥2×" result and the Sunday +4.12% ROI are all June 21 artifacts.
- **Clean baseline:** W27 (+$5,533, 99.3% WR) is the honest run rate for the core sweep, at roughly $790/day **[inference]**. W25, the anomaly week, ran at 89.9% WR. That is *below* the 97% break-even for $0.97 entries, so outside the cluster that week's sweep was fragile.
- **Realized vs model:** the report expected about $35,200 against $26,291 realized (−25%). Budget for live results to come in under the report's EV.

### LIL222: competition decay
- The EV of about $0.0252 per ticket rests on two branches: a 56% bounce fill at $0.02 and about 1.4% of shares paying $1. The bounce leg made only +$563. **The book is essentially a 296-win lottery** (+$5,661).
- **Decay mechanics (from the report):** if a rival posts at $0.02 ahead of you, your chance of filling at $0.03 drops "from ~50% to <10%". The report's alarms are markets/day under 80 (the reference wallet did 140), bounce fill under 50%, and $0.02 SELL share under 95%.
- **Quantified [inference]:** with N equally fast bots splitting the floor, your fills and dollar P&L scale by about 1/N, so two bots means about $125/day. Below about 50% bounce fill, the sell branch adds almost nothing, and variance from a small lottery sample dominates: 296 wins in 25 days is about 12 per day.
- The report says the reference wallet's 56% in late April means either the market is too small for serious competition or 3–4 bots can coexist. Either way the ceiling is about $250/day for one bot.

### SLIP-ME: choppy sessions
- **Structural drag:** paired cost averages $1.0183. Across 3.74M paired shares that cost −$97,523, about −$4,430 per active day **[inference: ÷22]**, paid whether or not BTC trends.
- **Offset at risk:** the directional leg averaged +$8,890/day. In chop, final skew stays in the 1.0–1.5× bucket, where the dominant-side WR is only **67.1%** (vs 95.6%+ at ≥2×), so the offset shrinks while the drag stays.
- **Observed damage:** one losing day (Apr 12, −$2,898), worst market −$614, and markets with paired cost ≥$1.10 at −5.33% ROI. The Apr 17–20 throttle (13,304 trades/day down to 0) suggests the operator intervened by hand **[report inference]**.
- **Implication for Playbook B:** dropping the hedge leg removes the −$4.4K/day drag entirely. What's left in chop is that late loads fire at weak skew, which is why the YAML has a 2× live-skew floor and a volatility-based chop gate.

---

## Summary verdict

| Mode | Verdict |
|---|---|
| Near-certainty sweep, 30–120 s band | **Measure, then pilot** (Playbook A) |
| Reactive late load, dominant only | **Measure, then pilot** (Playbook B) |
| Latency capture, final-30-s sweep | **Do not attempt** (T3 only) |
| Penny floor | **Do not attempt** (probe only) |
| Favorite buying, deep value | **Do not attempt** (no mechanism; tail dominates) |

*Windows in these reports are 23–45 days. One session can dominate a report (June 21), and every after-the-fact filter overstates what you'll get live. This is not financial advice. Confirm that prediction markets are legal for you first.*
