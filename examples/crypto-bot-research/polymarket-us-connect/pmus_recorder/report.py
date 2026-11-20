"""Coverage and first-look late-window statistics from a recording.

This is a diagnostic, not a backtest: it assumes you could buy one contract at the
recorded best offer at the snapshot time (no queue, no latency, no depth impact).
Treat its numbers as an upper bound on what a live strategy could capture.
"""

from __future__ import annotations

import json
from collections import defaultdict

from .settlement import projected_close, taker_fee, window_average

BUCKETS = [(120, 90), (90, 60), (60, 30), (30, 10), (10, 0)]


def _bucket(secs: float) -> str | None:
    for hi, lo in BUCKETS:
        if lo <= secs < hi:
            return f"{hi}-{lo}s"
    return None


def build_report(conn, max_ask: float = 0.98, theta: float = 0.095) -> dict:
    markets = conn.execute(
        "SELECT slug, asset, horizon, window_start, window_end, price_to_beat, settlement_price, "
        "contract_settlement, outcome FROM markets").fetchall()
    ticks_by_asset: dict[str, dict[int, float]] = defaultdict(dict)
    for asset, ts, close in conn.execute("SELECT asset, ts, close FROM index_ticks"):
        ticks_by_asset[asset][ts] = close

    rep: dict = {"coverage": {}, "settlement_check": [], "late_window": {}, "notes": []}
    cov = rep["coverage"]
    cov["markets_seen"] = len(markets)
    cov["markets_settled"] = sum(1 for m in markets if m[8])
    cov["book_snapshots"] = conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0]
    cov["index_ticks"] = conn.execute("SELECT COUNT(*) FROM index_ticks").fetchone()[0]
    by_src = dict(conn.execute("SELECT COALESCE(source,'rest'), COUNT(*) FROM book_snapshots GROUP BY 1"))
    cov["book_snapshots_live_ws"] = by_src.get("ws", 0)
    cov["book_snapshots_rest_cached"] = by_src.get("rest", 0)
    cov["trades"] = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    cov["errors"] = conn.execute("SELECT COUNT(*) FROM events WHERE level='ERROR'").fetchone()[0]
    cov["median_book_latency_ms"] = conn.execute(
        "SELECT latency_ms FROM book_snapshots WHERE latency_ms IS NOT NULL ORDER BY latency_ms LIMIT 1 "
        "OFFSET (SELECT COUNT(*)/2 FROM book_snapshots WHERE latency_ms IS NOT NULL)").fetchone()
    cov["median_book_latency_ms"] = cov["median_book_latency_ms"][0] if cov["median_book_latency_ms"] else None

    # late-window study, per horizon and seconds-to-close bucket. Live websocket books are
    # used when present; CDN-cached REST books (up to 30 s stale) only as a labelled fallback.
    use_src = "ws" if cov["book_snapshots_live_ws"] else "rest"
    rep["late_window_source"] = use_src
    agg = defaultdict(lambda: {"snapshots": 0, "leader_won": 0, "leader_ask_avail": 0,
                               "ask_sum": 0.0, "ev_sum": 0.0, "ev_n": 0})
    for slug, asset, horizon, ws, we, ptb, close, contract, out in markets:
        ticks = ticks_by_asset.get(asset, {})
        t_end = int(round(we))
        if close is not None:
            avg, n = window_average(ticks, t_end)
            rep["settlement_check"].append({
                "slug": slug, "official_close": close, "recorded_avg": avg, "ticks": n,
                "error": None if avg is None else round(avg - close, 4)})
        if not out or ptb is None:
            continue
        snaps = conn.execute(
            "SELECT ts, secs_to_close, best_bid, best_ask, bids_json, offers_json FROM book_snapshots "
            "WHERE slug=? AND secs_to_close < 120 AND secs_to_close >= 0 AND COALESCE(source,'rest')=? "
            "ORDER BY ts", (slug, use_src)).fetchall()
        for ts, secs, best_bid, best_ask, _bj, _oj in snaps:
            b = _bucket(secs)
            est = projected_close(ticks, t_end, int(ts))
            if b is None or est is None:
                continue
            leader = "UP" if est >= ptb else "DOWN"
            # price to BUY the leader: UP -> best Up offer; DOWN -> 1 - best Up bid
            ask = best_ask if leader == "UP" else (None if best_bid is None else round(1 - best_bid, 4))
            a = agg[(horizon, b)]
            a["snapshots"] += 1
            won = leader == out
            a["leader_won"] += won
            if ask is not None and ask <= max_ask:
                a["leader_ask_avail"] += 1
                a["ask_sum"] += ask
                a["ev_sum"] += (1.0 if won else 0.0) - ask - taker_fee(ask, theta=theta)
                a["ev_n"] += 1
    for (horizon, b), a in sorted(agg.items()):
        n = a["snapshots"]
        rep["late_window"][f"{horizon} {b}"] = {
            "snapshots": n,
            "leader_win_rate": round(a["leader_won"] / n, 4) if n else None,
            f"leader_ask<={max_ask}_share": round(a["leader_ask_avail"] / n, 4) if n else None,
            "avg_leader_ask": round(a["ask_sum"] / a["ev_n"], 4) if a["ev_n"] else None,
            "naive_ev_per_contract_after_taker_fee": round(a["ev_sum"] / a["ev_n"], 4) if a["ev_n"] else None,
        }
    if use_src == "rest":
        rep["notes"].insert(0, "LATE-WINDOW TABLE USES CDN-CACHED REST BOOKS (up to 30 s stale). Prices "
                            "in it are NOT what you could have traded. Record with an API key (live "
                            "websocket) before drawing any conclusion.")
    if rep["settlement_check"]:
        errs = [abs(c["error"]) for c in rep["settlement_check"] if c["error"] is not None]
        if errs and max(errs) > 0.01:
            rep["notes"].append("The public 1-second index candles reproduce official closes only "
                                f"approximately (max error {max(errs):.2f}); treat closes within that "
                                "distance of priceToBeat as uncertain.")
    if cov["markets_settled"] < 200:
        rep["notes"].append(f"Only {cov['markets_settled']} settled markets: far too few to conclude "
                            "anything. Record 1-2 weeks before trusting these numbers.")
    rep["notes"].append("Naive EV assumes a fill at the recorded best offer with no latency or queue; "
                        "it is an upper bound, not a backtest.")
    return rep


