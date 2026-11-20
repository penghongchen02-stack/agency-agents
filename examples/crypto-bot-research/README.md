# Multi-Agent Run: Crypto Prediction-Market Bot Research

Four Finance-division agents were run in parallel on the same evidence base: the 21 crypto-trading bot reports in the [PR&R trader reports](https://www.polyresearchrobotics.com/reports), catalogued in [research-polymarket-crypto-trading-bots.md](../research-polymarket-crypto-trading-bots.md). Each agent took the slice that matches its specialty.

| Step | Agent | Output | What it produced |
|---|---|---|---|
| 1 | 🔬 [Prediction Market Wallet Forensics Analyst](../../finance/finance-prediction-market-wallet-forensics-analyst.md) | [01-forensic-audit.md](01-forensic-audit.md) | Reconciles P&L for all 21 reports (19 unique wallets), gives independent archetype calls, ranks the evidence for a durable edge, lists data-quality flags, and hands off to the strategists |
| 2 | ⚖️ [Crypto Up/Down Spread-Capture Strategist](../../finance/finance-crypto-updown-spread-capture-strategist.md) | [02-spread-capture-strategy.md](02-spread-capture-strategy.md) | A comparative teardown of 14 both-sides books, a base strategy spec, an incentive-mode spec, causal replacements for the hindsight filter, a backtest plan, and kill switches |
| 3 | ⚡ [Crypto Up/Down Latency & Late-Window Strategist](../../finance/finance-crypto-updown-latency-strategist.md) | [03-latency-late-window-playbooks.md](03-latency-late-window-playbooks.md) | A latency-feasibility matrix, two playbooks a well-equipped independent can attempt, "do not attempt" verdicts, a measurement plan, and tail-risk numbers |
| 4 | 🚀 [Token Launch Event Market Strategist](../../finance/finance-token-launch-event-market-strategist.md) | [04-token-launch-playbook.md](04-token-launch-playbook.md) | A MegaETH ladder post-mortem, an ROI reconciliation, a reusable launch playbook with a worked hypothetical, the public-sale "No" screen, and a risk register |

## Next step: Polymarket US connectivity

[polymarket-us-connect/](polymarket-us-connect/README.md) is a read-only pre-flight check. It verifies that public market data, the BRTI settlement feed, the authenticated API, and both websockets connect, before any bot is built. It cannot trade.

## Where the four agents agree

1. **Incentives, not trading, make the biggest account numbers.**
   - About 81% of Bonereaper's June P&L is liquidity rewards.
   - Doggystyie lost $34.9K on trading and is positive only because of $93.7K in rewards.
   - About 71% of X-MoneyForWhiskas's account P&L is not trading. Its taker rebates come to about 0.91% of notional.
   - Treat any strategy that needs rewards as a bet on the reward program.
2. **The popular "dominant leg ≥2x" filter uses hindsight.** Final dominance is known only at the close. The forensic audit goes further and argues that the dominance curves mostly reflect the price paid for late-loaded leaders [inference]. Only causal entry rules qualify for live testing: live skew, spot-implied probability gap, and "side already at $0.70+".
3. **The reports disagree with themselves.**
   - Two of them double-count the hedge tax in their spread/directional split. Under a consistent rule, 0x04b6d7's tilt is about −$154K, not +$1.79M.
   - Several headline P&L and ROI figures do not reconcile. ExitLiquidty quotes 86.4%, but the resolved-buy ROI is 62.0%.
   - Two pairs of reports are the same wallet: 080BEc/B1C58 and Bonereaper April/June.
4. **Every series long enough to show it decays.** Bonereaper's trading ROI fell from 1.53% to 0.20%, and 080BEc's rolling 7-day P&L went from +$13K to −$3.3K.
5. **What an independent builder could realistically attempt:**
   - A both-sides BTC/ETH 5m book with a paired-cost gate and a causal tilt. Expect roughly 0.3–1.0% of notional before your own latency costs [inference].
   - A near-certainty sweep in the 30–120 s band, with redundant feeds.
   - A late load of the leading side only, with no underdog buys.
   - Research-led token-launch ladders capped per event.
6. **Don't attempt** spot-to-CLOB latency capture, sweeping in the final 30 s, penny-floor harvesting at scale, or favorite buying. These need colocated infrastructure, or they carry tail risk the win rate hides.

**Strongest evidence of a durable edge** (forensic ranking): SIRMARTINGALE, ohanism, BTC5MScour (excluding June 21), SLIP-ME, and X-MoneyForWhiskas. FlippingSharks, NeverSmiling, sixx7, Sharky6999, and VidarX should be set aside until their P&L reconciles.

> Research only. Not financial advice. Every figure comes from short (12–45 day) on-chain reconstructions published by a third party. Prediction-market trading may be restricted where you live. No strategy here uses or permits non-public information.
