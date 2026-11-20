"""Live PAPER test of cross-window arbitrage (strategies_cross.py). Never sends an order.

Tracks every open Up/Down market for the chosen coins, groups the ones that close at the same
instant, and in each group's last `window_s` seconds polls each market's live best bid/ask
(`/v1/market/slug/{slug}`) every `quote_s` seconds. Whenever, for two markets A and B of the
same group with ptb(B) - ptb(A) >= gap,

    ask_up(A) + (1 - bid_up(B)) + both taker fees < 1 - min_edge

it records one paper pair trade (once per pair) with each leg's quote time and, as a rough
size check, the contracts offered at that price in the public book (CDN-cached up to 30 s).
After the close it settles both legs from the exchange's published result.
"""

from __future__ import annotations

import signal
import sqlite3
import time
from datetime import datetime, timezone

from pmus_connect.clients import RestClient

from .paper import _f, _ts
from .settlement import outcome as settle_outcome
from .settlement import taker_fee

SCHEMA = """
CREATE TABLE IF NOT EXISTS arb_markets (
    slug TEXT PRIMARY KEY, asset TEXT, horizon TEXT, window_end INTEGER, price_to_beat REAL,
    settlement_price REAL, outcome TEXT, settled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS arb_quotes (slug TEXT, ts REAL, best_bid REAL, best_ask REAL);
CREATE TABLE IF NOT EXISTS arb_trades (
    a TEXT, b TEXT, asset TEXT, window_end INTEGER, ts REAL, secs_left REAL,
    up_a REAL, down_b REAL, cost REAL, quote_gap_s REAL, qty_a REAL, qty_b REAL,
    pay REAL, pnl REAL, PRIMARY KEY (a, b));
"""


