"""Compare several late-window strategy families on backfilled public data.

Families (all buy 1 contract of one side at its displayed price and hold to settlement;
P&L = payout - price - taker fee; a $0.99 price is unbuyable):

  favourite      Buy the side the index projection says is ahead, if the market also
                 prices it as the favourite ($0.50-$0.98). This was the original study.
  model_edge     Same side, but only when a volatility-aware probability model says its
                 chance of winning beats price + fee by at least `edge`. This is the
                 "tighter rules" version.
  disagreement   Buy the index leader when the market prices it BELOW $0.50, meaning the
                 market disagrees with the index projection.

Model: log-price is a driftless random walk with per-second volatility estimated from the
previous 120 s of index ticks. The settlement value is the average of the 60 s before T,
so the remaining variance is:
    before the window:  sigma^2 * ((T-60 - now) + 20)       (a 60 s average adds 60/3)
    inside the window:  sigma^2 * (r/60)^2 * (r/3),  r = T - now
p(leader wins) = Phi(|margin| / sqrt(variance)).

Walk-forward: for each family, parameters are chosen on the first 2/3 of dates (by total
P&L, at least `min_trades` trades) and reported only on the last 1/3.
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import product
from statistics import NormalDist

from .settlement import projected_close, taker_fee
from .study import UNBUYABLE_AT_OR_ABOVE, decision_point, load

OFFSETS = (180, 120, 60)
_PHI = NormalDist().cdf


def _sigma(ticks: dict[int, float], now: int, lookback: int = 120) -> float | None:
    xs = [ticks[t] for t in range(now - lookback, now + 1) if t in ticks]
    if len(xs) < lookback // 2:
        return None
    rets = [math.log(b / a) for a, b in zip(xs, xs[1:]) if a > 0 and b > 0]
    if len(rets) < 10:
        return None
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) if var > 0 else None


def model_probability(margin: float, sigma: float, t_end: int, now: int,
                      k: float = 1.0, basis: float = 0.0) -> float:
    """k scales volatility (1 s index candles are smoothed); basis is the relative s.d. of
    the gap between the public index candles and the official settlement value."""
    start = t_end - 60
    s2 = (k * sigma) ** 2
    if now < start:
        var = s2 * ((start - now) + 20)
    else:
        r = max(t_end - now, 0)
        var = s2 * (r / 60) ** 2 * (r / 3)
    var += basis ** 2
    if var <= 0:
        return 1.0
    return _PHI(abs(margin) / math.sqrt(var))


K_GRID = (1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 24.0)
BASIS_GRID_BPS = (0.0, 1.0, 2.0, 3.0, 5.0, 8.0)


def fit_model(rows) -> tuple[float, float]:
    """Pick (k, basis) maximising the log-likelihood of outcomes on the given rows."""
    best, best_ll = (1.0, 0.0), -float("inf")
    rows = [r for r in rows if r["sigma"]]
    for k, b_bps in product(K_GRID, BASIS_GRID_BPS):
        ll = 0.0
        for r in rows:
            p = model_probability(r["margin"], r["sigma"], r["t_end"], r["now"], k, b_bps / 1e4)
            p = min(max(p, 1e-6), 1 - 1e-6)
            ll += math.log(p if r["won"] else 1 - p)
        if ll > best_ll:
            best, best_ll = (k, b_bps / 1e4), ll
    return best


def apply_model(rows, k: float, basis: float) -> None:
    for r in rows:
        if r["sigma"]:
            r["p_model"] = model_probability(r["margin"], r["sigma"], r["t_end"], r["now"], k, basis)


def observations(markets, ticks, points):
    rows = []
    for slug, asset, horizon, we, ptb, close, out in markets:
        t_end = int(round(we))
        full = ticks.get(asset, {})
        tk = {t: full[t] for t in range(t_end - max(OFFSETS) - 200, t_end) if t in full}
        for d in OFFSETS:
            pt = decision_point(points.get(slug, []), t_end - d)
            if not pt:
                continue
            now, up, down = pt                  # decide when the price was really seen
            est = projected_close(tk, t_end, now)
            sig = _sigma(tk, now)
            if est is None or up is None or down is None:
                continue                         # sig may be None: model_edge then skips the row
            margin = (est - ptb) / ptb
            leader = "UP" if margin >= 0 else "DOWN"
            price = up if leader == "UP" else down
            rows.append({"asset": asset, "horizon": horizon, "t_end": t_end, "offset": d,
                         "now": now, "margin": margin, "sigma": sig,
                         "margin_bps": abs(margin) * 1e4, "price": price, "won": leader == out,
                         "p_model": model_probability(margin, sig, t_end, now) if sig else None})
    return rows


def _pnl(r, theta):
    return (1.0 if r["won"] else 0.0) - r["price"] - taker_fee(r["price"], theta=theta)


def _select(rows, family, params, theta):
    out = []
    for r in rows:
        p = r["price"]
        if r["offset"] != params["offset"] or p >= UNBUYABLE_AT_OR_ABOVE or p <= 0:
            continue
        if family == "favourite":
            ok = 0.50 <= p <= params["max_price"] and r["margin_bps"] >= params["margin_bps"]
        elif family in ("model_edge", "model_edge_strict"):
            ok = r["p_model"] is not None and 0.50 <= p <= 0.98 and r["p_model"] - p - taker_fee(p, theta=theta) >= params["edge"]
        elif family == "hourly_leader":   # search winner: leader in a price band, margin, optional edge
            ok = (params["lo"] <= p <= params["hi"] and r["margin_bps"] >= params["margin_bps"]
                  and (params.get("edge") is None
                       or (r["p_model"] is not None and r["p_model"] - p - taker_fee(p, theta=theta) >= params["edge"])))
        else:  # disagreement
            ok = params["min_price"] <= p < 0.50 and r["margin_bps"] >= params["margin_bps"]
        if ok:
            out.append(r)
    return out


def _stats(sel, theta):
    if not sel:
        return {"n": 0}
    pnl = [_pnl(r, theta) for r in sel]
    return {"n": len(sel), "win_rate": sum(r["won"] for r in sel) / len(sel),
            "avg_price": sum(r["price"] for r in sel) / len(sel),
            "ev": sum(pnl) / len(pnl), "total": sum(pnl)}


GRIDS = {
    "favourite": [dict(offset=o, margin_bps=m, max_price=x)
                  for o, m, x in product(OFFSETS, (0, 5, 10, 20), (0.90, 0.95, 0.98))],
    "model_edge": [dict(offset=o, edge=e) for o, e in product(OFFSETS, (0.0, 0.02, 0.04, 0.08))],
    "model_edge_strict": [dict(offset=o, edge=e) for o, e in product(OFFSETS, (0.03, 0.05))],   # variant
    "disagreement": [dict(offset=o, margin_bps=m, min_price=x)
                     for o, m, x in product(OFFSETS, (0, 5, 10, 20), (0.02, 0.05, 0.10))],
}


def calibration_of_model(rows, bins=(0.5, 0.8, 0.9, 0.95, 0.98, 0.995, 1.0001)):
    """Does the model's probability match reality? (all rows, regardless of price)."""
    out = []
    for lo, hi in zip(bins, bins[1:]):
        sel = [r for r in rows if r["p_model"] is not None and lo <= r["p_model"] < hi]
        if sel:
            out.append({"p_model": f"{lo:.3f}-{min(hi, 1):.3f}", "n": len(sel),
                        "avg_model": sum(r["p_model"] for r in sel) / len(sel),
                        "won": sum(r["won"] for r in sel) / len(sel)})
    return out


