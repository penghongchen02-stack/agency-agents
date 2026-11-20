"""Variants: new bots built from the ones that lost, each aimed at the reason it lost.

The originals stay as they are; these run next to them.

  both_sides_strict      both_sides lost to fees on two legs. Only start below $0.25 and
                         only complete the pair if it costs at most $0.90-0.94 with fees.
  neversmiling_favourite NeverSmiling paid the fee again and again on both sides. Buy only
                         the market favourite, once, at a set time before close.
  longshot_close         Long shots lost because they rarely flip. Buy the cheap side only
                         when the index says the race is close (small margin).
  momentum_confirmed     Momentum lost on fake moves. Follow a price jump only when the
                         settlement index leader agrees with it.
  momentum_fade          The opposite bet: buy the side that just dropped, cheaply.
  model_edge_strict      model_edge, but only when the model's edge is at least 3-5 cents.

Each legs_* function is causal (it reads prices and index ticks only up to its decision
time) and never looks at the outcome. It returns (ts, side_up, price, contracts).
A market dict has: ws, t_end, pts [(ts, up, down)], ticks {ts: close}, ptb, won_up.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import product

from . import study
from .settlement import projected_close
from .strategies_extra import _at, _ok, legs_both_sides, settle_legs


def _leader(m, now):
    """(leader_is_up, margin_bps) from index ticks known at `now`, or None."""
    tk = {t: v for t, v in (m.get("ticks") or {}).items() if t <= now}
    if not tk or not m.get("ptb"):
        return None
    est = projected_close(tk, m["t_end"], now)
    if est is None:
        return None
    margin = (est - m["ptb"]) / m["ptb"]
    return margin >= 0, abs(margin) * 1e4


def legs_neversmiling_favourite(m, p, theta):
    pt = _at(m, m["t_end"] - p["offset"])
    if not pt:
        return []
    ts, up, down = pt
    side_up, price = (True, up) if up >= down else (False, down)
    if _ok(price) and p["lo"] <= price <= p["hi"]:
        return [(ts, side_up, price, 1)]
    return []


def legs_longshot_close(m, p, theta):
    pt = _at(m, m["t_end"] - p["offset"])
    if not pt:
        return []
    ts, up, down = pt
    lead = _leader(m, ts)
    if not lead or lead[1] > p["max_margin_bps"]:
        return []
    return [(ts, s, q, 1) for s, q in ((True, up), (False, down)) if _ok(q) and 0.01 <= q <= p["max_price"]]


def _moves(m, p):
    cur = _at(m, m["t_end"] - p["offset"])
    past = _at(m, m["t_end"] - p["offset"] - 60 * p["lookback_min"]) if cur else None
    return cur, past


def legs_momentum_confirmed(m, p, theta):
    cur, past = _moves(m, p)
    if not cur or not past:
        return []
    lead = _leader(m, cur[0])
    if not lead:
        return []
    for side_up, i in ((True, 1), (False, 2)):
        if cur[i] - past[i] >= p["rise"] and 0.50 <= cur[i] <= 0.98 and _ok(cur[i]) and side_up == lead[0]:
            return [(cur[0], side_up, cur[i], 1)]
    return []


def legs_momentum_fade(m, p, theta):
    cur, past = _moves(m, p)
    if not cur or not past:
        return []
    for side_up, i in ((True, 1), (False, 2)):
        if past[i] - cur[i] >= p["drop"] and 0.05 <= cur[i] <= 0.50 and _ok(cur[i]):
            return [(cur[0], side_up, cur[i], 1)]
    return []


VARIANTS = {
    "both_sides_strict": (legs_both_sides,
                          [dict(entry=e, edge=g) for e, g in product((0.15, 0.20, 0.25), (0.06, 0.08, 0.10))]),
    "neversmiling_favourite": (legs_neversmiling_favourite,
                               [dict(offset=o, lo=lo, hi=hi) for o, (lo, hi) in
                                product((540, 420, 300, 180), ((0.55, 0.70), (0.60, 0.80), (0.70, 0.90)))]),
    "longshot_close": (legs_longshot_close,
                       [dict(offset=o, max_price=x, max_margin_bps=b)
                        for o, x, b in product((120, 60), (0.10, 0.20, 0.30), (1, 3, 5))]),
    "momentum_confirmed": (legs_momentum_confirmed,
                           [dict(offset=o, lookback_min=l, rise=r)
                            for o, l, r in product((120, 60), (2, 3, 5), (0.10, 0.20))]),
    "momentum_fade": (legs_momentum_fade,
                      [dict(offset=o, lookback_min=l, drop=d)
                       for o, l, d in product((180, 120, 60), (2, 3, 5), (0.10, 0.20, 0.30))]),
}

# model_edge_strict reuses the index-bot machinery (strategies.py GRIDS / _select).


def load_variant_markets(conn):
    markets, ticks, points = study.load(conn)
    out = []
    for slug, asset, horizon, we, ptb, close, outc in markets:
        t_end = int(round(we))
        full = ticks.get(asset, {})
        ws = conn.execute("SELECT window_start FROM markets WHERE slug=?", (slug,)).fetchone()[0]
        out.append({"slug": slug, "asset": asset, "horizon": horizon, "ws": int(round(ws)), "t_end": t_end,
                    "ptb": ptb, "won_up": outc == "UP", "pts": points.get(slug, []),
                    "ticks": {t: full[t] for t in range(t_end - 400, t_end) if t in full}})
    return out


def _stats(results):
    res = [r for r in results if r]
    if not res:
        return {"n": 0}
    c = sum(r[0] for r in res)
    tot = sum(r[1] for r in res)
    return {"n": len(res), "win_rate": sum(1 for r in res if r[1] > 0) / len(res),
            "avg_price": sum(r[2] * r[0] for r in res) / c, "ev": tot / c, "total": tot, "contracts": c}


def compare_variants(conn, theta: float = 0.095, min_trades: int = 30) -> dict:
    by_seg = defaultdict(list)
    for m in load_variant_markets(conn):
        by_seg[(m["asset"], m["horizon"])].append(m)
    out = {}
    for seg, ms in sorted(by_seg.items()):
        ends = sorted(m["t_end"] for m in ms)
        split = ends[int(len(ends) * 2 / 3)]
        train = [m for m in ms if m["t_end"] < split]
        test = [m for m in ms if m["t_end"] >= split]
        fams = {}
        for fam, (legs, grid) in VARIANTS.items():
            def run(sample, params):
                return _stats([settle_legs(legs(m, params, theta), m["won_up"], theta) for m in sample])
            scored = [(tr["total"], params, tr) for params in grid
                      if (tr := run(train, params))["n"] >= min_trades]
            if not scored:
                fams[fam] = {"status": "too few trades to choose parameters"}
                continue
            _, params, tr = max(scored, key=lambda x: x[0])
            fams[fam] = {"params": params, "train": tr, "test": run(test, params)}
        out[f"{seg[0]} {seg[1]}"] = fams
    return out