class ArbPaper:
    def __init__(self, conn: sqlite3.Connection, assets=("btc", "eth", "sol", "xrp"),
                 horizons=("5m", "15m", "1h"), rest: RestClient | None = None, quote_s=3.0,
                 window_s=600, gap=0.01, min_edge=0.0, theta=0.095, log=print):
        self.conn, self.log, self.theta, self.gap, self.min_edge = conn, log, theta, gap, min_edge
        conn.executescript(SCHEMA)
        self.rest = rest or RestClient(None, rps=10)
        self.assets, self.horizons = set(assets), set(horizons)
        self.quote_s, self.window_s = quote_s, window_s
        self.markets: dict[str, dict] = {}
        self.quotes: dict[str, tuple] = {}            # slug -> (ts, bid, ask)
        self.done = {(a, b) for a, b in conn.execute("SELECT a, b FROM arb_trades")}
        for slug, a, h, we, ptb in conn.execute(
                "SELECT slug, asset, horizon, window_end, price_to_beat FROM arb_markets WHERE settled=0"):
            self.markets[slug] = {"slug": slug, "asset": a, "horizon": h, "t_end": we, "ptb": ptb,
                                  "next_settle": 0.0}
        self.next_disc = self.next_quote = 0.0
        self.running = True
        self.stats = {"quotes": 0, "pairs": 0, "settled": 0, "errors": 0}

    def stop(self, *_):
        self.running = False

    def discover(self, now):
        offset = 0
        while offset <= 5000:
            r = self.rest.public_get("/v1/markets", params={
                "active": "true", "closed": "false", "categories": "crypto", "limit": 200, "offset": offset})
            if r.status != 200:
                raise RuntimeError(f"discovery HTTP {r.status}")
            ms = r.json.get("markets", [])
            for x in ms:
                t = x.get("assetPriceTerms") or {}
                a, h = (t.get("asset") or {}).get("symbol"), t.get("horizon")
                we = _ts(t.get("windowEnd"))
                if (t.get("marketType") == "ASSET_PRICE_MARKET_TYPE_UP_DOWN" and a in self.assets
                        and h in self.horizons and we and we > now + 5 and x["slug"] not in self.markets):
                    m = {"slug": x["slug"], "asset": a, "horizon": h, "t_end": int(round(we)),
                         "ptb": _f(t.get("priceToBeat")), "next_settle": 0.0}
                    self.markets[x["slug"]] = m
                    self.conn.execute("INSERT OR IGNORE INTO arb_markets(slug, asset, horizon, window_end, "
                                      "price_to_beat) VALUES (?,?,?,?,?)", (m["slug"], a, h, m["t_end"], m["ptb"]))
            if len(ms) < 200:
                break
            offset += 200

    def _groups(self, now):
        g = {}
        for m in self.markets.values():
            if m["t_end"] - self.window_s <= now <= m["t_end"] - 30:
                g.setdefault((m["asset"], m["t_end"]), []).append(m)
        return [v for v in g.values() if len(v) > 1]

    def poll(self, m, now):
        r = self.rest.public_get(f"/v1/market/slug/{m['slug']}")
        if r.status != 200 or not isinstance(r.json, dict):
            return
        x = r.json.get("market", r.json) or {}
        bid, ask = _f(x.get("bestBidQuote")), _f(x.get("bestAskQuote"))
        ptb = _f((x.get("assetPriceTerms") or {}).get("priceToBeat"))
        if ptb is not None and m["ptb"] is None:
            m["ptb"] = ptb
            self.conn.execute("UPDATE arb_markets SET price_to_beat=? WHERE slug=?", (ptb, m["slug"]))
        self.quotes[m["slug"]] = (time.time(), bid, ask)
        self.conn.execute("INSERT INTO arb_quotes VALUES (?,?,?,?)", (m["slug"], time.time(), bid, ask))
        self.stats["quotes"] += 1

    def _book_qty(self, slug, side_up, price):
        r = self.rest.public_get(f"/v1/markets/{slug}/book")
        if r.status != 200 or not isinstance(r.json, dict):
            return None
        md = r.json.get("marketData") or {}
        if side_up:
            return sum(_f(l.get("qty")) or 0 for l in md.get("offers") or [] if (_f(l.get("px")) or 9) <= price + 1e-9)
        return sum(_f(l.get("qty")) or 0 for l in md.get("bids") or [] if (_f(l.get("px")) or -9) >= 1 - price - 1e-9)

    def check_pairs(self, group, now):
        for A in group:
            for B in group:
                if A is B or A["ptb"] is None or B["ptb"] is None or B["ptb"] - A["ptb"] < self.gap:
                    continue
                if (A["slug"], B["slug"]) in self.done:
                    continue
                qa, qb = self.quotes.get(A["slug"]), self.quotes.get(B["slug"])
                if not qa or not qb or qa[2] is None or qb[1] is None or abs(qa[0] - qb[0]) > self.quote_s:
                    continue
                up_a, down_b = qa[2], round(1 - qb[1], 4)
                if not (0 < up_a < 0.99 and 0 < down_b < 0.99):
                    continue
                cost = up_a + down_b + taker_fee(up_a, theta=self.theta) + taker_fee(down_b, theta=self.theta)
                if cost >= 1 - self.min_edge:
                    continue
                qty_a, qty_b = self._book_qty(A["slug"], True, up_a), self._book_qty(B["slug"], False, down_b)
                self.done.add((A["slug"], B["slug"]))
                self.conn.execute("INSERT OR IGNORE INTO arb_trades(a, b, asset, window_end, ts, secs_left, up_a, "
                                  "down_b, cost, quote_gap_s, qty_a, qty_b) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (A["slug"], B["slug"], A["asset"], A["t_end"], now, A["t_end"] - now, up_a,
                                   down_b, cost, abs(qa[0] - qb[0]), qty_a, qty_b))
                self.stats["pairs"] += 1
                self.log(f"PAPER PAIR {A['asset'].upper()} {A['horizon']}/{B['horizon']} close {A['t_end']}: "
                         f"Up {up_a:.2f} + Down {down_b:.2f} = {cost:.3f} with fees, T-{A['t_end'] - now:.0f}s, "
                         f"book {qty_a} / {qty_b} ct")

    def settle(self, m, now):
        r = self.rest.public_get(f"/v1/market/slug/{m['slug']}")
        x = (r.json.get("market", r.json) if r.status == 200 and isinstance(r.json, dict) else {}) or {}
        t = x.get("assetPriceTerms") or {}
        close, ptb = _f(t.get("settlementPrice")), _f(t.get("priceToBeat")) or m["ptb"]
        if x.get("status") != "MARKET_STATUS_RESOLVED" or close is None or ptb is None:
            return False
        self.conn.execute("UPDATE arb_markets SET settlement_price=?, outcome=?, settled=1 WHERE slug=?",
                          (close, settle_outcome(ptb, close), m["slug"]))
        self.stats["settled"] += 1
        for a, b, cost in self.conn.execute(
                "SELECT t.a, t.b, t.cost FROM arb_trades t JOIN arb_markets ma ON ma.slug=t.a "
                "JOIN arb_markets mb ON mb.slug=t.b WHERE t.pay IS NULL AND ma.settled=1 AND mb.settled=1").fetchall():
            oa, ob = (self.conn.execute("SELECT outcome FROM arb_markets WHERE slug=?", (s,)).fetchone()[0] for s in (a, b))
            pay = (1.0 if oa == "UP" else 0.0) + (1.0 if ob == "DOWN" else 0.0)
            self.conn.execute("UPDATE arb_trades SET pay=?, pnl=? WHERE a=? AND b=?", (pay, pay - cost, a, b))
            self.log(f"SETTLED PAIR {a} + {b}: pays {pay:.0f}, P&L {pay - cost:+.3f}")
        return True

    def step(self, now):
        if now >= self.next_disc:
            self.discover(now)
            self.next_disc = now + 60
        if now >= self.next_quote:
            for g in self._groups(now):
                for m in g:
                    self.poll(m, now)
                self.check_pairs(g, now)
            self.next_quote = now + self.quote_s
        for m in list(self.markets.values()):
            if now >= m["t_end"] + 20 and now >= m["next_settle"]:
                m["next_settle"] = now + 30
                if self.settle(m, now) or now > m["t_end"] + 3600:
                    self.markets.pop(m["slug"], None)
        self.conn.commit()

    def run(self, duration_s=None, status_every=600):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        t0 = last = time.time()
        while self.running and (duration_s is None or time.time() - t0 < duration_s):
            now = time.time()
            try:
                self.step(now)
            except Exception as exc:
                self.stats["errors"] += 1
                self.log(f"error: {exc}")
                time.sleep(5)
            if now - last >= status_every:
                last = now
                self.log(f"status {datetime.now(timezone.utc):%H:%M}Z tracking {len(self.markets)} {self.stats}")
            time.sleep(0.5)
        self.conn.commit()
        return self.stats


def arb_report(conn) -> str:
    conn.executescript(SCHEMA)
    rows = conn.execute("SELECT COUNT(*), SUM(pnl IS NOT NULL), SUM(pnl), AVG(cost), SUM(pay < 1), "
                        "AVG(quote_gap_s), AVG(MIN(COALESCE(qty_a, 0), COALESCE(qty_b, 0))), MIN(ts), MAX(ts) "
                        "FROM arb_trades").fetchone()
    n, settled, pnl, cost, zero, gap, qty, t0, t1 = rows
    if not n:
        return "Cross-window arbitrage paper test: no pairs yet."
    hours = max((t1 - t0) / 3600, 1e-9)
    return (f"Cross-window arbitrage paper test: {n} pairs ({settled or 0} settled), P&L {pnl or 0:+.2f} per "
            f"contract pair, avg cost {cost:.3f}, pairs that paid 0: {zero or 0}, avg time between leg quotes "
            f"{gap:.1f} s, avg smaller-leg book size {qty or 0:.0f} contracts, over {hours:.1f} h.")