def compare(conn, theta: float = 0.095, min_trades: int = 30) -> dict:
    rows = observations(*load(conn))
    from . import study
    res = {"observations": len(rows), "price_delay_s": study.PRICE_DELAY_S, "segments": {}, "raw_model_calibration": calibration_of_model(rows)}
    if not rows:
        return res
    test_all = []
    by_seg = defaultdict(list)
    for r in rows:
        by_seg[(r["asset"], r["horizon"])].append(r)
    for seg, seg_rows in sorted(by_seg.items()):
        ends = sorted({r["t_end"] for r in seg_rows})
        split = ends[int(len(ends) * 2 / 3)]
        train = [r for r in seg_rows if r["t_end"] < split]
        test = [r for r in seg_rows if r["t_end"] >= split]
        k, basis = fit_model(train)                 # calibrated on TRAIN only
        apply_model(seg_rows, k, basis)
        test_all.extend(test)
        seg_out = {"markets": len(ends), "model_fit": {"k": k, "basis_bps": round(basis * 1e4, 2)},
                   "families": {}}
        for fam, grid in GRIDS.items():
            scored = []
            for params in grid:
                tr = _stats(_select(train, fam, params, theta), theta)
                if tr["n"] >= min_trades:
                    scored.append((tr["total"], params, tr))
            if not scored:
                seg_out["families"][fam] = {"status": "too few trades to choose parameters"}
                continue
            scored.sort(key=lambda x: x[0], reverse=True)
            _, params, tr = scored[0]
            te = _stats(_select(test, fam, params, theta), theta)
            seg_out["families"][fam] = {"params": params, "train": tr, "test": te}
        res["segments"][f"{seg[0]} {seg[1]}"] = seg_out
    res["model_calibration"] = calibration_of_model(test_all)   # fitted model, TEST rows only
    from .strategies_extra import compare_extra
    from .strategies_variants import compare_variants
    extra = compare_extra(conn, theta=theta, min_trades=min_trades)
    for seg, fams in compare_variants(conn, theta=theta, min_trades=min_trades).items():
        extra.setdefault(seg, {}).update(fams)
    for seg, fams in extra.items():
        res["segments"].setdefault(seg, {"markets": None, "model_fit": {"k": "-", "basis_bps": "-"},
                                         "families": {}})["families"].update(fams)
    return res


