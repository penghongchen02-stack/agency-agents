"""Export one row per bot and coin (backtest + live paper results) as JSON for a dashboard.

    python -m pmus_recorder dashboard-export --db data/paper.sqlite --out bots.json

Output: {"rows": [...], "meta": [...]}; meta carries this file's own code so the numbers
can be checked and rerun.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .paper import BOTS, SCHEMA


def _settings(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items())


def export_rows(conn: sqlite3.Connection, bots=BOTS) -> list[dict]:
    conn.executescript(SCHEMA)
    rows = []
    for b in bots:
        markets = conn.execute("SELECT COUNT(*) FROM paper_markets WHERE asset=? AND horizon=? AND settled=1",
                               (b.asset, b.horizon)).fetchone()[0]
        trades = conn.execute("SELECT t.price, t.contracts, t.pnl FROM paper_trades t JOIN paper_markets m "
                              "ON m.slug = t.slug WHERE t.bot=? AND m.asset=? AND m.horizon=?",
                              (b.name, b.asset, b.horizon)).fetchall()
        done = [t for t in trades if t[2] is not None]
        contracts = sum(t[1] for t in done)
        total = sum(t[2] for t in done)
        rows.append({
            "bot": b.name,
            "kind": "Variant" if b.variant_of else "Original",
            "built_from": b.variant_of or "",
            "coin": b.asset.upper(),
            "window": b.horizon,
            "settings": _settings(b.params),
            "backtest_ev_cents": round(b.backtest_ev * 100, 2),
            "paper_markets": markets,
            "paper_trades": len(done),
            "paper_open": len(trades) - len(done),
            "paper_contracts": contracts,
            "paper_wins": sum(1 for t in done if t[2] > 0),
            "paper_total_usd": round(total, 4),
            "paper_ev_cents": round(total / contracts * 100, 2) if contracts else None,
        })
    return rows


def export(db: Path, out: Path) -> dict:
    conn = sqlite3.connect(str(db))
    rows = export_rows(conn)
    first, last = conn.execute("SELECT MIN(ts), MAX(ts) FROM paper_quotes").fetchone()
    doc = {"rows": rows, "meta": [
        {"label": "dashboard_export.py", "value": Path(__file__).read_text(), "type": "code", "lang": "python"},
        {"label": "Input", "value": db.name},
        {"label": "Paper data from", "value": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(first)) if first else "none"},
        {"label": "Paper data to", "value": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(last)) if last else "none"},
        {"label": "Backtest", "value": "45-day walk-forward, test period = last 1/3, 90 s price delay "
                                       "(RESULTS-2026-11-20-all-strategies.md)"},
    ]}
    out.write_text(json.dumps(doc, indent=1))
    return doc
