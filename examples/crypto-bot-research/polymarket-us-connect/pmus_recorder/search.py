"""Large, luck-resistant variation search on the backfilled public data.

Searching many variations finds winners by chance, so a variation only counts if it clears
every one of these, decided BEFORE looking at the final holdout:

  1. Time split (global dates): first 50% = A, next 25% = B (together "dev"), last 25% =
     HOLDOUT. The model is fitted on A only. The holdout is used once, at the very end.
  2. Positive EV per contract in A and in B separately, with at least `min_trades` dev trades.
  3. Positive dev EV under a PESSIMISTIC price delay as well as the measured one. Measured
     against live quotes, a /v1/price-history point is the quote 60 s after its timestamp;
     50 s (prices look fresher, index-following looks worse) is the pessimistic check.
  4. Dev z-score above the Bonferroni bar for the number of variations tried (one-sided, 5%
     family-wise): 11,880 variations x 12 segments = 142,560 tries, about z >= 4.96.
     The z-score uses the NO-EDGE variance: under "no edge" a trade bought at price p with fee f
     wins with probability q = p + f, so z = sum(won - q) / sqrt(sum(q (1 - q))). A sample
     t-stat is wrong for 95-98c favourites: with no loss yet its variance is ~0 and t explodes.

Per coin/window segment, the passing variation with the highest dev t-stat is kept, then the
kept set is scored once on the HOLDOUT at both delays, with P&L per day.

Variation space, per segment (every combination):
  decision time   offset 60 / 120 / 180 s (as in the backtest; real time = offset + ~30 s)
  side            the index leader, or the other side
  price band      [lo, hi] from {0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.98}
  index margin    at least 0 / 2 / 5 / 10 / 20 bps
  model edge      none, or (model prob of the side) - price - fee >= 0 / 0.02 / 0.04 / 0.06 / 0.10
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import product
from statistics import NormalDist

import numpy as np

from . import study
from .settlement import projected_close, taker_fee
from .strategies import _sigma, fit_model, model_probability

OFFSETS = (60, 120, 180)
BANDS = (0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.98)
MARGINS = (0.0, 2.0, 5.0, 10.0, 20.0)
EDGES = (None, 0.0, 0.02, 0.04, 0.06, 0.10)
SIDES = ("leader", "other")


def build_rows(conn, delay: int):
    """Decision rows for both sides at every offset, with all features. No outcome is used
    except to score `won`."""
    study.PRICE_DELAY_S = delay
    markets, ticks, points = study.load(conn)
    rows = []
    for slug, asset, horizon, we, ptb, close, out in markets:
        t_end = int(round(we))
        full = ticks.get(asset, {})
        tk = {t: full[t] for t in range(t_end - max(OFFSETS) - 200, t_end) if t in full}
        for d in OFFSETS:
            pt = study.decision_point(points.get(slug, []), t_end - d)
            if not pt:
                continue
            now, up, down = pt
            if up is None or down is None:
                continue
            est = projected_close(tk, t_end, now)
            if est is None:
                continue
            margin = (est - ptb) / ptb
            leader_up = margin >= 0
            sig = _sigma(tk, now)
            for side in SIDES:
                side_up = leader_up if side == "leader" else not leader_up
                rows.append({"seg": f"{asset} {horizon}", "t_end": t_end, "offset": d, "side": side,
                             "now": now, "margin": margin, "sigma": sig,
                             "margin_bps": abs(margin) * 1e4, "price": up if side_up else down,
                             "won": side_up == (out == "UP")})
    return rows


def _arrays(rows, theta):
    a = {k: np.array([r[k] for r in rows]) for k in ("t_end", "offset", "margin_bps", "price")}
    a["side"] = np.array([r["side"] == "leader" for r in rows])
    a["won"] = np.array([r["won"] for r in rows], dtype=float)
    a["p_side"] = np.array([np.nan if r.get("p_model") is None else
                            (r["p_model"] if r["side"] == "leader" else 1 - r["p_model"]) for r in rows])
    fee = np.array([taker_fee(p, theta=theta) for p in a["price"]])
    a["fee"] = fee
    a["pnl"] = a["won"] - a["price"] - fee
    a["q"] = a["price"] + fee                    # break-even win probability
    a["buyable"] = (a["price"] > 0) & (a["price"] < study.UNBUYABLE_AT_OR_ABOVE)
    a["day"] = (a["t_end"] // 86400).astype(int)
    return a


def configs():
    for o, s, lo, hi, m, e in product(OFFSETS, SIDES, BANDS, BANDS, MARGINS, EDGES):
        if lo < hi:
            yield {"offset": o, "side": s, "lo": lo, "hi": hi, "margin_bps": m, "edge": e}


def _mask(a, c):
    m = (a["offset"] == c["offset"]) & (a["side"] == (c["side"] == "leader")) & a["buyable"]
    m &= (a["price"] >= c["lo"]) & (a["price"] <= c["hi"]) & (a["margin_bps"] >= c["margin_bps"])
    if c["edge"] is not None:
        m &= np.nan_to_num(a["p_side"] - a["price"] - a["fee"], nan=-1.0) >= c["edge"]
    return m


def _t(p):
    n = len(p)
    if n < 2:
        return 0.0
    s = p.std(ddof=1)
    return float(p.mean() / (s / math.sqrt(n))) if s > 0 else 0.0


def _z(p, q):
    """z-score of total P&L against the no-edge null (win probability q = price + fee)."""
    v = float((q * (1 - q)).sum())
    return float(p.sum() / math.sqrt(v)) if v > 0 else 0.0


def _score(p, q, days):
    if not len(p):
        return {"n": 0}
    return {"n": int(len(p)), "ev": float(p.mean()), "total": float(p.sum()), "t": _z(p, q),
            "losses": int((p < 0).sum()), "per_day": float(p.sum() / days)}


def run_search(conn, theta=0.095, min_trades=100, alpha=0.05, delays=(60, 50)):
    main, pess = delays
    data = {d: build_rows(conn, d) for d in delays}
    ends = sorted({r["t_end"] for r in data[main]})
    cut_a, cut_b = ends[int(len(ends) * 0.50)], ends[int(len(ends) * 0.75)]
    span_days = {k: v / 86400 for k, v in {"A": cut_a - ends[0], "B": cut_b - cut_a,
                                         "dev": cut_b - ends[0], "hold": ends[-1] - cut_b}.items()}

    # model fit per segment on period A only (main delay), applied to both delays
    fits = {}
    for d in delays:
        by_seg = defaultdict(list)
        for r in data[d]:
            by_seg[r["seg"]].append(r)
        for seg, rs in by_seg.items():
            if d == main:
                lead_a = [r for r in rs if r["side"] == "leader" and r["t_end"] < cut_a and r["sigma"]]
                for r in lead_a:
                    r["won_leader"] = r["won"]
                fits[seg] = fit_model([dict(r, won=r["won"]) for r in lead_a]) if lead_a else (1.0, 0.0)
            k, basis = fits.get(seg, (1.0, 0.0))
            for r in rs:
                r["p_model"] = (model_probability(r["margin"], r["sigma"], r["t_end"], r["now"], k, basis)
                                if r["sigma"] else None)

    cfgs = list(configs())
    segs = sorted({r["seg"] for r in data[main]})
    n_tests = len(cfgs) * len(segs)
    t_bar = NormalDist().inv_cdf(1 - alpha / n_tests)

    out = {"delays": delays, "n_tests": n_tests, "t_bar": t_bar, "days": span_days, "segments": {}, "fits": fits}
    hold_daily = defaultdict(float)
    hold_daily_pess = defaultdict(float)
    for seg in segs:
        A = {d: _arrays([r for r in data[d] if r["seg"] == seg], theta) for d in delays}
        per = {}
        for d in delays:
            t = A[d]["t_end"]
            per[d] = {"A": t < cut_a, "B": (t >= cut_a) & (t < cut_b), "dev": t < cut_b, "hold": t >= cut_b}
        passing, best_any = [], None
        for c in cfgs:
            m = _mask(A[main], c)
            dsel = m & per[main]["dev"]
            dev = A[main]["pnl"][dsel]
            if len(dev) < min_trades or dev.mean() <= 0:
                continue
            tdev = _z(dev, A[main]["q"][dsel])
            if best_any is None or tdev > best_any[0]:
                best_any = (tdev, c)
            pa = A[main]["pnl"][m & per[main]["A"]]
            pb = A[main]["pnl"][m & per[main]["B"]]
            if not len(pa) or not len(pb) or pa.mean() <= 0 or pb.mean() <= 0:
                continue
            mp = _mask(A[pess], c)
            devp = A[pess]["pnl"][mp & per[pess]["dev"]]
            if not len(devp) or devp.mean() <= 0:
                continue
            passing.append((tdev, c))
        seg_out = {"tested": len(cfgs), "passed_all_but_bar": len(passing),
                   "best_dev_t_any": round(best_any[0], 2) if best_any else None}
        winners = [p for p in passing if p[0] >= t_bar]
        seg_out["passed_bar"] = len(winners)
        if winners:
            tdev, c = max(winners, key=lambda x: x[0])
            res = {"config": c, "dev_t": tdev}
            for d, tag in ((main, "hold"), (pess, "hold_pessimistic")):
                m = _mask(A[d], c)
                sel = m & per[d]["hold"]
                res[tag] = _score(A[d]["pnl"][sel], A[d]["q"][sel], span_days["hold"])
                for day, p in zip(A[d]["day"][sel], A[d]["pnl"][sel]):
                    (hold_daily if d == main else hold_daily_pess)[int(day)] += float(p)
            m = _mask(A[main], c)
            res["dev"] = _score(A[main]["pnl"][m & per[main]["dev"]], A[main]["q"][m & per[main]["dev"]],
                                span_days["dev"])
            seg_out["winner"] = res
        elif passing:   # best that passed everything except the Bonferroni bar (shown, not used)
            tdev, c = max(passing, key=lambda x: x[0])
            m = _mask(A[main], c)
            seg_out["best_below_bar"] = {"config": c, "dev_t": tdev,
                                         "dev": _score(A[main]["pnl"][m & per[main]["dev"]],
                                                       A[main]["q"][m & per[main]["dev"]], span_days["dev"])}
        out["segments"][seg] = seg_out

    def daily(dd):
        v = np.array([dd[k] for k in sorted(dd)]) if dd else np.array([])
        if not len(v):
            return None
        return {"days": len(v), "mean": float(v.mean()), "worst": float(v.min()), "best": float(v.max()),
                "positive_days": float((v > 0).mean()), "t": _t(v)}
    out["portfolio_hold_daily"] = daily(hold_daily)
    out["portfolio_hold_daily_pessimistic"] = daily(hold_daily_pess)
    return out


def format_search(res, target=(100.0, 200.0)) -> str:
    L = ["Variation search (public Polymarket US data; luck-resistant rules)", "=" * 74,
         f"variations tested: {res['n_tests']:,}   Bonferroni bar: dev z >= {res['t_bar']:.2f}",
         f"days: A {res['days']['A']:.1f}, B {res['days']['B']:.1f}, holdout {res['days']['hold']:.1f}", ""]
    L.append(f"  {'segment':9s} {'pass*':>6s} {'bar':>4s} {'best z':>6s}  result")
    for seg, s in res["segments"].items():
        head = f"  {seg:9s} {s['passed_all_but_bar']:>6d} {s['passed_bar']:>4d} {str(s['best_dev_t_any']):>6s}  "
        if "winner" in s:
            w = s["winner"]
            c = w["config"]
            h, hp = w["hold"], w["hold_pessimistic"]
            hev = f"{h['ev'] * 100:+.1f}c" if h.get("n") else "none"
            hpev = f"{hp['ev'] * 100:+.1f}c" if hp.get("n") else "none"
            L.append(head + f"WINNER {c['side']} @{c['offset']}s px {c['lo']}-{c['hi']} m>={c['margin_bps']} "
                     f"edge>={c['edge']} | dev z {w['dev_t']:.1f} | HOLDOUT n {h.get('n', 0)} EV {hev} "
                     f"z {h.get('t', 0):.1f} losses {h.get('losses', 0)} ${h.get('per_day', 0):.2f}/day/contract (pessimistic: {hpev})")
        elif "best_below_bar" in s:
            b = s["best_below_bar"]
            c = b["config"]
            L.append(head + f"no winner; best below bar: {c['side']} @{c['offset']}s px {c['lo']}-{c['hi']} "
                     f"m>={c['margin_bps']} edge>={c['edge']} dev z {b['dev_t']:.1f} EV {b['dev']['ev'] * 100:+.1f}c")
        else:
            L.append(head + "no variation passed the basic checks")
    for tag, label in (("portfolio_hold_daily", f"{res['delays'][0]} s delay"), ("portfolio_hold_daily_pessimistic", f"{res['delays'][1]} s delay")):
        p = res.get(tag)
        if p:
            lo = target[0] / p["mean"] if p["mean"] > 0 else float("inf")
            hi = target[1] / p["mean"] if p["mean"] > 0 else float("inf")
            L.append(f"\nWinners combined, HOLDOUT, {label}, 1 contract per trade: "
                     f"${p['mean']:.2f}/day (worst day ${p['worst']:.2f}, best ${p['best']:.2f}, "
                     f"{p['positive_days']:.0%} of {p['days']} days positive, daily t {p['t']:.1f})")
            L.append(f"  contracts per trade needed for ${target[0]:.0f}-${target[1]:.0f}/day: "
                     f"{lo:.0f}-{hi:.0f}" if math.isfinite(lo) else "  no positive daily mean")
    L.append("\npass* = passed every check except the Bonferroni bar; bar = also passed the bar;\n"
             "best z = highest dev z-score (no-edge null) of any variation with positive dev EV (before the other checks).\n"
             "Display prices carry no size: whether that many contracts could be bought is unknown.")
    return "\n".join(L)
