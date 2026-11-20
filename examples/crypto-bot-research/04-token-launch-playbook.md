# Token-Launch & Event-Market Playbook: Lessons from the ExitLiquidty Wallet

*Persona: Ladder (Token Launch Event Market Strategist). Sources: the PR&R ExitLiquidty report (published May 14, 2026, wallet `0xeb67…d696`, window 2026-03-30 to 2026-05-09), the dossier notes and the catalogue. Unlabelled figures come from those inputs. **[inferred]** marks my own reasoning. **[hypothetical]** marks invented numbers.*

> **Not financial advice.** Launch markets are thin and easy to manipulate, and they may be restricted where you live, so check your jurisdiction before trading. Everything below assumes public information only: no team, investor or launch-partner MNPI.

---

## 1. MegaETH ladder post-mortem (Launch Thesis template, filled in after the fact)

```markdown
# Launch Thesis (POST-MORTEM): MegaETH — launched inside the window; report infers a Wednesday
**Resolution source**: "MegaETH market cap (FDV) >$X one day after launch?" plus a second
  series "MegaETH FDV above $X one day after launch?". Price source/timestamp: NOT in inputs.
**Supply / comparables / pre-market signals**: NOT in inputs. The report says the operator
  "clearly tracks token supply schedules" [report inference]
```

