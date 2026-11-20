"""Historical study of the late-window "buy the leader" strategy on backfilled public data.

Inputs (from `backfill`): resolved markets, the exchange's stored Up/Down display prices
(about one per minute), and 1-second settlement-index candles.

At each decision offset d seconds before close, using only information available at T-d:
  * projected close = average of the index seconds of [T-60, T) already elapsed, with
    the latest price filling the remaining seconds (no look-ahead)
  * margin = (projected close - priceToBeat) / priceToBeat; leader = UP if margin >= 0
  * leader price = Up display price (if UP) or Down display price (if DOWN), at the
    latest stored point in [T-d-30, T-d]
  * trade 1 contract at that price if |margin| >= threshold and price <= max_price
  * P&L = payout (1/0) - price - taker fee (theta * p * (1-p), Tier 1 theta 0.095)

Limits, stated plainly: display prices carry no size, so fill size and slippage are
unknown; points are ~1 per minute; the index candles reconstruct closes only
approximately. Treat results as a screening test, not a promise of live P&L.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import product

from .settlement import projected_close, taker_fee, window_average

OFFSETS = (180, 120, 60)
MARGINS_BPS = (0, 2, 3, 5, 8, 12, 20)
MAX_PRICES = (0.90, 0.95, 0.97, 0.98)
# A $0.99 display price usually means "best bid 0.99, no offer" (seen in live books): nothing
# to buy. Never count it as a fill.
UNBUYABLE_AT_OR_ABOVE = 0.99
# The strategy buys the FAVOURITE. A leader priced under $0.50 means the market disagrees with
# the index projection; buying it is a different (long-shot) strategy, so it is excluded.
MIN_PRICE = 0.50
# /v1/price-history timestamps run EARLY. A lead-lag test against the 1 s settlement index
# (400 random 15m/1h markets, 2026-11-20) showed price changes line up with index moves about
# 90 s AFTER their timestamp, with no correlation at the stated time. Using the raw stamp lets
# a "T-60" decision see the price from about T+30, after the result is known. Every point is
# therefore moved to ts + PRICE_DELAY_S, and each decision is made AT that moment, using index
# data only up to then. A delay set too short peeks ahead; one set too long trades a stale
# quote against a fresher index. Both inflate profits, so run `compare --price-delay` at
# 60/90/120 and trust only results that hold at the measured value (90 s).
PRICE_DELAY_S = 90


def decision_point(pts, target, max_age=60):
    """Latest price point really known at or before `target` (and no older than max_age).
    Returns (decision_time, up, down) or None. The caller must use index data only up to
    decision_time, so the price and the index are equally fresh."""
    best = None
    for p in pts:
        if target - max_age <= p[0] <= target:
            best = p
    return best
CALIB_BUCKETS = [(0.50, 0.80), (0.80, 0.90), (0.90, 0.95), (0.95, 0.97), (0.97, 0.985)]


def load(conn):
    markets = conn.execute(
        "SELECT m.slug, m.asset, m.horizon, m.window_end, m.price_to_beat, m.settlement_price, m.outcome "
        "FROM markets m JOIN backfill_done b ON b.slug = m.slug "
        "WHERE m.outcome IS NOT NULL AND b.points > 0 ORDER BY m.window_end").fetchall()
    ticks = defaultdict(dict)
    for asset, ts, close in conn.execute("SELECT asset, ts, close FROM index_ticks"):
        ticks[asset][ts] = close
    points = defaultdict(list)
    for slug, ts, up, down in conn.execute("SELECT slug, ts, up_price, down_price FROM price_points ORDER BY ts"):
        points[slug].append((ts + PRICE_DELAY_S, up, down))   # when it was really known
    return markets, ticks, points


def observations(markets, ticks, points):
    """One row per (market, offset) with everything known at decision time."""
    rows = []
    for slug, asset, horizon, we, ptb, close, out in markets:
        t_end = int(round(we))
        full = ticks.get(asset, {})
        # only this market's last minutes: keeps projected_close O(window) instead of O(all ticks)
        tk = {t: full[t] for t in range(t_end - max(OFFSETS) - 200, t_end) if t in full}
        for d in OFFSETS:
            pt = decision_point(points.get(slug, []), t_end - d)
            if not pt:
                continue
            now, up, down = pt
            est = projected_close(tk, t_end, now)
            if est is None or up is None or down is None:
                continue
            margin = (est - ptb) / ptb
            leader = "UP" if margin >= 0 else "DOWN"
            price = up if leader == "UP" else down
            rows.append({"slug": slug, "horizon": horizon, "t_end": t_end, "offset": d,
                         "margin_bps": abs(margin) * 1e4, "leader": leader, "price": price,
                         "won": leader == out})
    return rows


def _pnl(r, theta):
    return (1.0 if r["won"] else 0.0) - r["price"] - taker_fee(r["price"], theta=theta)


def evaluate(rows, offset, margin_bps, max_price, theta):
    sel = [r for r in rows if r["offset"] == offset and r["margin_bps"] >= margin_bps
           and MIN_PRICE <= r["price"] <= max_price and r["price"] < UNBUYABLE_AT_OR_ABOVE]
    if not sel:
        return {"n": 0}
    pnl = [_pnl(r, theta) for r in sel]
    return {"n": len(sel), "win_rate": sum(r["won"] for r in sel) / len(sel),
            "avg_price": sum(r["price"] for r in sel) / len(sel),
            "ev": sum(pnl) / len(pnl), "total": sum(pnl), "worst_loss": min(pnl)}


def run_study(conn, theta: float = 0.095, min_trades: int = 30) -> dict:
    markets, ticks, points = load(conn)
    rows = observations(markets, ticks, points)
    out: dict = {"markets": len(markets), "observations": len(rows), "theta": theta}
    if not rows:
        return out
    # settlement reproduction over the whole backfill
    errs = []
    for slug, asset, horizon, we, ptb, close, o in markets:
        avg, n = window_average(ticks.get(asset, {}), int(round(we)))
        if avg is not None and n >= 55:
            errs.append(abs(avg - close) / close * 1e4)
    errs.sort()
    if errs:
        out["reproduction_error_bps"] = {"n": len(errs), "median": errs[len(errs) // 2],
                                         "p95": errs[int(len(errs) * 0.95)], "max": errs[-1]}
    # how often is there anything to buy below $0.99 at all?
    for d in OFFSETS:
        sub = [r for r in rows if r["offset"] == d]
        out.setdefault("availability", {})[d] = {
            "obs": len(sub),
            "leader_price<=0.98": sum(r["price"] <= 0.98 for r in sub) / max(len(sub), 1),
            "leader_price>=0.99": sum(r["price"] >= UNBUYABLE_AT_OR_ABOVE for r in sub) / max(len(sub), 1),
            "leader_win_rate": sum(r["won"] for r in sub) / max(len(sub), 1)}
    # calibration: does the market under-price the leader?
    calib = {}
    for d in OFFSETS:
        for lo, hi in CALIB_BUCKETS:
            sel = [r for r in rows if r["offset"] == d and lo <= r["price"] < hi]
            if sel:
                pnl = [_pnl(r, theta) for r in sel]
                calib[f"T-{d}s {lo:.3f}-{hi:.3f}"] = {
                    "n": len(sel), "avg_price": sum(r["price"] for r in sel) / len(sel),
                    "win_rate": sum(r["won"] for r in sel) / len(sel), "ev": sum(pnl) / len(pnl)}
    out["calibration"] = calib
    # walk-forward: choose parameters on the first 2/3 of time, test on the last 1/3
    cut = sorted({r["t_end"] for r in rows})
    split = cut[int(len(cut) * 2 / 3)]
    train = [r for r in rows if r["t_end"] < split]
    test = [r for r in rows if r["t_end"] >= split]
    grid = []
    for d, mb, mp in product(OFFSETS, MARGINS_BPS, MAX_PRICES):
        tr = evaluate(train, d, mb, mp, theta)
        if tr["n"] >= min_trades:
            grid.append(((d, mb, mp), tr))
    grid.sort(key=lambda x: x[1]["total"], reverse=True)
    out["split_ts"] = split
    out["train_top"] = [{"offset": p[0], "margin_bps": p[1], "max_price": p[2], **s} for p, s in grid[:5]]
    if grid:
        (d, mb, mp), _ = grid[0]
        out["chosen"] = {"offset": d, "margin_bps": mb, "max_price": mp}
        out["test_result"] = evaluate(test, d, mb, mp, theta)
        out["test_by_horizon"] = {h: evaluate([r for r in test if r["horizon"] == h], d, mb, mp, theta)
                                  for h in sorted({r["horizon"] for r in test})}
    return out


def format_study(s: dict) -> str:
    L = ["Late-window leader study (public Polymarket US data)", "=" * 64,
         f"markets: {s['markets']}   observations: {s['observations']}   taker theta: {s['theta']}"]
    if not s.get("observations"):
        return "\n".join(L + ["No data. Run `python -m pmus_recorder backfill` first."])
    if "reproduction_error_bps" in s:
        e = s["reproduction_error_bps"]
        L.append(f"index reconstruction error vs official close (bps): median {e['median']:.2f}, "
                 f"p95 {e['p95']:.2f}, max {e['max']:.2f} over {e['n']} markets")
    L.append("\nIs there anything to buy? (leader = side ahead on projected 60 s average)")
    for d, a in s["availability"].items():
        L.append(f"  T-{d:>3}s  obs {a['obs']:>5}  buyable (<= $0.98): {a['leader_price<=0.98']:>6.1%}"
                 f"  already $0.99 (no offer): {a['leader_price>=0.99']:>6.1%}"
                 f"  leader won: {a['leader_win_rate']:.1%}")
    L.append("\nCalibration: leader price vs how often the leader actually won")
    L.append(f"  {'bucket':24s} {'n':>5s} {'avg px':>7s} {'won':>7s} {'EV/contract':>12s}")
    for k, v in s["calibration"].items():
        L.append(f"  {k:24s} {v['n']:>5d} {v['avg_price']:>7.3f} {v['win_rate']:>7.1%} {v['ev']:>+12.4f}")
    L.append("\nWalk-forward (params chosen on first 2/3 of time, tested on last 1/3)")
    for t in s.get("train_top", [])[:3]:
        L.append(f"  train: T-{t['offset']}s margin>={t['margin_bps']}bps px<={t['max_price']}: "
                 f"n {t['n']} win {t['win_rate']:.1%} EV {t['ev']:+.4f} total {t['total']:+.2f}")
    if "test_result" in s:
        c, t = s["chosen"], s["test_result"]
        if t.get("n"):
            L.append(f"  TEST : T-{c['offset']}s margin>={c['margin_bps']}bps px<={c['max_price']}: "
                     f"n {t['n']} win {t['win_rate']:.1%} avg px {t['avg_price']:.3f} "
                     f"EV {t['ev']:+.4f}/contract total {t['total']:+.2f} worst {t['worst_loss']:+.2f}")
            for h, v in s["test_by_horizon"].items():
                if v.get("n"):
                    L.append(f"         {h}: n {v['n']} win {v['win_rate']:.1%} EV {v['ev']:+.4f}")
        else:
            L.append("  TEST : no qualifying trades in the test period")
    else:
        L.append("  not enough trades to choose parameters")
    L.append("\nLimits: display prices carry no size (fill size and slippage unknown); ~1 point per "
             "minute; 1 contract per trade; index reconstruction is approximate. Screening only.")
    return "\n".join(L)