def format_compare(res: dict) -> str:
    L = ["Strategy comparison (public Polymarket US data, walk-forward)", "=" * 72,
         f"decision observations: {res['observations']}   price delay: {res.get('price_delay_s')} s"]
    if res.get("raw_model_calibration"):
        L.append("\nRaw model (uncalibrated), all rows: predicted vs actual leader win rate")
        for c in res["raw_model_calibration"]:
            L.append(f"  model {c['p_model']:13s} n {c['n']:>6}  predicted {c['avg_model']:.3f}  actual {c['won']:.3f}")
    if res.get("model_calibration"):
        L.append("\nCalibrated model (fit on train, shown on TEST rows): predicted vs actual")
        for c in res["model_calibration"]:
            L.append(f"  model {c['p_model']:13s} n {c['n']:>6}  predicted {c['avg_model']:.3f}  actual {c['won']:.3f}")
    fits = ", ".join(f"{k}: k={v['model_fit']['k']} basis={v['model_fit']['basis_bps']}bps"
                     for k, v in res["segments"].items() if v.get("model_fit"))
    L.append(f"\nModel fit per segment: {fits}")
    L.append("\nTEST period only (last 1/3 of dates); parameters chosen on the first 2/3")
    L.append(f"  {'segment':10s} {'family':13s} {'params':38s} {'n':>4s} {'win':>6s} {'px':>6s} "
             f"{'EV/ct':>8s} {'total':>8s}")
    for seg, s in res["segments"].items():
        for fam, f in s["families"].items():
            if "test" not in f:
                L.append(f"  {seg:10s} {fam:13s} {f['status']}")
                continue
            p = ",".join(f"{k}={v}" for k, v in f["params"].items())
            t = f["test"]
            if not t.get("n"):
                L.append(f"  {seg:10s} {fam:13s} {p:38s}    0 trades in test")
                continue
            L.append(f"  {seg:10s} {fam:13s} {p:38s} {t['n']:>4d} {t['win_rate']:>6.1%} {t['avg_price']:>6.3f} "
                     f"{t['ev']:>+8.4f} {t['total']:>+8.2f}")
    L.append("\nn = markets traded; win = share of traded markets with positive P&L; px = average price paid;\n"
             "EV/ct = average P&L per contract after the Tier 1 taker fee; total = sum of P&L (dollars).\n"
             "Limits: display prices have no size; ~1 point per minute; small test samples are noise.")
    return "\n".join(L)
