"""New bot families that the hunt adds automatically, one per round.

Each family is tested under the same luck checks as the base grid: dev = first 75% of dates
(frozen), positive in A and B, positive at the pessimistic delay, dev z-score (no-edge null)
above a Bonferroni bar that counts EVERY variation tried so far (base grid + all families),
then scored once on the holdout and on new forward days. A family whose best variation is
confirmed and ranks in the top 5 is added to the leaderboard and the portfolio, and is
re-checked every later round.

Queue (FAMILY_QUEUE), tested in this order, one new family per hunt round:
  cross_window_arb      riskless pairs across 5m/15m/1h markets closing together (one per pair)
  cross_coin_lead       BTC's index lead decides the bet on ETH/SOL/XRP markets closing together
  cross_window_confirm  buy a 15m/1h side only when the 5m market closing together agrees
  arb_repeat            the riskless pair, bought again every minute while it stays cheap
"""

from __future__ import annotations

from itertools import product

import numpy as np

from .search import BANDS, _arrays, _z

FAMILY_QUEUE = ("cross_window_arb", "cross_coin_lead", "cross_window_confirm", "arb_repeat")
PAIRS = [(lo, hi) for lo, hi in product(BANDS, BANDS) if lo < hi]


# ---------------------------------------------------------------- shared helpers
def _arr(rows, theta, state, extra=None):
    a = _arrays(rows, theta)
    t = a["t_end"]
    a["per"] = {"A": t < state["cut_a"], "B": (t >= state["cut_a"]) & (t < state["cut_b"]),
                "dev": t < state["cut_b"], "hold": (t >= state["cut_b"]) & (t <= state["freeze"]),
                "fwd": t > state["freeze"]}
    a["side_up"] = np.array([(r["margin"] >= 0) == (r["side"] == "leader") for r in rows])
    a["own_lead_up"] = np.array([r["margin"] >= 0 for r in rows])
    for k, f in (extra or {}).items():
        a[k] = np.array([f(r) for r in rows], dtype=float)
    return a


def _pick(am, ap, masks, bar, min_trades=100):
    """masks: iterable of (config, mask_main, mask_pess). Best passing (z, cfg, m, mp) or None."""
    best = None
    for c, m, mp in masks:
        dsel = m & am["per"]["dev"]
        if dsel.sum() < min_trades:
            continue
        dev = am["pnl"][dsel]
        if dev.mean() <= 0:
            continue
        z = _z(dev, am["q"][dsel])
        if z < bar or (best and z <= best[0]):
            continue
        pa, pb = am["pnl"][m & am["per"]["A"]], am["pnl"][m & am["per"]["B"]]
        if not len(pa) or not len(pb) or pa.mean() <= 0 or pb.mean() <= 0:
            continue
        devp = ap["pnl"][mp & ap["per"]["dev"]]
        if not len(devp) or devp.mean() <= 0:
            continue
        best = (z, c, m, mp)
    return best


def _candidate(family, seg, rule, z, am, ap, m, mp, span):
    res = {"segment": seg, "family": family, "config": {"rule": rule}, "dev_z": z}
    for tag, a, mm in (("hold", am, m), ("hold_pess", ap, mp)):
        sel = mm & a["per"]["hold"]
        p = a["pnl"][sel]
        res[tag] = {"n": int(len(p)), "ev": float(p.mean()) if len(p) else None,
                    "z": _z(p, a["q"][sel]) if len(p) else 0.0, "losses": int((p < 0).sum()),
                    "per_day": float(p.sum() / span["hold"]) if span["hold"] > 0 else 0.0,
                    "_pnl": p, "_day": a["day"][sel], "_entry": a["t_end"][sel] - a["offset"][sel],
                    "_end": a["t_end"][sel] + 60, "_cost": a["q"][sel], "_kind": "bet"}
    sel = m & am["per"]["fwd"]
    p = am["pnl"][sel]
    res["forward"] = {"n": int(len(p)), "ev": float(p.mean()) if len(p) else None,
                      "per_day": float(p.sum() / span["forward"]) if span["forward"] > 0 else 0.0,
                      "_pnl": p, "_day": am["day"][sel], "_entry": am["t_end"][sel] - am["offset"][sel],
                    "_end": am["t_end"][sel] + 60, "_cost": am["q"][sel], "_kind": "bet"}
    return res


