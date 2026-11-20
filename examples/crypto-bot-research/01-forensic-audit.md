# Forensic Audit: 21 PR&R Crypto-Bot Reports

**Analyst:** Ledger (Prediction Market Wallet Forensics Analyst)
**Inputs:** the PR&R crypto catalogue, dossier notes A–D, and raw report extracts. All figures come from those inputs. Anything I derived is marked "derived". Anything I infer is marked [inference].
**Regime:** every window falls between 2026-03-15 and 2026-08-26. Windows are 12–45 days long (SLIP-ME's is 22 active days). Ten of the windows overlap in April 2026.
**Not financial advice.** These are reconstructions of short historical windows. Prediction markets can be restricted in some jurisdictions, so readers must check their own eligibility. Nothing here is a copy-trade signal: mirroring a sub-second bot on-chain arrives after the depth is gone.

**Headline.** The 21 reports cover **19 unique wallets, not 20.** 080BEc and B1C58 are one address (`0x60889af5…bec32f361`). Bonereaper's April report and its June update are also one address (`0xeebde7a0…6eba30`). Five wallets report a negative spread leg: FlippingSharks, Bonereaper-Jun, Doggystyie, SLIP-ME and ohanism. In those books, the tilt pays for everything. Three of the large account P&L numbers are mostly policy income: Bonereaper-Jun (81% rewards), Doggystyie (159% of the account P&L is rewards), and X-MoneyForWhiskas (71% non-trading). Only one wallet has a true second window: Bonereaper. That second window shows trading ROI falling from 1.53% to 0.20%.

---

## 1. Reconciliation table

How to read the columns:
- **Trading** is cash-flow P&L, `−buys + sells + payout`, as the report computes it.
- **Platform** is the Polymarket-reported figure, where the report gives one.
- **Gap** is Platform minus Trading.
- **Incentive** is rebates and rewards.
- **Spread conv.** is the convention the report used for spread P/L. "net" means all paired markets are counted, above-$1 included. "sub-$1" means only profitable pairs are counted, so it is an upper bound. "unst." means the report does not say.
- **Dir. residual** is Trading − Spread P/L. "R" means the report states it; otherwise I derived it.
- "n/r" means not reported. "n/a" means not applicable.

| # | Report | Days | Trading | Platform | Gap | Incentive | Spread P/L (conv.) | Hedge tax | Dir. residual |
|---|---|---|---|---|---|---|---|---|---|
| 1 | FlippingSharks | 12 | +$4,121 | +$17,755 | **+$13,634 unexplained** | n/r | −$1,869 (net) | $497,333 | +$5,990 R |
| 2 | Bonereaper Apr | 22 | +$443,754 | n/r | n/r | n/r (not discussed) | n/r | $5,001,226 | n/r |
| 3 | Bonereaper Jun | 45 (44) | +$88,606 | +$458,493 | +$369,887 | $369,887 rewards/other | −$685,278 (net) | $7.65M | +$773,884 derived |
| 4 | BTC5MScour | 27 (26) | +$26,291 | +$26,520 | +$230 | $230 rewards/other | n/a (0.26% both-sides) | n/a | n/a. Core $0.90+ band +$18,543. Jun-21 cluster >+$13K |
| 5 | Doggystyie | 29 (28) | **−$34,877** | +$58,792 | +$93,668 | $93,668 LP rewards | −$40,705 (net) | $1.34M | +$5,828 R |
| 6 | Gabigol | 34 | +$30,190 | +$36,798 | +$6,608 | $6,608 LP/other | +$34,785 (sub-$1, upper bound) | $199,748 | **−$4,595 derived (lower bound)** |
| 7 | NeverSmiling | 16 | +$4,337 | +$20,977 | **+$16,640** ("likely" open positions) | n/r | +$160 (unst.) | $369,270 | +$4,177 derived |
| 8 | PBot-6 | 14 | +$23,564 | n/r | n/r | n/r | +$1,030 (net per prose) | $205,399 | +$22,534 derived |
| 9 | X-MoneyForWhiskas | 26 | +$38,776 (tables $38,466) | +$134,180 | +$95,404 | $37,619 taker + $5,255 maker + $594 LP, plus **$51,936 unexplained** | +$33,114 (unst.) | $1,743,422 | +$5,662 R |
| 10 | VidarX | 32 | +$103,949 (crypto +$125,538) | n/r | n/r | n/r | +$58,509 (unst.) | $4.74M | +$45,440 derived (crypto +$67,029) |
| 11 | sixx7 | 21 | +$19,190 (tables $16,663) | n/r | internal $2,527 | n/r | +$42,894 (unst.) | $845.3K | **−$23,704 derived** |
| 12 | 080BEc | 29 | +$25,483 | n/r | n/r | n/r | +$15,679 (unst.) | $672,224 | +$9,804 R |
| 13 | B1C58 (=080BEc) | 29 | +$27,984 | n/r | n/r | n/r | +$18,449 (unst.) | $676.5K | +$9,535 derived |
| 14 | 0x04b6d7 | 23 (20) | +$36,132 | n/r | n/r | n/r | +$189,723 (unst.) | $1,947,327 | R +$1,793,736 (three-way). **Derived −$153,591** |
| 15 | ohanism | 27 | +$258,687 (filter $258,554) | n/r | n/r | n/r | −$142,045 (net) | $980,261 | R ~+$1.38M (three-way). Derived +$400,732 |
| 16 | Ratue | 28 | +$18,952 | n/r | n/r | n/r | +$20,611 (unst.) | $196,870 | −$1,659 derived (report's arithmetic does not close) |
| 17 | SLIP-ME | 23 (22) | +$111,822 | n/r | n/r | "no rebates mentioned" | −$97,523 (net) | $1.20M | R +$204,450. Derived +$209,345 (**$4,895 unassigned**) |
| 18 | SIRMARTINGALE | 28 (27) | +$119,586 cash-flow. Resolved-BUY view +$54,020 | n/r | internal $65,566 | n/r | n/a (0% both-sides) | n/a | Sells +$72,735, settlement +$46,828 |
| 19 | LIL222 | 25 | +$6,267 cash-flow. Resolved view +$5,563 | n/r | internal $704 | n/r | n/a (56 pairs at $0.02 made +$4,470) | n/r | Sells +$563, settlement +$5,661 |
| 20 | Sharky6999 | 31 | +$59,615 (filter $56,475) | n/r | internal $3,140 | n/r | −$10,989 (unst.) | $12.0K | immaterial (1.03% both-sides) |
| 21 | ExitLiquidty | 41 (34) | +$330,940 cash-flow. Resolved-BUY +$185,765 | n/r | internal $145,175 | n/r | n/a | n/a | n/a (event book) |

**How the decompositions differ between reports.** 0x04b6d7 and ohanism write the result as "spread + hedge tax + directional = net". That counts the losing leg twice, because the losing paired shares already sit inside spread P/L. Every other report that states a residual (FlippingSharks, Doggystyie, X-MoneyForWhiskas, 080BEc) uses "net − spread". Under that consistent rule, 0x04b6d7's tilt is **−$153.6K**, not +$1.79M. Its "directional" story then rests on a spread figure whose convention the report never states. Gabigol's spread is explicitly sub-$1 only, so it is too high. Its derived residual (−$4.6K) is therefore a floor, not a measured loss. Treat every "unst." row as unreconciled until the spread is recomputed under one rule.

---

## 2. Archetype calls, using the Classifier

| Report | Classifier evidence | My call | Conf. | Report label | Disagree? |
|---|---|---|---|---|---|
| FlippingSharks | 98.3% both-sides, median paired $0.9996, 3x+ WR 95.8%, spread −$1.9K | A+B (directional in MM costume) | Low (12 d) | A + B skew | Emphasis only. The spread is negative, so "spread capture" is a costume |
| Bonereaper Apr | 96.7%, median $1.006, 5x+ WR 97.7%, 1.0–1.5x bucket loses | A+B | Med | fair-value MM | No |
| Bonereaper Jun | 89.2%, spread −$685K, rewards 81% of account | A+B costume + reward farmer | High | MM + liquidity farmer | No. The second window is evidence of drift |
| BTC5MScour | 0.26% both-sides, buys $0.96–0.99 late | C (near-certainty sweeper), plus an unexplained B episode | High (core) | C | No. The Jun-21 B episode is unexplained |
| Doggystyie | trading −1.0%, account +, 99.5% pairing, most uniform clips | Reward farmer | High | A reward farmer | No |
| Gabigol | 59.7% both-sides, buys sides already at $0.70–0.95, curve ~flat to 2–3x (53→61%), then 82.9% | **B** (favorite loader with longshot hedge), A minor | Med-Low | "directionally-informed MM" | **Yes.** Pairing rate too low for A primary, and the derived tilt residual is ≤ −$4.6K |
| NeverSmiling | 79.2%, spread +$160, 3x+ 78.8% | A+B, weak B | Low (16 d, $16.6K gap) | A+B | No |
| PBot-6 | 45.2% both-sides, 54.8% single-sided, fills at $0.49–0.51 | B | Med-Low (14 d) | B in MM costume | No |
| X-MoneyForWhiskas | 97.6%, median $0.9925, spread **+$33.1K**, 3x+ 92.6% | A + rebate engine, thin B | Med | spread + taker rebate engine | No. The closest to a genuine A in the set |
| VidarX | 93.3%, median $0.9917, 2x+ leg +$821K, 3x+ 84.2% | A+B | Low | "classical market maker" | **Yes.** The ≥2x leg dominates, so it is not classical MM |
| sixx7 | 99.2%, high tiers pay >$1, 3x+ 97.3% | A+B costume | Low (template report) | "classical MM" | **Yes** |
| 080BEc / B1C58 | 99.0%, median ~$0.99, spread +$15.7K, 3x+ 95.8% | A+B | Med | A + B / "classical MM" | Partly. B1C58's "classical MM" is a template label |
| 0x04b6d7 | 98.2%, median $0.968, 3x+ 92.9%, front-loads in 60–120 s | A+B; tilt sign unresolved | Low | B using A mechanics | **Partly.** The tilt is positive only under the double-counted decomposition |
| ohanism | 33.3% both-sides, 15.2% SELLs, spread −$142K | B + active exits | Med | A+B dynamic | No |
| Ratue | 88.3%, median $0.9999, loads leader in minutes 12–14, 3x+ 85.2% | **B primary**, A secondary | Med-Low | A primary | **Yes.** Spread +$20.6K is about equal to trading P&L, and 3x+ paired cost is $0.978 |
| SLIP-ME | 98.6%, median $1.018, spread −$97.5K, final-90 s loading | A+B costume, with C timing | Med-High | B+C costume | No |
| SIRMARTINGALE | 0% both-sides, SELL/BUY 1.32–2.59×, 60–90 s holds | C latency arb | Med-High | B+C | No |
| LIL222 | every BUY at $0.01, 98.55% of SELLs at $0.02 | Penny-floor harvester | High | same | No (the page header is wrong) |
| Sharky6999 | 1.03% both-sides, ~97% of capital at $0.90–1.00, 98.9% WR | Favorite buyer, C-like. Timing unverified | Low | one-sided favorite book | No. The mechanism is undocumented |
| ExitLiquidty | 73 markets, median fill $163, threshold ladders, SELL/BUY 1.37× | Event specialist (B) | Med | B event specialist | No |

---

## 3. Ranking by quality of evidence for a durable, tradeable edge

The criteria are window length, single-session dominance, incentive dependence, decay, internal contradictions, and whether the headline filter can be traded live. The rank is about evidence quality, not profit size.

1. **SIRMARTINGALE.** The mechanism shows up in the fills: buy, then sell into the requote 15–60 s later, with average buy $0.43 against average sell $0.80. 26 of 27 days are green and the worst day is −$274. No single session carries the month. The headline filter is not retrospective. Weak points: the cash-flow figure is $119.6K but the filter tables use $54.0K, and the report says capacity is tiny (ETH 5m about $580/day) and needs colocation.
2. **ohanism.** 27 days, $8.57M BUY notional, 100% of rolling windows green, best week 25% of P&L. The exits are observable SELLs. Weak points: the "max loss $280–380" claim is contradicted by a −$3,332 market, the three-way decomposition inflates the directional figure, and the ≥2x filter is retrospective.
3. **BTC5MScour (core band only).** The edge is priced in the data: 99.3% realized WR against roughly 97% implied, over 22,220 fills. W27, the cleanest week, still made +$5.5K. The Jun-21 cluster (>$13K of $26.5K) is not explained and has to be stripped out. Main risk is competition for stale asks.
4. **SLIP-ME.** 22 of 22 rolling windows green and one red day. Its "block underdog buys once skew ≥2x" filter (+12.7%) can be computed from live skew, so it is closer to causal [inference]. Against that: 23 days, operator throttling on Apr 17–18, and $4.9K of directional P&L the report never assigns.
5. **X-MoneyForWhiskas.** The spread is positive (+$33.1K) with 97.6% pairing, and no day was negative. Against that: $51.9K of account P&L is unexplained, rebates roughly equal trading P&L, and the window is 26 days.
6. **LIL222.** A one-rule mechanism with structural EV (about $0.025 per $0.01 ticket) across 296 settlement wins. Against that: $6.3K total, a ~$50–75K capacity cap, an edge that ends when competitors arrive, and a page header that describes another trader.
7. **Bonereaper.** It is the only wallet seen in two windows (67 days in total). That second window is itself the evidence that the trading edge is not durable: both-sides 96.7% → 89.2%, lag 10 s → 21 s, ROI 1.53% → 0.20%, and a −$28.6K week in W23. What stayed durable was reward income, which is policy.
8. **Gabigol.** 34 days and 6 of 6 weeks positive. Against that: the spread is overstated, the derived tilt is ≤ −$4.6K (which contradicts the "real directional alpha" claim), the $0.90+ band loses at a 96.4% WR, and the 7-day green counts disagree (32 vs 34).
9. **Ratue.** 28 days. Its spread, hedge-tax and net figures do not reconcile. W19 was −$945. Two different worst-hour lists. It calls 88.3% the "highest both-sides rate" in the series, which is false.
10. **080BEc / B1C58.** Two reports, but one wallet and a one-day offset, so they are not independent. The rolling 7-day P&L fell from +$13,096 to −$3,276 by the end of the window, which is decay.
11. **0x04b6d7.** Wednesday is 72% of P&L, a May 1 cluster lost −$6.4K, and day and window counts conflict. The tilt sign depends on the decomposition. The report itself says +200 ms of latency breaks it.
12. **PBot-6.** 14 days. The curve is flat at 49–51% until 3x, and the playbook admits dependence on the May 18 session. In its favor [inference]: dominance is set early, with the first leg near $0.50, so 57.6% WR on the ≥2x leg is less of a priced-in artifact than in late-loading books.
13. **VidarX.** Address truncated. Daily swings of −$254K to +$303K on a +$104K net with 33/33 green 15-day windows are implausible together. The odds-feed hypothesis does not fit an all-crypto book. "ISO weeks 11–14" sits next to six weekly figures. A stray crude-oil bet lost −$22K.
14. **Doggystyie.** Every hour, day, price band and rolling window loses on trading. The account is positive only while rewards stay above about 1% of volume. That is clean evidence of a reward farm and zero evidence of a trading edge.
15. **sixx7.** A template report. Two P&L figures ($19,190 vs $16,663), a derived tilt of −$23.7K against a claimed ≥2x leg of +$185K, and weaker late weeks.
16. **ExitLiquidty.** In practice the sample is one or two launches (MegaETH). Rolling 15-day P&L went from +$140.9K to −$22.2K. The ROI labels are mismatched, and execution is human-directed.
17. **NeverSmiling.** 16 days, a $16.6K platform gap, one week producing about 70% of profit, and conflicting counts (7-day green 9 vs 12; both-sides 4,034 vs 5,034).
18. **Sharky6999.** +0.29% on $20.7M with a 98.9% WR. The worst losses are 5m crypto markets, no mechanism is documented, and the filter baseline disagrees with the headline.
19. **FlippingSharks.** 12 days, the platform figure is 4.3× the computed one, the edge fades late (rolling 7-day +$5,109 → +$238), and the worked example contradicts the report's "cheaper side" claim.

---

## 4. Data-quality flags

**Identity**
- **080BEc = B1C58.** Both are `0x60889af507ec3f9da136f38b1c58080bec32f361`, on windows one day apart. Count them as one observation.
- **Bonereaper Apr and Jun** are the same wallet, `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`. That is a legitimate re-profile, not independent evidence. The Jun update's own slug is unverified.
- **VidarX** is given only as `0x2d8b…260a`, so a collision cannot be excluded. No full address in the set matches that prefix.
- **The unique-wallet count is 19**, not the 20 in the brief.
- **Mismatched labels on other pages.** Sidebar cards call Bonereaper a "penny-longshot harvester" and VidarX "political and macro events". Neither matches the wallet's own report.

**P&L contradictions**
- Platform figure differs from computed: FlippingSharks (+$13,634), NeverSmiling (+$16,640), X-MoneyForWhiskas ($51,936 unexplained).
- Two P&L figures in one report: sixx7 ($19,190 vs $16,663), Sharky6999 ($59,615 vs $56,475), X-MoneyForWhiskas ($38,776 vs $38,466), ohanism ($258,687 vs $258,554).
- Cash-flow versus resolved-only views: SIRMARTINGALE ($119,586 vs $54,020), ExitLiquidty ($330,940 vs $185,765, and "86.4%" attached to the wrong base), LIL222 ($6,267 vs $5,563).
- Decomposition conventions are mixed across reports (Section 1). Ratue and SLIP-ME do not close arithmetically.

**Count contradictions**
- Rolling-window green counts: Gabigol, NeverSmiling, 0x04b6d7, Ratue, 080BEc, ExitLiquidty.
- SLIP-ME claims "8,658 of 4,725 markets" and "22/22 weeks" in a 3-week window.

**Mechanism contradictions**
- FlippingSharks claims it overweights the "cheaper side", but its own worked example tilts to the favorite.
- LIL222 is described as a "passive maker" in prose but lifts the ask with IOC orders in the playbook.
- BTC5MScour gives coverage as 36% in one place and "essentially every market" in another, and both "final 60–120 s" and "4+ min" entries.
- Hour filters do not match the hour tables: FlippingSharks, Bonereaper-Jun, NeverSmiling, Ratue.

**Unverifiable claims**
- Every fair-value or spot-feed signal.
- VidarX's sportsbook feed.
- BTC5MScour's Jun-21 "secondary signal".
- ExitLiquidty's DEX-lag entries.
- 0x04b6d7's US-East operator and ExitLiquidty's Asia-Pacific operator.
- SLIP-ME's manual throttling.
- Maker/taker status everywhere except X-MoneyForWhiskas. Notes C and D state that no report in those sets measures it.

**Wrong-trader header.** LIL222's header block (12 months, +$284K, Sharpe 2.1) describes a different trader.

---

## 5. Cross-wallet findings

**1. The dominance curve mostly measures price paid, not edge [inference].** All 15 both-sides curves (14 wallets, with Bonereaper counted twice) show the same rise. At 1.0–1.5x the dominant-side WR is 49–67%. At 3x+ it is 60–99%: PBot-6 60.4%, ohanism 77.7%, NeverSmiling 78.8%, Gabigol 82.9%, VidarX 84.2%, Ratue 85.2%, Bonereaper-Jun 87.6%, X-MoneyForWhiskas 92.6%, 0x04b6d7 92.9%, FlippingSharks and 080BEc 95.8%, Doggystyie 96.8%, sixx7 97.3%, SLIP-ME 99.0–99.8%.

The late-loading books build dominance by buying the leader at $0.85–0.97 near the close (Bonereaper-Jun, SLIP-ME, Ratue, 080BEc). Their high-dominance WR then approximates the implied probability of the prices paid. Four facts support that reading:
- Bonereaper-Jun's 3x+ markets have a mean paired cost of $1.058.
- Gabigol's $0.90+ band loses −$3,286 at a 96.4% WR.
- NeverSmiling's $0.90+ band loses −$4,517 at 95.4%.
- X-MoneyForWhiskas is −1.4% ROI at $0.90+.

Test: compare the 3x+ WR with the VWAP-implied probability for each bucket. A curve that sits on the implied line is not a signal.

**2. The "≥2x dominant leg only" filter is retrospective in every report.** Reported results: SLIP-ME +36.1%, sixx7 +29.7%, PBot-6 +22.8%, VidarX +22.5%, 080BEc +19.6%, 0x04b6d7 +18.1%, Ratue +12.5%, ohanism +6.4%, X-MoneyForWhiskas +3.3%. Final dominance is known only at the close, and in late-loading books it is partly caused by the outcome having become visible. The filter fails or loses money on three wallets: FlippingSharks +0.79%, Gabigol 1.81% (below baseline), Doggystyie −0.86%. The causal candidates are SLIP-ME's live-skew underdog block and Gabigol and Ratue's "side already at $0.70+" entry rules. Even those are tested only in-sample.

**3. Rewards and rebates are policy, not alpha.**
- Bonereaper-Jun: $369.9K, 4.2× its trading P&L.
- Doggystyie: $93.7K, against a −$34.9K trading result.
- X-MoneyForWhiskas: $43.5K in rebates plus $51.9K unexplained.
- Gabigol: $6.6K, 18% of the account.
- BTC5MScour: $230.

Four of the 19 wallets (21%) would show a much smaller or negative account P&L without incentive income. Every report that discusses incentives rates a program change as critical or high risk.

**4. Decay signs show up in five wallets:**
- Bonereaper: second window.
- 080BEc: rolling 7-day turned negative.
- FlippingSharks: late fade.
- sixx7: weaker late weeks.
- Ratue: W19 −$945.

NeverSmiling's first six rolling windows are negative, which is the reverse pattern. Signs of competition: Bonereaper's median paired cost rose from $1.006 to $1.016 and its share of sub-$1 markets fell from 47.3% to 44.9%.

**5. Shared-session clusters [inference].** April 12 appears in four wallets:
- SLIP-ME: its only red day, −$2,898.
- sixx7: worst market BTC 7:45 AM.
- Ratue: worst market BTC 7:30–7:45 PM ET.
- Sharky6999: worst market BTC 5:35–5:40.

Wednesday is extreme in four wallets: 0x04b6d7 (+72% of P&L), ExitLiquidty (+$165.8K), ohanism (only red day), and Bonereaper-Jun (only negative day). Hour 12–14 UTC is weak for Gabigol, NeverSmiling and X-MoneyForWhiskas but is PBot-6's best hour.

Ten windows overlap in April 2026, so cross-wallet "consistency" is largely one regime. Test: line up the daily P&L of the April-overlap wallets and measure their correlation.

**6. The $0.30–0.70 price filter cut P&L in 13 of the 14 reports that state its effect.** NeverSmiling is the only exception (+$2.5K). B1C58 and 0x04b6d7 quote only an ROI for it, with no P&L effect stated.

---

## 6. Handoff

**To the Spread-Capture Strategist**
- **X-MoneyForWhiskas.** Verify that the spread is positive under the net convention. Find the source of the $51,936 unexplained income. Confirm the taker-rebate rate (about 0.91 bps) still applies at your volume.
- **Bonereaper (both windows).** Re-profile a third window. Check whether trading ROI stays above 0. Model account P&L with rewards set to 0.
- **Doggystyie.** Use it as the reward-economics control. Get the live reward/volume ratio (break-even about 1.0%, run threshold >1.5%) before writing any code.
- **080BEc.** Pull fills after 2026-05-06 to test whether the rolling 7-day P&L recovered or kept decaying. Count it once.

**To the Latency & Late-Window Strategist**
- **SIRMARTINGALE.** Shadow-trade against Coinbase, Binance and Kraken ticks to confirm the spot→CLOB lag of 1–30 s. Reconcile the $119.6K and $54.0K figures. Measure the fill rate on exits at your own latency.
- **BTC5MScour.** Re-run without Jun 21. Track average entry price (alarm above $0.985). Confirm the realized-versus-implied WR gap in the $0.96–0.99 band from new data.
- **SLIP-ME.** Rebuild the underdog-block filter using **running** skew at fill time, not final skew. Then test it out of sample after 2026-04-27.
- **LIL222.** Count competing bids at $0.01 per market and confirm markets/day stays above 80. Ignore the header block.

**To the Token-Launch Strategist**
- **ExitLiquidty.** Treat it as at most two or three independent events. Verify MegaETH's actual FDV (the report says "~$1.2B" yet >$1.5B won 16-0). Recompute ROI on one base. Test whether entries really followed DEX prints [inference] by timestamp-matching fills to DEX price data. Size by event correlation, not by threshold count.

**Kill or park:** FlippingSharks, NeverSmiling, sixx7, Sharky6999 and VidarX until their P&L reconciles. Gabigol, 0x04b6d7 and Ratue until their spread is recomputed under one convention.

**Thesis breakers to monitor**
- For any tilt book: 3x+ WR falling to its VWAP-implied probability.
- For a reward book: reward/volume below 1.2% over 7 days.
- For a latency book: average entry above $0.985, or exit fill rate falling.
