"""Four more strategy families, simulated per market on backfilled public data.

All buy at the exchange's stored display prices (about one point per minute, no size),
pay the taker fee theta * p * (1 - p) per contract, and hold to settlement. A $0.99 price is
unbuyable.

  both_sides     Legged pair (FlippingSharks / Gabigol style). Buy the first side at or
                 below `entry`, then the other side later if the pair, including fees, would
                 cost at most 1 - `edge`. If the second leg never comes, the first leg rides
                 to settlement (leg risk). The top-of-book Up and Down prices always sum to
                 >= $1 (Down = 1 - best Up bid), so a pair can only cost under $1 when the
                 two legs are bought at different times.
  longshot       Penny bot (LIL222 style). At T-d, buy any side priced between $0.01 and
                 `max_price` and hope the result flips.
  momentum       SLIP-ME style. At T-d, buy the side whose price rose by at least `rise`
                 over the previous `lookback_min` minutes, if it costs $0.50-$0.98.
  neversmiling   NeverSmiling style. At every price point between 10% and 90% of the window
                 (within the downloaded history), buy each side priced in $0.30-$0.70: `tilt`
                 contracts of the market favourite and 1 of the other side. Hold all.

Each simulate_* returns None (no trade) or (contracts, total_pnl, avg_price).
"""

from __future__ import annotations

from collections import defaultdict
from itertools import product

from .settlement import taker_fee
from . import study
from .study import UNBUYABLE_AT_OR_ABOVE


def load_markets(conn):
    rows = conn.execute(
        "SELECT m.slug, m.asset, m.horizon, m.window_start, m.window_end, m.outcome "
        "FROM markets m JOIN backfill_done b ON b.slug = m.slug "
        "WHERE m.outcome IS NOT NULL AND b.points > 0 ORDER BY m.window_end").fetchall()
    pts = defaultdict(list)
    for slug, ts, up, down in conn.execute(
            "SELECT slug, ts, up_price, down_price FROM price_points ORDER BY ts"):
        if up is not None and down is not None:
            pts[slug].append((ts + study.PRICE_DELAY_S, up, down))   # when it was really known
    return [{"slug": s, "asset": a, "horizon": h, "ws": int(round(ws)), "t_end": int(round(we)),
             "won_up": out == "UP", "pts": pts.get(s, [])} for s, a, h, ws, we, out in rows]


def _ok(p: float) -> bool:
    return 0 < p < UNBUYABLE_AT_OR_ABOVE


def _payout(side_up: bool, m) -> float:
    return 1.0 if side_up == m["won_up"] else 0.0


def _at(m, now, tolerance=60):
    return study.decision_point(m["pts"], now, tolerance)


# Each legs_* function is causal: it reads the price points in time order and returns the
# buys it would have made, as (ts, side_up, price, contracts). It never looks at the outcome,
# so the live paper trader (paper.py) runs the same functions on the data seen so far.

def legs_both_sides(m, params, theta):
    entry, edge = params["entry"], params["edge"]
    legs = []
    for ts, up, down in m["pts"]:
        if ts < m["ws"] or ts > m["t_end"] - 30:
            continue
        if not legs:
            for side_up, p in ((True, up), (False, down)):
                if _ok(p) and p <= entry:
                    legs.append((ts, side_up, p, 1))
                    break
        else:
            _, first_up, p1, _ = legs[0]
            p2 = down if first_up else up
            cost = p1 + p2 + taker_fee(p1, theta=theta) + taker_fee(p2, theta=theta)
            if _ok(p2) and cost <= 1 - edge:
                legs.append((ts, not first_up, p2, 1))
                break
    return legs


def legs_longshot(m, params, theta):
    pt = _at(m, m["t_end"] - params["offset"])
    if not pt:
        return []
    ts, up, down = pt
    return [(ts, s, p, 1) for s, p in ((True, up), (False, down))
            if _ok(p) and 0.01 <= p <= params["max_price"]]


