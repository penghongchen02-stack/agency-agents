"""Cross-window arbitrage ("dominance pairs"): a bot family the earlier research never tried.

For one coin, the 5m, 15m and 1h Up/Down markets that END AT THE SAME INSTANT settle on the
same index value (the 60 s BRTI average). Take two of them, A and B, with
price_to_beat(A) <= price_to_beat(B) - gap. Then

    Up(A) wins  when close >= ptb(A)
    Down(B) wins when close <  ptb(B)

and for ANY close at least one of them wins (both win when ptb(A) <= close < ptb(B)). So the
pair Up(A) + Down(B) pays at least $1, whatever the coin does. When the two legs together
cost less than $1 including both taker fees, the pair cannot lose; it only has execution risk
(both legs must actually fill at those prices).

`gap` (default 0.01) covers settlement rounding: 15m and 1h markets publish 2-decimal closes and
opens, 5m markets 4 decimals, so a gap of one cent keeps the "at least one wins" rule true.
In the backtest, 11,913 of 11,968 same-instant groups had identical closes and the other 55
differed only by that rounding; no group ever had the lower-open market settle Down while the
higher-open market settled Up.

Prices are the stored display prices, moved to when they were really quoted (study.PRICE_DELAY_S):
Up price = best ask, Down price = 1 - best bid, $0.99 = no offer. Both legs are read at the same
instant. One trade per pair (the first time it is cheap enough), `contracts` of each leg.
"""

from __future__ import annotations

from collections import defaultdict

from . import study
from .settlement import taker_fee


def load_groups(conn):
    """{(asset, t_end): [market dict]} for groups of 2+ resolved markets with price points."""
    delay = study.PRICE_DELAY_S
    mk = {}
    for slug, a, h, we, ptb, close, out in conn.execute(
            "SELECT m.slug, m.asset, m.horizon, m.window_end, m.price_to_beat, m.settlement_price, m.outcome "
            "FROM markets m JOIN backfill_done b ON b.slug = m.slug "
            "WHERE m.outcome IS NOT NULL AND b.points > 0"):
        mk[slug] = {"slug": slug, "asset": a, "horizon": h, "t_end": int(round(we)), "ptb": ptb,
                    "close": close, "won_up": out == "UP", "pts": {}}
    for slug, ts, up, down in conn.execute("SELECT slug, ts, up_price, down_price FROM price_points"):
        m = mk.get(slug)
        if m and up is not None and down is not None:
            m["pts"][ts + delay] = (up, down)
    groups = defaultdict(list)
    for m in mk.values():
        groups[(m["asset"], m["t_end"])].append(m)
    return {k: v for k, v in groups.items() if len(v) > 1}


def pair_trades(groups, theta=0.095, max_cost=1.0, gap=0.01, min_left=30, max_left=600):
    """First cheap-enough dominance pair per (A, B), causal in time. Returns trade dicts."""
    out = []
    for (asset, t_end), ms in groups.items():
        for A in ms:
            for B in ms:
                if A is B or A["ptb"] is None or B["ptb"] is None or B["ptb"] - A["ptb"] < gap:
                    continue
                for t in sorted(set(A["pts"]) & set(B["pts"])):
                    left = t_end - t
                    if not (min_left <= left <= max_left):
                        continue
                    up_a, down_b = A["pts"][t][0], B["pts"][t][1]
                    if not (0 < up_a < study.UNBUYABLE_AT_OR_ABOVE and 0 < down_b < study.UNBUYABLE_AT_OR_ABOVE):
                        continue
                    cost = up_a + down_b + taker_fee(up_a, theta=theta) + taker_fee(down_b, theta=theta)
                    if cost >= max_cost:
                        continue
                    pay = (1.0 if A["won_up"] else 0.0) + (0.0 if B["won_up"] else 1.0)
                    out.append({"asset": asset, "t_end": t_end, "t": t, "left": left,
                                "a": A["slug"], "b": B["slug"], "ha": A["horizon"], "hb": B["horizon"],
                                "up_a": up_a, "down_b": down_b, "cost": cost, "pay": pay,
                                "pnl": pay - cost})
                    break
    return out
