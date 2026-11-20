"""Automatic hunt: keep searching for a bot variation that meets a daily-profit target.

Each round:
  1. Backfill newly resolved markets (public data, no key). New days after the first round
     form a FORWARD set that no search ever chose on.
  2. Search every variation: the base grid of search.py (11,880 per segment) times
     7 time-of-day filters (any, or one 4-hour UTC block) times 4 volatility filters (any,
     or the low / mid / high third of the index's recent volatility, cut on period A).
     That is 332,640 variations per segment and 3,991,680 across 12 segments.
  3. Apply the luck checks of search.py, with the Bonferroni bar set for all of them:
     dev = A + B (fixed dates from the first round), positive in A and in B, positive at a
     pessimistic delay, dev z-score (no-edge null) >= bar.
  4. Rank the best passing variation per coin/window (1-5 by holdout profit per day) and
     test the request on the holdout AND on the forward days:

        portfolio of confirmed winners x `cap` contracts per trade >= `target` $/day
        on the holdout and on >= `min_forward_days` forward days, with most days positive.

  5. Write data/hunt/leaderboard.md + .json, then sleep `interval` seconds and repeat,
     until the request is met (or forever with --keep-going).

The split dates are frozen in data/hunt/state.json at the first round, so later rounds never
choose on the holdout or forward days.
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np

from .search import _arrays, _mask, _z, build_rows, configs
from .strategies import fit_model, model_probability

HOUR_BLOCKS = (None, 0, 1, 2, 3, 4, 5)        # 4-hour UTC blocks: 0 = 00-04, ..., 5 = 20-24
VOL = (None, "low", "mid", "high")


def _prep(conn, delays, state):
    data = {d: build_rows(conn, d) for d in delays}
    main = delays[0]
    ends = sorted({r["t_end"] for r in data[main]})
    if "cut_a" not in state:
        state.update(cut_a=ends[int(len(ends) * 0.50)], cut_b=ends[int(len(ends) * 0.75)],
                     freeze=ends[-1], frozen_at=datetime.now(timezone.utc).isoformat())
    cut_a, cut_b, freeze = state["cut_a"], state["cut_b"], state["freeze"]
    fits, vol_cuts = {}, {}
    for d in delays:
        by_seg = defaultdict(list)
        for r in data[d]:
            by_seg[r["seg"]].append(r)
        for seg, rs in by_seg.items():
            if d == main:
                lead_a = [r for r in rs if r["side"] == "leader" and r["t_end"] < cut_a and r["sigma"]]
                fits[seg] = fit_model(lead_a) if lead_a else (1.0, 0.0)
                sig_a = sorted(r["sigma"] for r in lead_a)
                vol_cuts[seg] = (sig_a[len(sig_a) // 3], sig_a[2 * len(sig_a) // 3]) if len(sig_a) > 30 else None
            k, basis = fits.get(seg, (1.0, 0.0))
            for r in rs:
                r["p_model"] = (model_probability(r["margin"], r["sigma"], r["t_end"], r["now"], k, basis)
                                if r["sigma"] else None)
    return data, ends, fits, vol_cuts


def _filters(a, vol_cut):
    hours = (a["t_end"] % 86400) // 14400
    out = {}
    for h in HOUR_BLOCKS:
        hm = np.ones(len(hours), bool) if h is None else hours == h
        for v in VOL:
            if v is None:
                vm = np.ones(len(hours), bool)
            elif vol_cut is None:
                continue
            else:
                s = a["sigma"]
                vm = {"low": s <= vol_cut[0], "mid": (s > vol_cut[0]) & (s <= vol_cut[1]),
                      "high": s > vol_cut[1]}[v] & ~np.isnan(s)
            out[(h, v)] = hm & vm
    return out


def _daily(pnl, days_idx, contracts=1.0):
    if not len(pnl):
        return {"days": 0}
    by = defaultdict(float)
    for d, p in zip(days_idx, pnl):
        by[int(d)] += float(p) * contracts
    v = np.array([by[k] for k in sorted(by)])
    return {"days": len(v), "mean": float(v.mean()), "worst": float(v.min()), "positive_days": float((v > 0).mean())}


def hunt_round(conn, state, theta=0.095, min_trades=100, alpha=0.05, delays=(60, 50)):
    main, pess = delays
    data, ends, fits, vol_cuts = _prep(conn, delays, state)
    cut_a, cut_b, freeze = state["cut_a"], state["cut_b"], state["freeze"]
    base = list(configs())
    segs = sorted({r["seg"] for r in data[main]})
    n_tests = len(base) * len(HOUR_BLOCKS) * len(VOL) * len(segs)
    bar = NormalDist().inv_cdf(1 - alpha / n_tests)
    span = {"hold": (freeze - cut_b) / 86400, "forward": max(ends[-1] - freeze, 0) / 86400}
    cands = []
    for seg in segs:
        rows = {d: [r for r in data[d] if r["seg"] == seg] for d in delays}
        A = {}
        for d in delays:
            a = _arrays(rows[d], theta)
            a["sigma"] = np.array([np.nan if r["sigma"] is None else r["sigma"] for r in rows[d]])
            t = a["t_end"]
            a["per"] = {"A": t < cut_a, "B": (t >= cut_a) & (t < cut_b), "dev": t < cut_b,
                        "hold": (t >= cut_b) & (t <= freeze), "fwd": t > freeze}
            a["flt"] = _filters(a, vol_cuts.get(seg))
            A[d] = a
        best = None
        am, ap = A[main], A[pess]
        for c in base:
            m0 = _mask(am, c)
            if (m0 & am["per"]["dev"]).sum() < min_trades:
                continue                     # no filter can add trades
            mp0 = _mask(ap, c)
            for key, f in am["flt"].items():
                m = m0 & f
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
                mp = mp0 & ap["flt"].get(key, np.zeros(len(mp0), bool))
                devp = ap["pnl"][mp & ap["per"]["dev"]]
                if not len(devp) or devp.mean() <= 0:
                    continue
                best = (z, c, key, m, mp)
        if not best:
            continue
        z, c, key, m, mp = best
        res = {"segment": seg, "config": dict(c, hours=key[0], vol=key[1]), "dev_z": z}
        for tag, a, mm in (("hold", am, m), ("hold_pess", ap, mp)):
            sel = mm & a["per"]["hold"]
            p = a["pnl"][sel]
            res[tag] = {"n": int(len(p)), "ev": float(p.mean()) if len(p) else None,
                        "z": _z(p, a["q"][sel]) if len(p) else 0.0, "losses": int((p < 0).sum()),
                        "per_day": float(p.sum() / span["hold"]) if span["hold"] > 0 else 0.0,
                        "_pnl": p, "_day": a["day"][sel]}
        sel = m & am["per"]["fwd"]
        p = am["pnl"][sel]
        res["forward"] = {"n": int(len(p)), "ev": float(p.mean()) if len(p) else None,
                          "per_day": float(p.sum() / span["forward"]) if span["forward"] > 0 else 0.0,
                          "_pnl": p, "_day": am["day"][sel]}
        cands.append(res)
    return {"n_tests": n_tests, "bar": bar, "span_days": span, "candidates": cands, "fits": fits}


def evaluate_request(res, cap=50, target=100.0, min_forward_days=3):
    conf = [c for c in res["candidates"]
            if c["hold"]["n"] and c["hold"]["ev"] > 0 and c["hold_pess"]["n"] and c["hold_pess"]["ev"] > 0
            and c["hold"]["z"] >= 2.0]
    ranked = sorted(res["candidates"], key=lambda c: c["hold"]["per_day"], reverse=True)

    def port(key):
        pnl = np.concatenate([c[key]["_pnl"] for c in conf]) if conf else np.array([])
        days = np.concatenate([c[key]["_day"] for c in conf]) if conf else np.array([])
        return _daily(pnl, days, cap)
    hold, fwd = port("hold"), port("forward")
    met = (bool(conf) and hold.get("days", 0) > 0 and hold["mean"] >= target and hold["positive_days"] >= 0.6
           and fwd.get("days", 0) >= min_forward_days and fwd["mean"] >= target and fwd["positive_days"] >= 0.6)
    return {"met": met, "confirmed": conf, "ranked": ranked[:5], "portfolio_hold": hold,
            "portfolio_forward": fwd, "cap": cap, "target": target, "min_forward_days": min_forward_days}


def _cfg_text(c):
    h = "any time" if c["hours"] is None else f"{c['hours'] * 4:02d}-{c['hours'] * 4 + 4:02d} UTC"
    v = "any vol" if c["vol"] is None else f"{c['vol']} vol"
    e = "" if c["edge"] is None else f", model edge >= {c['edge']:.2f}"
    return (f"buy the {c['side']} {c['offset']} s before close at ${c['lo']:.2f}-{c['hi']:.2f}, "
            f"index lead >= {c['margin_bps']:g} bps{e}, {h}, {v}")


def leaderboard(res, ev, round_no, stamp) -> str:
    L = [f"# Bot hunt leaderboard (round {round_no}, {stamp})", "",
         f"Target: at least ${ev['target']:.0f}/day with at most {ev['cap']} contracts per trade, on the holdout "
         f"and on at least {ev['min_forward_days']} new forward days. "
         f"**Met: {'YES' if ev['met'] else 'not yet'}.**", "",
         f"Variations tested: {res['n_tests']:,}. Luck bar: dev z >= {res['bar']:.2f}. "
         f"Holdout {res['span_days']['hold']:.1f} days, forward {res['span_days']['forward']:.1f} days.", "",
         "| Rank | Coin / window | Rule | Holdout trades | Losses | Profit / contract | $/day at 1 contract | "
         f"$/day at {ev['cap']} | Forward $/day at {ev['cap']} | Confirmed |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    conf = {id(c) for c in ev["confirmed"]}
    for i, c in enumerate(ev["ranked"], 1):
        h, f = c["hold"], c["forward"]
        L.append(f"| {i} | {c['segment']} | {_cfg_text(c['config'])} | {h['n']} | {h['losses']} | "
                 f"{(h['ev'] or 0) * 100:+.1f}¢ | ${h['per_day']:.2f} | ${h['per_day'] * ev['cap']:.0f} | "
                 f"{'$%.0f' % (f['per_day'] * ev['cap']) if f['n'] else 'no data yet'} | "
                 f"{'yes' if id(c) in conf else 'no'} |")
    if not ev["ranked"]:
        L.append("| - | - | no variation passed the luck checks | | | | | | | |")
    ph, pf = ev["portfolio_hold"], ev["portfolio_forward"]
    L += ["", f"**All confirmed winners together at {ev['cap']} contracts per trade:**"]
    L.append(f"- Holdout: ${ph['mean']:.0f}/day, worst day ${ph['worst']:.0f}, {ph['positive_days']:.0%} of "
             f"{ph['days']} days positive." if ph.get("days") else "- Holdout: none.")
    L.append(f"- Forward: ${pf['mean']:.0f}/day, worst day ${pf['worst']:.0f}, {pf['positive_days']:.0%} of "
             f"{pf['days']} days positive." if pf.get("days") else
             f"- Forward: no new days yet (need {ev['min_forward_days']}).")
    L += ["", "Display prices carry no size: fills at that size are assumed, not proven. Not financial advice."]
    return "\n".join(L)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def run_hunt(db_path: Path, out_dir: Path, cap=50, target=100.0, interval=3600, keep_going=False,
             max_rounds=None, log=print):
    from . import db as dbm
    from .backfill import SCHEMA, Backfill
    out_dir.mkdir(parents=True, exist_ok=True)
    state_f = out_dir / "state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {"rounds": 0}
    while True:
        conn = dbm.connect(db_path)
        conn.executescript(SCHEMA)
        try:
            Backfill(conn, assets=("btc", "eth", "sol", "xrp"), horizons=("5m", "15m", "1h"), days=2,
                     rps=12, workers=6).run(progress_every=10**9)
        except Exception as exc:               # keep hunting on the data we have
            log(f"backfill failed: {exc}")
        res = hunt_round(conn, state)
        ev = evaluate_request(res, cap=cap, target=target)
        state["rounds"] += 1
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        md = leaderboard(res, ev, state["rounds"], stamp)
        (out_dir / "leaderboard.md").write_text(md)
        (out_dir / "leaderboard.json").write_text(json.dumps(_clean({"round": state["rounds"], "at": stamp,
                                                                     "met": ev["met"], "result": res,
                                                                     "evaluation": ev}), default=str, indent=1))
        state_f.write_text(json.dumps(state, indent=1))
        with open(out_dir / "history.log", "a") as h:
            ph, pf = ev["portfolio_hold"], ev["portfolio_forward"]
            h.write(f"{stamp} round {state['rounds']} winners {len(ev['confirmed'])} "
                    f"hold ${ph.get('mean', 0):.0f}/day fwd ${pf.get('mean', 0):.0f}/day "
                    f"({pf.get('days', 0)} days) met={ev['met']}\n")
        log(md)
        conn.close()
        if (ev["met"] and not keep_going) or (max_rounds and state["rounds"] >= max_rounds):
            return ev
        time.sleep(interval)
