"""Replay trades with a real starting bankroll (default $1,000).

Every trade's stake (contracts x cost per contract, fees included) leaves cash when it is
opened and comes back with its payout when its market settles, so positions open at the
same time share the money. Each trade is sized as

    contracts = min(cap, floor(min(cash, max_frac x equity) / cost))

where equity = cash + stakes still open, and max_frac is 5% for a bet that can lose and 10%
for a riskless arbitrage pair (execution risk: one leg might not fill). A trade that cannot
afford one contract is skipped. Winnings are reinvested, so sizes grow with the balance.

A trade is (entry_ts, settle_ts, cost_per_contract, pnl_per_contract, kind), with kind
"bet" or "arb".
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

MAX_FRAC = {"bet": 0.05, "arb": 0.10}


def replay(trades, start=1000.0, cap=50, max_frac=None):
    max_frac = max_frac or MAX_FRAC
    cash, open_stake = float(start), 0.0
    pending = []                                   # (settle_ts, payout, stake)
    daily = defaultdict(float)
    n = skipped = limited = 0
    contracts_total = 0
    peak = trough_dd = equity = float(start)
    for entry, settle, cost, pnl, kind in sorted(trades, key=lambda t: (t[0], t[1])):
        while pending and pending[0][0] <= entry:
            s_ts, payout, stake = heapq.heappop(pending)
            cash += payout
            open_stake -= stake
            daily[int(s_ts // 86400)] += payout - stake
        equity = cash + open_stake
        peak = max(peak, equity)
        trough_dd = min(trough_dd, equity - peak)
        if cost <= 0:
            continue
        budget = min(cash, max_frac.get(kind, 0.05) * equity)
        k = min(cap, math.floor(budget / cost + 1e-9))
        if k < 1:
            skipped += 1
            continue
        if k < cap:
            limited += 1
        stake = k * cost
        cash -= stake
        open_stake += stake
        heapq.heappush(pending, (settle, k * (cost + pnl), stake))
        n += 1
        contracts_total += k
    while pending:
        s_ts, payout, stake = heapq.heappop(pending)
        cash += payout
        open_stake -= stake
        daily[int(s_ts // 86400)] += payout - stake
    days = sorted(daily)
    v = [daily[d] for d in days]
    return {"start": start, "end": cash, "profit": cash - start, "trades": n, "skipped": skipped,
            "size_limited": limited, "avg_contracts": contracts_total / n if n else 0.0,
            "days": len(v), "per_day": (sum(v) / len(v)) if v else 0.0,
            "worst_day": min(v) if v else 0.0, "positive_days": (sum(1 for x in v if x > 0) / len(v)) if v else 0.0,
            "max_drawdown": trough_dd}
