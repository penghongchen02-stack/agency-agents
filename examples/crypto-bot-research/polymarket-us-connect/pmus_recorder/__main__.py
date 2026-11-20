"""CLI.

  python -m pmus_recorder record [--db data/pmus.sqlite] [--assets btc] [--horizons 15m,1h] [--duration 3600]
  python -m pmus_recorder report [--db data/pmus.sqlite] [--json]

Recording uses public endpoints, plus the live markets websocket when API keys are set.
It never trades.
"""

from __future__ import annotations

import argparse
import queue
import sys
from pathlib import Path

from pmus_connect.config import load_credentials

from . import db
from .recorder import Config, Recorder
from .report import build_report, format_report, to_json

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "pmus.sqlite"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pmus_recorder", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="record order books, index ticks, and settlements")
    rec.add_argument("--db", type=Path, default=DEFAULT_DB)
    rec.add_argument("--assets", default="btc", help="comma list: btc,eth,sol,xrp")
    rec.add_argument("--horizons", default="15m,1h", help="comma list: 5m,15m,1h,1d")
    rec.add_argument("--duration", type=float, help="seconds to run (default: until Ctrl-C)")
    rec.add_argument("--fast-window", type=float, default=180.0,
                     help="seconds before close to poll books every second")
    rec.add_argument("--rps", type=float, default=8.0, help="max requests/second (exchange limit 25)")
    rec.add_argument("--no-ws", action="store_true",
                     help="do not use the live websocket even if API keys are set")
    bf = sub.add_parser("backfill", help="download past resolved markets from public data (no key)")
    bf.add_argument("--db", type=Path, default=DEFAULT_DB)
    bf.add_argument("--assets", default="btc")
    bf.add_argument("--horizons", default="15m,1h")
    bf.add_argument("--days", type=float, default=45)
    bf.add_argument("--rps", type=float, default=12.0, help="max requests/second (public limit 20)")
    bf.add_argument("--workers", type=int, default=8, help="parallel requests in flight")
    st = sub.add_parser("study", help="test the late-window leader strategy on backfilled data")
    st.add_argument("--db", type=Path, default=DEFAULT_DB)
    st.add_argument("--price-delay", type=int, default=60,
                    help="seconds a /v1/price-history point lags its timestamp (measured: 60)")
    st.add_argument("--theta", type=float, default=0.095, help="taker fee coefficient (Tier 1 = 0.095)")
    st.add_argument("--json", action="store_true")
    cp = sub.add_parser("compare", help="compare strategy families per asset/horizon (walk-forward)")
    cp.add_argument("--db", type=Path, default=DEFAULT_DB)
    cp.add_argument("--price-delay", type=int, default=60,
                    help="seconds a /v1/price-history point lags its timestamp (measured: 60)")
    cp.add_argument("--theta", type=float, default=0.095)
    cp.add_argument("--json", action="store_true")
    pp = sub.add_parser("paper", help="paper-trade the 7 bots live on their best coin/window (no orders)")
    pp.add_argument("--db", type=Path, default=DEFAULT_DB.parent / "paper.sqlite")
    pp.add_argument("--duration", type=float, help="seconds to run (default: until Ctrl-C)")
    pp.add_argument("--quote-s", type=float, default=3.0, help="seconds between quote polls per market")
    pp.add_argument("--bots", choices=("originals", "ranking", "all"), default="originals",
                    help="originals = the 7 original bots; all = also the variants and search winners")
    pr = sub.add_parser("paper-report", help="paper-trading results per bot vs the backtest")
    pr.add_argument("--db", type=Path, default=DEFAULT_DB.parent / "paper.sqlite")
    pr.add_argument("--bots", choices=("originals", "ranking", "all"), default="originals")
    se = sub.add_parser("search", help="luck-resistant search over many strategy variations")
    se.add_argument("--db", type=Path, default=DEFAULT_DB)
    se.add_argument("--min-trades", type=int, default=100)
    se.add_argument("--delays", default="60,50",
                    help="price delay to score at, then a pessimistic (shorter) one; measured: 60")
    se.add_argument("--json", action="store_true")
    ap = sub.add_parser("arb-paper", help="paper-test cross-window arbitrage live (no orders)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB.parent / "arb.sqlite")
    ap.add_argument("--duration", type=float)
    ar = sub.add_parser("arb-report", help="results of the arbitrage paper test")
    ar.add_argument("--db", type=Path, default=DEFAULT_DB.parent / "arb.sqlite")
    bt = sub.add_parser("backtest", help="day-by-day backtest of the hunt's portfolio from a bankroll, with stress tests")
    bt.add_argument("--db", type=Path, default=DEFAULT_DB)
    bt.add_argument("--state", type=Path, default=DEFAULT_DB.parent / "hunt" / "state.json")
    bt.add_argument("--out", type=Path)
    bt.add_argument("--bankroll", type=float, default=1000.0)
    bt.add_argument("--cap", type=int, default=50)
    hu = sub.add_parser("hunt", help="keep backfilling and searching until a variation meets the target")
    hu.add_argument("--db", type=Path, default=DEFAULT_DB)
    hu.add_argument("--out", type=Path, default=DEFAULT_DB.parent / "hunt")
    hu.add_argument("--cap", type=int, default=50, help="max contracts per trade")
    hu.add_argument("--target", type=float, default=100.0, help="dollars per day")
    hu.add_argument("--bankroll", type=float, default=1000.0, help="starting money in dollars")
    hu.add_argument("--interval", type=float, default=3600, help="seconds between rounds")
    hu.add_argument("--rounds", type=int, help="stop after this many rounds")
    hu.add_argument("--keep-going", action="store_true", help="keep hunting after the target is met")
    de = sub.add_parser("dashboard-export", help="write per-bot backtest + paper results as JSON")
    de.add_argument("--db", type=Path, default=DEFAULT_DB.parent / "paper.sqlite")
    de.add_argument("--out", type=Path, default=DEFAULT_DB.parent / "bots.json")
    de.add_argument("--bots", choices=("originals", "ranking", "all"), default="originals")
    rep = sub.add_parser("report", help="summarize a recording")
    rep.add_argument("--db", type=Path, default=DEFAULT_DB)
    rep.add_argument("--max-ask", type=float, default=0.98)
    rep.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.cmd == "record":
        args.db.parent.mkdir(parents=True, exist_ok=True)
        conn = db.connect(args.db)
        cfg = Config(assets=tuple(a.strip() for a in args.assets.split(",") if a.strip()),
                     horizons=tuple(h.strip() for h in args.horizons.split(",") if h.strip()),
                     fast_window_s=args.fast_window, rps=min(args.rps, 20.0))
        feed = q = None
        creds = None if args.no_ws else load_credentials()
        if creds:
            from .ws_feed import MarketsFeed
            q = queue.Queue()
            feed = MarketsFeed(creds, q)
            mode = f"live websocket books + trades (key {creds.redacted_key_id})"
        else:
            mode = ("REST books only: CDN-cached up to 30 s, NOT usable for late-window analysis. "
                    "Set POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY for live books")
        print(f"Recording {cfg.assets} {cfg.horizons} into {args.db}\nMode: {mode}\n(Ctrl-C to stop)",
              flush=True)
        stats = Recorder(conn, cfg, feed=feed, feed_queue=q).run(args.duration)
        print(f"Stopped: {stats}")
        return 0
    if args.cmd == "backfill":
        from .backfill import Backfill
        args.db.parent.mkdir(parents=True, exist_ok=True)
        b = Backfill(db.connect(args.db), assets=tuple(args.assets.split(",")),
                     horizons=tuple(args.horizons.split(",")), days=args.days, rps=args.rps,
                     workers=args.workers)
        print(f"Done: {b.run()}")
        return 0
    if args.cmd == "paper":
        from .paper import PaperTrader
        args.db.parent.mkdir(parents=True, exist_ok=True)
        conn = db.connect(args.db)
        print(f"Paper trading into {args.db} (no orders are ever sent; Ctrl-C to stop)", flush=True)
        from .paper import select_bots
        stats = PaperTrader(conn, bots=select_bots(args.bots), quote_s=args.quote_s,
                            log=lambda s: print(s, flush=True)).run(args.duration)
        print(f"Stopped: {stats}")
        return 0
    if args.cmd == "arb-paper":
        from .arb_paper import ArbPaper
        args.db.parent.mkdir(parents=True, exist_ok=True)
        print(f"Arbitrage paper test into {args.db} (no orders; Ctrl-C to stop)", flush=True)
        print(ArbPaper(db.connect(args.db), log=lambda s: print(s, flush=True)).run(args.duration))
        return 0
    if args.cmd == "arb-report":
        from .arb_paper import arb_report
        print(arb_report(db.connect(args.db)))
        return 0
    if args.cmd == "backtest":
        from .portfolio_backtest import main as bt_main
        print(bt_main(args.db, args.state, args.out, args.bankroll, args.cap))
        return 0
    if args.cmd == "hunt":
        from .hunt import run_hunt
        run_hunt(args.db, args.out, cap=args.cap, target=args.target, interval=args.interval,
                 keep_going=args.keep_going, max_rounds=args.rounds, log=lambda s: print(s, flush=True),
                 bankroll=args.bankroll)
        return 0
    if not args.db.exists():
        print(f"No recording at {args.db}", file=sys.stderr)
        return 1
    if args.cmd in ("compare", "study"):
        from . import study as _study
        _study.PRICE_DELAY_S = args.price_delay
    if args.cmd == "search":
        import json
        from .backfill import SCHEMA
        from .search import format_search, run_search
        conn = db.connect(args.db)
        conn.executescript(SCHEMA)
        res = run_search(conn, min_trades=args.min_trades,
                         delays=tuple(int(x) for x in args.delays.split(",")))
        print(json.dumps(res, indent=2, default=str) if args.json else format_search(res), flush=True)
        return 0
    if args.cmd == "compare":
        import json
        from .backfill import SCHEMA
        from .strategies import compare, format_compare
        conn = db.connect(args.db)
        conn.executescript(SCHEMA)
        res = compare(conn, theta=args.theta)
        print(json.dumps(res, indent=2, default=str) if args.json else format_compare(res))
        return 0
    if args.cmd == "study":
        import json
        from .backfill import SCHEMA
        from .study import format_study, run_study
        conn = db.connect(args.db)
        conn.executescript(SCHEMA)
        res = run_study(conn, theta=args.theta)
        print(json.dumps(res, indent=2, default=str) if args.json else format_study(res))
        return 0
    if args.cmd == "dashboard-export":
        from .dashboard_export import export
        from .paper import select_bots
        doc = export(args.db, args.out, bots=select_bots(args.bots))
        print(f"Wrote {len(doc['rows'])} rows to {args.out}")
        return 0
    if args.cmd == "paper-report":
        from .paper import paper_report
        from .paper import select_bots
        print(paper_report(db.connect(args.db), bots=select_bots(args.bots)))
        return 0
    rep_ = build_report(db.connect(args.db), max_ask=args.max_ask)
    print(to_json(rep_) if args.json else format_report(rep_))
    return 0


if __name__ == "__main__":
    sys.exit(main())