| Threshold | P&L | Resolved record | Avg entry | Volume | Rung type (ex-ante, per report's ladder) |
|---|---|---|---|---|---|
| >$600M | +$11,609 | 24–0 | ~$0.42 | $57.5K | core |
| >$800M | +$50,968 | 70–0 | ~$0.32 | $143.2K | core |
| >$1B | +$51,555 | 134–0 | ~$0.40 | $159.6K | core (heaviest) |
| >$1.2B ("FDV above" series) | +$9,585 | n/a | n/a | $8.0K | core/upper |
| >$1B ("FDV above" series) | +$2,220 | n/a | n/a | $8.7K | core |
| >$1.5B | +$43,715 | 16–0 | ~$0.25 (EV section) / $0.15–0.20 (Phase 4) | $14.8K | stretch ("moderate", 10%) |
| >$1.6B ("FDV above") | −$1,692 | n/a | n/a | $1.7K | stretch |
| >$2B | −$21,665 | 0–18 | ~$0.21 | $25.5K | stretch ("longshot", 5%) |
| >$3B | −$1,649 | n/a | ~$0.058 | $1.6K | skip ("0% of budget") |

**Ladder net.** The report's five headline rungs net **+$136,182**. Adding the four smaller rungs gives **+$144,646 [my sum]**. The two launch-date binaries add another +$7,632, for about $152K in total. The report's event-family table says "~+$160K on ~$490K volume", which I cannot reconcile exactly.

**What the ladder shows.**
- **Correlation worked in its favour.** The three core rungs went **228–0 together**. The stretch rungs above about $1.6B lost together. "Every rung on one launch is the same bet," and here the bet was right.
- **Sizing was core-heavy but not clean.** By volume, the core rungs ($600M, $800M, $1B) total $360.3K. The $1.6B, $2B and $3B rungs total $28.8K, about 7% of the ladder. **[inferred]** That fits the 5–15% stretch rule. But the losing >$2B rung ($25.5K) drew *more* volume than the winning >$1.5B rung ($14.8K), so stretch dollars went to the wrong rung.
- **>$2B was negative EV at its price.** The report's own model (FDV $1.2B ± $300M) gives P(>$2B) ≈ 10% against an entry near $0.21. That is −52% expected ROI. The report concludes stretch entries are "only defensible at deeply discounted prices".
- **The entry prices break monotonicity.** >$800M averaged ~$0.32 while >$1B averaged ~$0.40. P(>$800M) must be at least P(>$1B), so **[inferred]** either the entries were made at different times, or the book was internally inconsistent, which is a free edge. The playbook below adds a monotonicity check.
- **The realized FDV is internally inconsistent.** The narrative says "~$1.2B", yet >$1.5B won 16–0 and >$1.2B won. **[inferred]** If both series resolve on the same source, the FDV landed between $1.5B and $1.6B. But the two series may use different wording or timestamps, and a negative "net P/L" can come from selling a rung at a loss rather than from the rung resolving No. Neither can be confirmed from the inputs.
- **The win was concentrated in time.** Wednesday produced +$165,835, about **89%** of resolved-buy P&L **[my ratio]**. The report attributes this to MegaETH launch day.

**Weeks 17–18 (the correlation's other face).**

| Week | Trades | Win rate | P&L | Cumulative |
|---|---|---|---|---|
| W14–W16 | 477 | 79–93% | +$195,508 | peak Apr 19 |
| W17 (Apr 20–26) | 64 | 81.2% | −$1,641 | $193,867 |
| W18 (Apr 27–May 1) | 19 | 31.6% | −$8,101 | $185,766 |

- The rolling 15-day P&L fell from **+$140,864 (Apr 18) to −$22,201 (May 7)**. Once MegaETH rolled out of the window, nothing replaced it.
- The report blames Printr in Phase 8, but it also lists Printr as **unresolved, $0 P&L**. **[inferred]** The red weeks therefore came from smaller events: P2P −$3K net, the Sentio/Based/Gensyn group about −$2.5K, Fluent FDV −$1.3K and LoL −$2.3K.
- The weekly table ends May 1 while the rolling series runs to May 7–8. A −$22.2K 15-day low implies losses after May 1 that the weekly table does not show **[inferred]**.
- The report also gives rolling-window counts that conflict (24/35 vs 27/41 for 7-day; 28/41 vs 33/41 for 15-day).

**P&L reconciliation (do this before quoting any ROI).**

| Basis | Numerator | Denominator | ROI |
|---|---|---|---|
| Resolved-BUY P&L | +$185,765 | $299,809 resolved-buy notional | **62.0%** (the category table says +61.96%) |
| Total realized cash flow | +$330,940 | $382,813 all BUY notional | **86.4%** |
| Headline as printed | +$185,765 | stated as "+86.4%" | **mismatched** |

- SELL minus BUY = +$141,350. The cash-flow identity (−buy + sell + payout) then implies about **$189,590** of settlement payout and open-position marks **[my arithmetic]**.
- The report describes the $145,175 gap (330,940 − 185,765) as "SELL proceeds above cost basis". That mixes two different bases.
- **[inferred]** Resolved-BUY P&L credits every resolved buy as if held to settlement, but many shares were sold first (EdgeX >$300M was sold out in full). It is a counterfactual hold-to-settle figure, not realized cash.
- Open positions, including the ~$195K Printr volume, were "marked at last price". That flatters the cash-flow figure until they settle.
- **Quote:** "~62% on resolved buys over 41 days. The 86.4% is cash flow on all buys, with open marks included."
- Ignore the report's "~+90% monthly" extrapolation, which comes from a single event.
- MegaETH reached **~41% of total buy notional**, above the report's own 35–40% cap.

---

## 2. Other events (brief post-mortems)

**EdgeX (Mar 31, rungs at $300M, $400M and $500M).**
- **>$300M:** sold entirely at $0.80–0.81 before settlement, giving up up to 20¢/share in exchange for no risk.
- **>$400M:** +$3,548 on $7.8K volume, 1–0 resolved, partly unresolved. It opened with sells of carried inventory at $0.65, scaled out at $0.61–0.63, sold a dip at $0.55 at 11:24, then **re-bought 3,023 shares at $0.70 at 12:32**, paying 15¢ more an hour later once conviction held. **[inferred]** That is information-driven re-entry, not price-driven re-entry.
- **>$500M:** bought at $0.59–0.64, with the buy at 12:34 coming in a 14-fills-in-7-minutes burst. It "returned additional P/L", amount not stated.
- **Family:** ~$16K volume, about +$3.5K.
- **Lesson:** this is a good template for tranche exits and re-entry. The trace's timestamps are slightly out of order (04:35 is listed before 04:26), and the inventory bought before the sample is invisible.

**Fluent.**
- "Over $2M committed to the Fluent public sale?" made **+$13,049 on $14.9K volume, 30/30 resolved wins**. The side is not stated. **[inferred]** P&L close to volume suggests a cheap-side entry, not $0.98 "No" grinding.
- "Fluent FDV above $100M" lost −$1,311 on $8.0K.
- **Lesson:** the sale-commitment edge and the FDV edge are separate theses on the same project. One worked and one did not.

**Gensyn and Sentio.**
- Gensyn FDV above $400M: −$793 on $2.2K. Sentio FDV above $100M: −$365 on $7.1K.
- The Sentio/Based/Gensyn group totals about −$2.5K on ~$20K.
- **Lesson:** small, mixed and unprofitable. Without a MegaETH-grade thesis, the ladder edge disappears.

**Printr public sale (see §4).**
- Five tiers: $6M ($33.3K volume), $8M ($41.7K), $10M ($52.6K), $15M ($39.2K) and $60M ($29.0K), about **$195.8K** in total.
- **All unresolved, $0 P&L** in the window. Do not count it as a win.

**P2P Protocol.**
- >$8M: +$5,716 on $1.1K volume. >$7M: −$3,075 on $3.1K. Net about −$3K on ~$26K.
- The sides are not stated. **[inferred]** Adjacent tiers splitting win/loss is consistent with the total landing between $7M and $8M, so a thin miss on one rung.

**Launch-date binaries.**
- "Will MegaETH launch a token by June 30, 2026?": **+$8,878** on $74.0K volume (40 trades, 17 resolved).
- "…by April 30, 2026?": **−$1,246** on $8.7K.
- **[inferred]** The FDV ladder resolved inside the window, which implies a launch before May. A loss on the April 30 binary is therefore puzzling: the inputs do not show whether it came from a No position, from selling at a loss, or from resolution wording that defines "launch" differently from the FDV markets.
- **Lesson:** run cross-market consistency checks, and read what "launch a token" means in each market's text.

**Off-niche.** Two LoL eSports trades lost −$2,327 at 0% win rate.

---

## 3. Reusable playbook for the next launch

**3.1 Research checklist (days to weeks before)**
- [ ] Match the market slug against the whitelist `*-fdv-above-*`, `*-market-cap-fdv-*`, `*committed-to-the-*-public-sale*` or `*launch-a-token*`. Reject everything else.
- [ ] Copy every market's resolution text verbatim. Check FDV vs market cap, "one day after launch", which price source, which timestamp, the slip/cancellation rule, and the supply definition (burns, staged unlocks).
- [ ] Check whether two series on the same token resolve differently. MegaETH ran two series.
- [ ] Build the tokenomics sheet from public docs only: total supply, TGE float and unlocks.
- [ ] Pull 3+ comparables with realized day+1 FDV.
- [ ] Record public pre-market signals: perps, points markets, OTC quotes.
- [ ] Identify the launch DEX and pool (e.g. Uniswap V3 or Raydium) and the contract address.
- [ ] Set up two independent DEX feeds.
- [ ] Check visible depth: at least $1,000 on the side you intend to buy.

**3.2 FDV distribution method**
1. Set a prior from the comparables (median and spread), then adjust it for float and pre-market signals.
2. Express the result as a distribution, e.g. lognormal, or the report's illustrative normal with σ ≈ 25% of the mean. Compute P(>T) for every listed threshold.
3. Check monotonicity: model probabilities and market prices must both fall as thresholds rise. A higher rung priced above a lower one is an edge or a data error. Investigate before trading.
4. Edge = P(model) − price. Stretch rungs need a deep discount; the report's >$2B example turns positive only below about $0.10.

**3.3 Ladder sizing: worked example. [hypothetical: "TOKEN-X", all numbers invented]**

Bankroll $20,000. Event budget $2,000 (10%), deliberately far below the 35–40% ceiling.

| Rung | P(model) | Price | Edge | Kind | `size_ladder` weight | Allocation |
|---|---|---|---|---|---|---|
| >$300M | 0.92 | 0.75 | +0.17 | core | 0.23×4 = 0.91 | **$634** |
| >$500M | 0.75 | 0.55 | +0.20 | core | 0.36×4 = 1.45 | **$1,017** |
| >$750M | 0.45 | 0.30 | +0.15 | stretch | 0.50 | $350 → capped **$300** |
| >$1B | 0.15 | 0.22 | −0.07 | stretch | 0 | **$0 (skip)** |

- Output from running the persona's function: **$1,950 deployed**. The 15% stretch cap trims $49.50, and the function leaves it unspent rather than redistributing it, which errs conservative.
- Core-to-stretch dollars come to about 5.5:1.
- Worst case, an FDV below $300M, loses $1,950, or 9.75% of bankroll.

**3.4 Launch-window DEX monitoring procedure**
1. At T−1h, confirm both feeds and the pool address. Confirm the supply figure that the resolution uses.
2. From T0, poll the DEX at least every 30 s (sub-minute is enough; no co-location needed). Compute live FDV as price × the resolution's supply definition, and mirror the CLOB mid every 30 s.
3. Re-rate each rung:
   - FDV > 1.15×T and Yes < $0.85: high-conviction add.
   - FDV between 0.95×T and 1.15×T and Yes < $0.60: moderate add.
   - FDV < 0.85×T: no Yes buys.
4. Walk the book in small bursts (5–20 fills). The report says the CLOB takes 30–120 min to price in DEX data, and the window lasts 6–24 h.
5. Be wary of the first-minutes DEX print. Act on prices sustained across both feeds **[inferred]**.
6. If a feed fails, make no new entries.

**3.5 Tranche exits (write them before entry).** Sell 30% at 2× entry, 20% more at ≥$0.85, and 20% more in the final hour at ≥$0.90. Hold the remaining 30%.
- **Gap [inferred]:** for any entry above $0.50, the 2× trigger can never fire. In §3.3, the $0.55 and $0.75 rungs go straight to the $0.85 tranche. For such rungs, pre-set a substitute first trim, e.g. 30% at +25¢.
- Stagger exits over hours, not minutes.
- Public-sale "No" positions: sell at $0.997–0.999 or hold to settlement.

**3.6 Invalidation rules**
- If DEX FDV stays below 0.9× a rung's threshold for 30 min, exit that rung in full. If it stays below 0.9× the lowest core threshold, exit every core rung.
- If the launch slips past a market's date, apply that market's text. Pre-decide hold or exit for each market.
- If the two DEX feeds disagree by more than a pre-set tolerance, freeze **[hypothetical parameter]**.

**3.7 Per-event caps**
- **Bankroll per launch.** The absolute ceiling is 35–40% of bankroll; most users should stay at 5–15% **[my recommendation]**. MegaETH ran at about 41%.
- **Stretch.** At most 5–15% of the event budget.
- **Launch binaries.** Under 5% of bankroll.
- **Public-sale "No".** Small. The report's $10–20K per tier is a ceiling at reference scale, not a target.
- **Depth.** Above about $50K per tier you move your own price.

---

## 4. Public-sale "No" screen

**Procedure**
1. List every threshold. Read the committed total from the official dashboard or the on-chain contract, never from social posts.
2. Compute the required rate: (threshold − committed) ÷ time left.
3. Compare it with the **best observed hourly inflow** for this sale and for comparable sales. The playbook's average-rate extrapolation is weaker, because sales often surge at the end **[inferred]**.
4. Buy "No" only when the required rate is many times the best observed rate, e.g. 10× or more **[hypothetical threshold]**, and the "No" book has depth.
5. Do the arithmetic before buying. At $0.99 you make 1¢ to risk 99¢, so break-even certainty is **99%**. One overshoot erases about 99 wins.
6. Note a contradiction in the report's playbook: it says "minimum No entry $0.90 (at least 10-cent upside)", but the actual fills were at $0.98–0.99.

**Printr example**
- The report's worked example has about **$12M committed, under 24h left, and "Over $60M" No at $0.99**. The gross is about $10 per $1,000.
- Fills were $499–$1,996 each, 10+ per market, with sells at $0.997–0.998, so roughly 0.7–0.8¢ captured per share.
- **[inferred]** At $12M committed, the $6M, $8M and $10M tiers were already exceeded, so their combined $127.6K of volume cannot have been unreachable-"No" trades at that moment. They were either Yes, or traded earlier, and the inputs do not say which.
- All tiers were unresolved in the window, so the screen's realized result is **unknown**.

---

## 5. Risk register

| Risk | Evidence in inputs | Control |
|---|---|---|
| **Correlation** | 228–0 core rungs and stretch rungs losing together on one launch; 15-day P&L from +$140.9K to −$22.2K; "If MegaETH had launched at $500M… near-total losses" | Treat one launch as one risk unit; use the event cap; size with `size_ladder` on a single shared budget |
| **Launch delay** | The MegaETH April 30 binary lost −$1,246 | Read each market's slip rule; keep binaries under 5% of bankroll; cross-check ladders against binaries |
| **Resolution wording** | Two MegaETH series, the "~$1.2B" vs >$1.5B-won conflict, an unexplained binary loss | Keep verbatim resolution text in the journal; log disputes |
| **Viral overshoot** | Report: "real examples exist of viral public sales dramatically exceeding projections" | Best-rate screen, small size, the 99% break-even rule |
| **Depth collapse on exit** | Report lists it as a medium risk | Exit in tranches over hours; stay under ~$50K per tier |
| **Manipulation of thin books** | Persona Rule 6; books thin enough that 14 fills walk them in 7 min | Act on sustained DEX prints from two feeds; never chase a single CLOB print **[inferred]** |
| **MNPI boundary** | Persona Rule 3 | Public tokenomics, DEX and dashboards only. No team, investor or partner leaks, no advance knowledge of TGE time. If you have a connection to the project, do not trade it |
| **Off-niche drift** | LoL −$2,327 at 0% win rate | Slug whitelist |
| **Accounting illusion** | 86.4% vs 62% ROI; open marks | Reconcile by rung on a cash-flow basis; quote resolved and open figures separately |

---

## 6. What can't be replicated, and why

1. **The operator's research pipeline and judgment.** The inputs never show the tokenomics model or the comparables, only the trades. The report says fully systematic entries produce "the same win rate as a random buyer… which is not 82.5%".
2. **The MegaETH outcome itself.** About 89% of resolved P&L came on one weekday from one launch. That is n=1, and the follow-on events (Gensyn, Sentio, P2P, Fluent FDV) were net negative.
3. **Lazily priced books at entry.** The report warns the edge decays as competitors arrive. If near-certain rungs open above $0.70, the ROI compresses.
4. **Risk tolerance.** About 41% of buy notional went into one event, with a $52,200 maximum fill. Most readers should not size like this.
5. **Data gaps.** Buys before the sample are invisible (EdgeX inventory), Printr is unresolved, sides are often unstated, and the report's figures conflict (ROI, realized FDV, rolling counts, 34 vs 41 days). Any backtest built from these inputs inherits those gaps.
6. **Timing advantage.** Activity peaks at 02:00–11:00 UTC. The report only infers an Asia-Pacific operator or deliberate pre-US timing; copying the clock does not copy the information.
