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
    st.add_argument("--theta", type=float, default=0.095, help="taker fee coefficient (Tier 1 = 0.095)")
    st.add_argument("--json", action="store_true")
    cp = sub.add_parser("compare", help="compare strategy families per asset/horizon (walk-forward)")
    cp.add_argument("--db", type=Path, default=DEFAULT_DB)
    cp.add_argument("--theta", type=float, default=0.095)
    cp.add_argument("--json", action="store_true")
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
    if not args.db.exists():
        print(f"No recording at {args.db}", file=sys.stderr)
        return 1
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
    rep_ = build_report(db.connect(args.db), max_ask=args.max_ask)
    print(to_json(rep_) if args.json else format_report(rep_))
    return 0


if __name__ == "__main__":
    sys.exit(main())
