"""CLI: python -m pmus_connect [--asset btc] [--horizon 15m] [--market SLUG] [--preview-order] [--json]

Exit code 0 when no check FAILs, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import checks as c
from .clients import RestClient
from .config import load_credentials

ICON = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭️ "}


def run(args: argparse.Namespace) -> list[c.CheckResult]:
    creds = load_credentials()
    results: list[c.CheckResult] = []
    rest = RestClient(creds)
    try:
        gw = c.check_gateway(rest)
        results.append(gw)
        if gw.status == "FAIL":
            return results
        results.append(c.check_clock(gw.data.get("server_time")))

        market = None
        if args.market:
            slug = args.market
        else:
            disc, market = c.discover_crypto_markets(rest, args.asset, args.horizon)
            results.append(disc)
            slug = market["slug"] if market else None

        if slug:
            results.append(c.check_bbo(rest, slug))
            results.append(c.check_book(rest, slug))
        results.append(c.check_reference_index(rest, args.asset))
        results.append(c.check_auth_host_unsigned(rest))

        if creds is None:
            results.append(c.check_ws(None, "/v1/ws/markets", None, "Markets websocket reachable", 0))
            results.append(c.CheckResult("Authenticated checks", "SKIP",
                                         "set POLYMARKET_KEY_ID and POLYMARKET_SECRET_KEY to run them"))
            return results

        key_check = c.check_key_format(creds)
        results.append(key_check)
        if key_check.status == "FAIL":
            return results
        results.append(c.check_auth_get(rest, "Account balances", "/v1/account/balances",
                                        c.summarize_balances))
        results.append(c.check_auth_get(rest, "Portfolio positions", "/v1/portfolio/positions",
                                        c.summarize_positions))
        results.append(c.check_auth_get(rest, "Open orders", "/v1/orders/open", c.summarize_orders))
        if slug:
            results.append(c.check_ws(creds, "/v1/ws/markets", c.market_ws_subscription(slug),
                                      "Markets websocket stream", args.ws_wait))
        results.append(c.check_ws(creds, "/v1/ws/private", c.private_ws_subscription(),
                                  "Private websocket stream", args.ws_wait))
        if args.preview_order and slug:
            results.append(c.check_preview(rest, slug))
    finally:
        rest.close()
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pmus_connect",
                                description="Read-only Polymarket US connectivity check. Never trades.")
    p.add_argument("--asset", default="btc", help="crypto asset symbol (default: btc)")
    p.add_argument("--horizon", default="15m", help="preferred Up/Down window (5m, 15m, 1h, 1d)")
    p.add_argument("--market", help="probe this market slug instead of auto-discovering one")
    p.add_argument("--ws-wait", type=float, default=10.0, help="seconds to wait for a websocket message")
    p.add_argument("--preview-order", action="store_true",
                   help="also validate (not submit) a 1-contract $0.01 maker order via /v1/order/preview")
    p.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = p.parse_args(argv)

    results = run(args)
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, default=str))
    else:
        print("\nPolymarket US connectivity check (read-only)\n" + "-" * 60)
        for r in results:
            lat = f" [{r.latency_ms:.0f} ms]" if r.latency_ms is not None else ""
            print(f"{ICON[r.status]} {r.name}{lat}\n     {r.detail}")
        n = {s: sum(r.status == s for r in results) for s in ICON}
        print("-" * 60 + f"\n{n['PASS']} passed, {n['FAIL']} failed, {n['WARN']} warnings, {n['SKIP']} skipped\n")
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