def legs_momentum(m, params, theta):
    now = m["t_end"] - params["offset"]
    cur, past = _at(m, now), _at(m, now - 60 * params["lookback_min"])
    if not cur or not past:
        return []
    for side_up, idx in ((True, 1), (False, 2)):
        p, p0 = cur[idx], past[idx]
        if p - p0 >= params["rise"] and 0.50 <= p <= 0.98 and _ok(p):
            return [(cur[0], side_up, p, 1)]
    return []


def legs_neversmiling(m, params, theta):
    span = m["t_end"] - m["ws"]
    lo_t, hi_t = m["ws"] + 0.10 * span, m["ws"] + 0.90 * span
    legs = []
    for ts, up, down in m["pts"]:
        if lo_t <= ts <= hi_t:
            for side_up, p in ((True, up), (False, down)):
                if _ok(p) and 0.30 <= p <= 0.70:
                    legs.append((ts, side_up, p, params["tilt"] if p >= 0.50 else 1))
    return legs


def settle_legs(legs, won_up: bool, theta):
    """(contracts, total_pnl, avg_price) or None, holding every leg to settlement."""
    if not legs:
        return None
    contracts = sum(q for *_, q in legs)
    pnl = sum(q * ((1.0 if s == won_up else 0.0) - p - taker_fee(p, theta=theta)) for _, s, p, q in legs)
    return contracts, pnl, sum(q * p for _, _, p, q in legs) / contracts


def _simulator(legs_fn):
    def sim(m, params, theta):
        return settle_legs(legs_fn(m, params, theta), m["won_up"], theta)
    return sim


simulate_both_sides = _simulator(legs_both_sides)
simulate_longshot = _simulator(legs_longshot)
simulate_momentum = _simulator(legs_momentum)
simulate_neversmiling = _simulator(legs_neversmiling)

LEGS = {"both_sides": legs_both_sides, "longshot": legs_longshot,
        "momentum": legs_momentum, "neversmiling": legs_neversmiling}


FAMILIES = {
    "both_sides": (simulate_both_sides,
                   [dict(entry=e, edge=g) for e, g in product((0.30, 0.40, 0.45, 0.50), (0.0, 0.02, 0.04))]),
    "longshot": (simulate_longshot,
                 [dict(offset=o, max_price=x) for o, x in product((300, 180, 120, 60), (0.03, 0.05, 0.10))]),
    "momentum": (simulate_momentum,
                 [dict(offset=o, lookback_min=l, rise=r)
                  for o, l, r in product((180, 120, 60), (2, 3, 5), (0.10, 0.20, 0.30))]),
    "neversmiling": (simulate_neversmiling, [dict(tilt=t) for t in (1, 2, 3)]),
}


def _stats(results):
    res = [r for r in results if r]
    if not res:
        return {"n": 0}
    contracts = sum(r[0] for r in res)
    total = sum(r[1] for r in res)
    return {"n": len(res), "win_rate": sum(1 for r in res if r[1] > 0) / len(res),
            "avg_price": sum(r[2] * r[0] for r in res) / contracts,
            "ev": total / contracts, "total": total, "contracts": contracts}


def compare_extra(conn, theta: float = 0.095, min_trades: int = 30) -> dict:
    markets = load_markets(conn)
    by_seg = defaultdict(list)
    for m in markets:
        by_seg[(m["asset"], m["horizon"])].append(m)
    out = {}
    for seg, ms in sorted(by_seg.items()):
        ends = sorted(m["t_end"] for m in ms)
        split = ends[int(len(ends) * 2 / 3)]
        train = [m for m in ms if m["t_end"] < split]
        test = [m for m in ms if m["t_end"] >= split]
        fams = {}
        for fam, (sim, grid) in FAMILIES.items():
            scored = []
            for params in grid:
                tr = _stats([sim(m, params, theta) for m in train])
                if tr["n"] >= min_trades:
                    scored.append((tr["total"], params, tr))
            if not scored:
                fams[fam] = {"status": "too few trades to choose parameters"}
                continue
            scored.sort(key=lambda x: x[0], reverse=True)
            _, params, tr = scored[0]
            fams[fam] = {"params": params, "train": tr,
                         "test": _stats([sim(m, params, theta) for m in test])}
        out[f"{seg[0]} {seg[1]}"] = fams
    return out