def _band(a, lo, hi):
    return a["buyable"] & (a["price"] >= lo) & (a["price"] <= hi)


# ---------------------------------------------------------------- cross_coin_lead
CCL_GRID = list(product((60, 120), (2.0, 5.0, 10.0, 20.0), ("any", "agree", "against"), PAIRS))


def _btc_map(rows):
    return {(r["t_end"], r["offset"]): r["margin"] * 1e4
            for r in rows if r["seg"].startswith("btc ") and r["side"] == "leader"}


def cross_coin_lead(ctx):
    out = []
    data, (main, pess) = ctx["data"], ctx["delays"]
    btc = {d: _btc_map(data[d]) for d in (main, pess)}
    for seg in sorted({r["seg"] for r in data[main] if not r["seg"].startswith("btc ")}):
        A = {d: _arr([r for r in data[d] if r["seg"] == seg], ctx["theta"], ctx["state"],
                     {"btc": lambda r, d=d: btc[d].get((r["t_end"], r["offset"]), np.nan)}) for d in (main, pess)}

        def masks():
            for o, th, mode, (lo, hi) in CCL_GRID:
                ms = []
                for a in (A[main], A[pess]):
                    b = a["btc"]
                    m = (a["offset"] == o) & ~np.isnan(b) & (np.abs(np.nan_to_num(b)) >= th) & _band(a, lo, hi)
                    m &= a["side_up"] == (np.nan_to_num(b) > 0)
                    if mode == "agree":
                        m &= a["own_lead_up"] == (np.nan_to_num(b) > 0)
                    elif mode == "against":
                        m &= a["own_lead_up"] != (np.nan_to_num(b) > 0)
                    ms.append(m)
                yield (o, th, mode, lo, hi), ms[0], ms[1]
        best = _pick(A[main], A[pess], masks(), ctx["bar"])
        if best:
            z, (o, th, mode, lo, hi), m, mp = best
            rule = (f"{o} s before close, buy the side BTC's index points to (BTC lead >= {th:g} bps"
                    f"{'' if mode == 'any' else ', own index ' + ('agrees' if mode == 'agree' else 'disagrees')}) "
                    f"at ${lo:.2f}-{hi:.2f}")
            out.append(_candidate("cross_coin_lead", seg, rule, z, A[main], A[pess], m, mp, ctx["span"]))
    return out


# ---------------------------------------------------------------- cross_window_confirm
CWC_GRID = list(product((60, 120, 180), ("leader", "other"), (0.6, 0.7, 0.8, 0.9, 0.95), (0.0, 5.0), PAIRS))


def _five_map(rows):
    """(asset, t_end, offset, side_up) -> 5m market's price of that direction."""
    out = {}
    for r in rows:
        if r["seg"].endswith(" 5m"):
            side_up = (r["margin"] >= 0) == (r["side"] == "leader")
            out[(r["seg"].split()[0], r["t_end"], r["offset"], side_up)] = r["price"]
    return out


