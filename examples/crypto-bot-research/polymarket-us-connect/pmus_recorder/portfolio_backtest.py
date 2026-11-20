"""Backtest of the hunt's portfolio from a $1,000 bankroll, day by day, with stress tests.

Bots (the two confirmed by the hunt, settings fixed in advance):
  1. arb_repeat      cross-window arbitrage pairs, every cheap minute (strategies_cross.py)
  2. xrp_1h_leader   XRP 1h: 60 s before close buy the index leader at $0.02-0.98 when it leads
                     by >= 5 bps and the volatility model's edge >= 0 (model fitted on period A)

Periods (frozen by the hunt): dev = first 75% of dates, where the settings were CHOSEN (in-sample,
so optimistic), holdout = the next dates, never used to choose, forward = days after the freeze.

Stress tests (each applied on its own, then all together):
  slippage   +1 cent per contract on every leg bought (arbitrage pays it twice)
  fees       taker fee x 1.5
  size       at most 25 contracts per trade instead of 50
  losses     the XRP bot loses its whole stake on 1 trade in 30 (backtest showed ~0 losses)
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import study
from .bankroll import replay
from .search import _arrays, _mask, build_rows
from .settlement import taker_fee
from .strategies import fit_model, model_probability
from .strategies_cross import load_groups, pair_trades

XRP_RULE = {"offset": 60, "side": "leader", "lo": 0.02, "hi": 0.98, "margin_bps": 5.0, "edge": 0.0}


def xrp_trades(conn, state, theta=0.095, fee_mult=1.0):
    rows = [r for r in build_rows(conn, 60) if r["seg"] == "xrp 1h"]
    lead_a = [r for r in rows if r["side"] == "leader" and r["t_end"] < state["cut_a"] and r["sigma"]]
    k, basis = fit_model(lead_a)
    for r in rows:
        r["p_model"] = (model_probability(r["margin"], r["sigma"], r["t_end"], r["now"], k, basis)
                        if r["sigma"] else None)
    a = _arrays(rows, theta * fee_mult)
    m = _mask(a, XRP_RULE)
    out = []
    for te, off, price, won in zip(a["t_end"][m], a["offset"][m], a["price"][m], a["won"][m]):
        fee = taker_fee(price, theta=theta * fee_mult)
        out.append({"bot": "xrp_1h_leader", "entry": int(te - off), "end": int(te + 60), "t_end": int(te),
                    "cost": price + fee, "pnl": won - price - fee, "legs": 1})
    return out


def arb_trades(conn, theta=0.095, fee_mult=1.0):
    study.PRICE_DELAY_S = 60
    out = []
    for t in pair_trades(load_groups(conn), theta=theta * fee_mult, max_cost=1.0, repeat=True):
        out.append({"bot": "arb_repeat", "entry": t["t"], "end": t["t_end"] + 60, "t_end": t["t_end"],
                    "cost": t["cost"], "pnl": t["pnl"], "legs": 2})
    return out


def _period(t_end, state):
    if t_end < state["cut_b"]:
        return "dev"
    return "holdout" if t_end <= state["freeze"] else "forward"


def _run(trades, state, start, cap, slip=0.0, lose_every=0):
    tr, i = [], 0
    for t in sorted(trades, key=lambda t: t["entry"]):
        cost, pnl = t["cost"] + slip * t["legs"], t["pnl"] - slip * t["legs"]
        if lose_every and t["bot"] == "xrp_1h_leader":
            i += 1
            if i % lose_every == 0:
                pnl = -cost
        tr.append((t["entry"], t["end"], cost, pnl, "arb" if t["bot"] == "arb_repeat" else "bet", t))
    res = {}
    for name, sel in (("all", lambda t: True), ("holdout", lambda t: _period(t["t_end"], state) == "holdout"),
                      ("forward", lambda t: _period(t["t_end"], state) == "forward")):
        res[name] = replay([x[:5] for x in tr if sel(x[5])], start=start, cap=cap)
    return res


def daily_table(trades, state, start=1000.0, cap=50):
    """Day-by-day equity from `start`, sizing as bankroll.replay, over all periods."""
    from .bankroll import MAX_FRAC
    import heapq
    import math
    cash, open_stake, pending = float(start), 0.0, []
    day_rows = defaultdict(lambda: {"trades": 0, "contracts": 0, "pnl": 0.0, "bots": defaultdict(float)})
    for t in sorted(trades, key=lambda t: t["entry"]):
        while pending and pending[0][0] <= t["entry"]:
            s, payout, stake, bot = heapq.heappop(pending)
            cash += payout
            open_stake -= stake
            d = day_rows[int(s // 86400)]
            d["pnl"] += payout - stake
            d["bots"][bot] += payout - stake
        equity = cash + open_stake
        kind = "arb" if t["bot"] == "arb_repeat" else "bet"
        k = min(cap, math.floor(min(cash, MAX_FRAC[kind] * equity) / t["cost"] + 1e-9))
        if k < 1:
            continue
        cash -= k * t["cost"]
        open_stake += k * t["cost"]
        heapq.heappush(pending, (t["end"], k * (t["cost"] + t["pnl"]), k * t["cost"], t["bot"]))
        d = day_rows[int(t["end"] // 86400)]
        d["trades"] += 1
        d["contracts"] += k
    while pending:
        s, payout, stake, bot = heapq.heappop(pending)
        cash += payout
        d = day_rows[int(s // 86400)]
        d["pnl"] += payout - stake
        d["bots"][bot] += payout - stake
    out, eq = [], float(start)
    for day in sorted(day_rows):
        r = day_rows[day]
        eq += r["pnl"]
        out.append({"day": day, "period": _period(day * 86400 + 43200, state), "trades": r["trades"],
                    "contracts": r["contracts"], "pnl": r["pnl"], "arb": r["bots"]["arb_repeat"],
                    "xrp": r["bots"]["xrp_1h_leader"], "equity": eq})
    return out


def run_backtest(conn, state, start=1000.0, cap=50, theta=0.095):
    base = xrp_trades(conn, state, theta) + arb_trades(conn, theta)
    fees = xrp_trades(conn, state, theta, 1.5) + arb_trades(conn, theta, 1.5)
    scen = {
        "base": _run(base, state, start, cap),
        "slippage 1c/leg": _run(base, state, start, cap, slip=0.01),
        "fees x1.5": _run(fees, state, start, cap),
        "25-contract cap": _run(base, state, start, 25),
        "1 loss in 30 (XRP)": _run(base, state, start, cap, lose_every=30),
        "all stresses": _run(fees, state, start, 25, slip=0.01, lose_every=30),
    }
    per_bot = {b: _run([t for t in base if t["bot"] == b], state, start, cap) for b in ("arb_repeat", "xrp_1h_leader")}
    return {"start": start, "cap": cap, "scenarios": scen, "per_bot": per_bot,
            "daily": daily_table(base, state, start, cap), "n_trades": len(base)}


def format_backtest(res) -> str:
    from datetime import datetime, timezone
    L = [f"# Portfolio Backtest from ${res['start']:,.0f}", "",
         "Bots: arbitrage repeat (all coins) + XRP 1h leader. At most "
         f"{res['cap']} contracts per trade, 5% of the balance per bet, 10% per arbitrage buy, winnings reinvested.",
         "", "**Dev** dates are where the settings were chosen (in-sample, optimistic). **Holdout** dates were never "
         "used to choose. Each period is replayed from a fresh $1,000.", ""]
    L += ["| Scenario | All 45 days: end balance | $/day | Holdout: end balance | $/day | Worst holdout day | "
          "Holdout days positive |", "|---|---|---|---|---|---|---|"]
    for name, r in res["scenarios"].items():
        a, h = r["all"], r["holdout"]
        L.append(f"| {name} | ${a['end']:,.0f} | ${a['per_day']:,.0f} | ${h['end']:,.0f} | ${h['per_day']:,.0f} | "
                 f"${h['worst_day']:,.0f} | {h['positive_days']:.0%} |")
    L += ["", "| Bot alone (base) | All 45 days: end balance | $/day | Holdout $/day | Trades (all) | Avg contracts |",
          "|---|---|---|---|---|---|"]
    for b, r in res["per_bot"].items():
        L.append(f"| {b} | ${r['all']['end']:,.0f} | ${r['all']['per_day']:,.0f} | ${r['holdout']['per_day']:,.0f} | "
                 f"{r['all']['trades']} | {r['all']['avg_contracts']:.0f} |")
    L += ["", "## Day by day (base scenario, one $1,000 account over all 45 days)", "",
          "| Date (UTC) | Period | Trades | Contracts | Arbitrage P&L | XRP P&L | Day P&L | Balance |",
          "|---|---|---|---|---|---|---|---|"]
    for d in res["daily"]:
        date = datetime.fromtimestamp(d["day"] * 86400, timezone.utc).strftime("%Y-%m-%d")
        L.append(f"| {date} | {d['period']} | {d['trades']} | {d['contracts']} | ${d['arb']:+,.2f} | ${d['xrp']:+,.2f} | "
                 f"${d['pnl']:+,.2f} | ${d['equity']:,.2f} |")
    L += ["", "Display prices carry no size, so fills of up to 50 contracts are assumed, not proven. Arbitrage "
          "assumes both legs fill at the quoted prices. Not financial advice."]
    return "\n".join(L)


def main(db: Path, state_path: Path, out: Path | None, start=1000.0, cap=50):
    import sqlite3
    state = json.loads(state_path.read_text())
    res = run_backtest(sqlite3.connect(str(db)), state, start, cap)
    md = format_backtest(res)
    if out:
        out.write_text(md)
    return md