def format_report(rep: dict) -> str:
    out = ["Recording report", "=" * 60]
    for k, v in rep["coverage"].items():
        out.append(f"  {k:28s} {v}")
    checks = [c for c in rep["settlement_check"] if c["error"] is not None]
    if checks:
        errs = [abs(c["error"]) for c in checks]
        out.append(f"\nSettlement reproduction (recorded 60 s index average vs official close): "
                   f"{len(checks)} markets, max |error| {max(errs):.4f}")
        for c in checks[-5:]:
            out.append(f"  {c['slug']}: official {c['official_close']} recorded {c['recorded_avg']} "
                       f"({c['ticks']}/60 ticks) error {c['error']}")
    if rep["late_window"]:
        out.append(f"\nLate-window leader study (per snapshot, book source: {rep.get('late_window_source')}):")
        out.append(f"  {'bucket':18s} {'snaps':>6s} {'leader WR':>10s} {'ask ok':>8s} {'avg ask':>8s} {'naive EV':>9s}")
        for k, v in rep["late_window"].items():
            vals = list(v.values())
            fmt = lambda x: "-" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))
            out.append(f"  {k:18s} {vals[0]:>6d} {fmt(vals[1]):>10s} {fmt(vals[2]):>8s} "
                       f"{fmt(vals[3]):>8s} {fmt(vals[4]):>9s}")
    for n in rep["notes"]:
        out.append(f"\nNote: {n}")
    return "\n".join(out)


def to_json(rep: dict) -> str:
    return json.dumps(rep, indent=2, default=str)