def cross_window_confirm(ctx):
    out = []
    data, (main, pess) = ctx["data"], ctx["delays"]
    five = {d: _five_map(data[d]) for d in (main, pess)}
    for seg in sorted({r["seg"] for r in data[main] if not r["seg"].endswith(" 5m")}):
        asset = seg.split()[0]

        def p5(r, d):
            side_up = (r["margin"] >= 0) == (r["side"] == "leader")
            return five[d].get((asset, r["t_end"], r["offset"], side_up), np.nan)
        A = {d: _arr([r for r in data[d] if r["seg"] == seg], ctx["theta"], ctx["state"],
                     {"p5": lambda r, d=d: p5(r, d)}) for d in (main, pess)}

        def masks():
            for o, side, y, mg, (lo, hi) in CWC_GRID:
                ms = []
                for a in (A[main], A[pess]):
                    m = (a["offset"] == o) & (a["side"] == (side == "leader")) & _band(a, lo, hi)
                    m &= (np.nan_to_num(a["p5"], nan=-1) >= y) & (a["margin_bps"] >= mg)
                    ms.append(m)
                yield (o, side, y, mg, lo, hi), ms[0], ms[1]
        best = _pick(A[main], A[pess], masks(), ctx["bar"])
        if best:
            z, (o, side, y, mg, lo, hi), m, mp = best
            rule = (f"{o} s before close, buy the {side} at ${lo:.2f}-{hi:.2f} (index lead >= {mg:g} bps) only if "
                    f"the 5m market closing at the same moment prices that direction at >= ${y:.2f}")
            out.append(_candidate("cross_window_confirm", seg, rule, z, A[main], A[pess], m, mp, ctx["span"]))
    return out


# ---------------------------------------------------------------- arbitrage families
def _arb(ctx, repeat):
    from . import study
    from .strategies_cross import load_groups, pair_trades
    study.PRICE_DELAY_S = ctx["delays"][0]
    state, span = ctx["state"], ctx["span"]
    tr = pair_trades(load_groups(ctx["conn"]), theta=ctx["theta"], max_cost=1.0, repeat=repeat)
    if not tr:
        return []
    t_end = np.array([t["t_end"] for t in tr])
    pnl = np.array([t["pnl"] for t in tr])
    pay = np.array([t["pay"] for t in tr])
    entry = np.array([t["t"] for t in tr])
    cost = np.array([t["cost"] for t in tr])
    day = t_end // 86400
    zero = int((pay < 1).sum())
    per = {"dev": t_end < state["cut_b"], "hold": (t_end >= state["cut_b"]) & (t_end <= state["freeze"]),
           "fwd": t_end > state["freeze"]}

    def part(sel, days):
        p = pnl[sel]
        return {"n": int(len(p)), "ev": float(p.mean()) if len(p) else None,
                "z": 99.0 if len(p) and zero == 0 else 0.0, "losses": int((p < 0).sum()),
                "per_day": float(p.sum() / days) if days > 0 else 0.0, "_pnl": p, "_day": day[sel],
                "_entry": entry[sel], "_end": t_end[sel] + 60, "_cost": cost[sel], "_kind": "arb"}
    hold = part(per["hold"], span["hold"])
    rule = ("buy Up on the lower-open market and Down on the higher-open market of the same coin closing at "
            "the same instant (opens >= $0.01 apart) when both cost < $1 with fees"
            + (", again every minute while it stays that cheap" if repeat else ", once per pair"))
    return [{"segment": "all coins, paired windows", "family": "arb_repeat" if repeat else "cross_window_arb",
             "config": {"rule": rule}, "dev_z": 99.0 if zero == 0 else 0.0, "zero_payout_pairs": zero,
             "hold": hold, "hold_pess": hold, "forward": part(per["fwd"], span["forward"])}]


FAMILIES = {
    "cross_window_arb": {"run": lambda ctx: _arb(ctx, False), "grid": lambda segs: 1},
    "cross_coin_lead": {"run": cross_coin_lead, "grid": lambda segs: len(CCL_GRID) * sum(1 for s in segs if not s.startswith("btc "))},
    "cross_window_confirm": {"run": cross_window_confirm,
                             "grid": lambda segs: len(CWC_GRID) * sum(1 for s in segs if not s.endswith(" 5m"))},
    "arb_repeat": {"run": lambda ctx: _arb(ctx, True), "grid": lambda segs: 1},
}
