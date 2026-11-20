"""Polling recorder for Polymarket US crypto Up/Down markets (public data, no key needed).

Loop:
  * discovery  every `discovery_s`  -> track open Up/Down windows for chosen assets/horizons
  * index      every `index_s`      -> 1-second settlement-index (BRTI) candles
  * books      every `slow_s`, or every `fast_s` inside the final `fast_window_s` of a window
  * open price refetch until `priceToBeat` is stamped
  * settlement after the window closes, until the exchange publishes it

It never sends an order. All requests go to the public gateway through the shared,
rate-limited RestClient.
"""

from __future__ import annotations

import json
import queue
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime

from pmus_connect.clients import RestClient

from . import db
from .settlement import outcome as settle_outcome


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _f(x) -> float | None:
    try:
        return float(x["value"] if isinstance(x, dict) else x)
    except (TypeError, ValueError, KeyError):
        return None


@dataclass
class Config:
    assets: tuple[str, ...] = ("btc",)
    horizons: tuple[str, ...] = ("15m", "1h")
    discovery_s: float = 30.0
    index_s: float = 10.0
    slow_s: float = 10.0
    fast_s: float = 1.0
    fast_window_s: float = 180.0
    book_levels: int = 10
    settle_poll_s: float = 30.0
    settle_give_up_s: float = 45 * 60
    rps: float = 8.0


@dataclass
class Tracked:
    slug: str
    asset: str
    horizon: str
    window_start: float
    window_end: float
    price_to_beat: float | None
    next_book: float = 0.0
    next_meta: float = 0.0
    next_settle: float = 0.0
    settled: bool = False
    extra: dict = field(default_factory=dict)


class Recorder:
    def __init__(self, conn, cfg: Config, rest: RestClient | None = None, feed=None,
                 feed_queue: queue.Queue | None = None) -> None:
        self.conn, self.cfg = conn, cfg
        self.feed, self.feed_queue = feed, feed_queue
        self.rest = rest or RestClient(None, rps=cfg.rps)
        self.tracked: dict[str, Tracked] = {}
        self.last_index_ts: dict[str, int] = {}
        self.next_discovery = 0.0
        self.next_index = 0.0
        self.stats = {"books": 0, "ws_books": 0, "trades": 0, "index": 0, "settled": 0, "errors": 0}
        self._stop = False
        self._restore()

    # ------------------------------------------------------------ lifecycle
    def _restore(self) -> None:
        """Resume unsettled markets from a previous run."""
        rows = self.conn.execute(
            "SELECT slug, asset, horizon, window_start, window_end, price_to_beat FROM markets "
            "WHERE contract_settlement IS NULL").fetchall()
        for slug, asset, horizon, ws, we, ptb in rows:
            if time.time() - we < self.cfg.settle_give_up_s:
                self.tracked[slug] = Tracked(slug, asset, horizon, ws, we, ptb)
        for asset, ts in self.conn.execute("SELECT asset, MAX(ts) FROM index_ticks GROUP BY asset"):
            self.last_index_ts[asset] = ts
        if self.feed:
            for slug in self.tracked:
                self.feed.add(slug)

    def stop(self, *_) -> None:
        self._stop = True

    def run(self, duration_s: float | None = None) -> dict:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        db.log_event(self.conn, "INFO", f"recorder start {self.cfg}")
        t_end = time.time() + duration_s if duration_s else None
        if self.feed:
            self.feed.start()
        last_status = 0.0
        while not self._stop and (t_end is None or time.time() < t_end):
            now = time.time()
            try:
                if now >= self.next_discovery:
                    self.discover()
                    self.next_discovery = now + self.cfg.discovery_s
                if now >= self.next_index:
                    for a in self.cfg.assets:
                        self.record_index(a)
                    self.next_index = now + self.cfg.index_s
                self.drain_feed()
                for m in list(self.tracked.values()):
                    self.service(m, time.time())
                self.conn.commit()
            except Exception as exc:          # keep recording through transient faults
                self.stats["errors"] += 1
                db.log_event(self.conn, "ERROR", f"{type(exc).__name__}: {exc}")
                self.conn.commit()
                time.sleep(2)
            if now - last_status >= 60:
                print(self.status_line(), flush=True)
                last_status = now
            time.sleep(0.2)
        if self.feed:
            self.feed.stop()
            self.drain_feed()
        db.log_event(self.conn, "INFO", f"recorder stop {self.stats}")
        self.conn.commit()
        self.rest.close()
        return self.stats

    def status_line(self) -> str:
        live = [m for m in self.tracked.values() if not m.settled]
        ws = ""
        if self.feed:
            ws = (f"| ws {'up' if self.feed.connected else 'DOWN'} books {self.stats['ws_books']} "
                  f"trades {self.stats['trades']} ")
        return (f"[{time.strftime('%H:%M:%S')}] tracking {len(live)} markets {ws}| rest books {self.stats['books']} "
                f"| index ticks {self.stats['index']} | settled {self.stats['settled']} "
                f"| errors {self.stats['errors']}")

    # ------------------------------------------------------------ discovery
    def discover(self) -> None:
        now = time.time()
        offset = 0
        while True:
            r = self.rest.public_get("/v1/markets", params={
                "active": "true", "closed": "false", "categories": "crypto",
                "limit": 200, "offset": offset})
            if r.status != 200:
                raise RuntimeError(f"discovery HTTP {r.status}: {r.text[:120]}")
            markets = r.json.get("markets", [])
            for m in markets:
                t = m.get("assetPriceTerms") or {}
                if t.get("marketType") != "ASSET_PRICE_MARKET_TYPE_UP_DOWN":
                    continue
                asset = (t.get("asset") or {}).get("symbol")
                if asset not in self.cfg.assets or t.get("horizon") not in self.cfg.horizons:
                    continue
                slug = m["slug"]
                ws, we = _ts(t.get("windowStart")), _ts(t.get("windowEnd"))
                if slug in self.tracked or not ws or not we or we < now:
                    continue
                ptb = _f(t.get("priceToBeat"))
                self.tracked[slug] = Tracked(slug, asset, t["horizon"], ws, we, ptb)
                self.conn.execute(
                    "INSERT OR IGNORE INTO markets(slug, asset, horizon, window_start, window_end, "
                    "price_to_beat, tick_size, first_seen, updated) VALUES (?,?,?,?,?,?,?,?,?)",
                    (slug, asset, t["horizon"], ws, we, ptb, m.get("orderPriceMinTickSize"), now, now))
                db.log_event(self.conn, "INFO", f"tracking {slug}")
                if self.feed:
                    self.feed.add(slug)
            if len(markets) < 200 or offset > 5000:
                break
            offset += 200

    # ------------------------------------------------------------ index
    def record_index(self, asset: str) -> None:
        now = int(time.time())
        start = max(self.last_index_ts.get(asset, now - 120) - 5, now - 3000)
        r = self.rest.public_get("/v1/asset-prices/history", params={
            "assets": f"crypto:{asset}", "from": start, "to": 0, "bucket": "ASSET_PRICE_BUCKET_1S"})
        if r.status != 200:
            raise RuntimeError(f"index HTTP {r.status}: {r.text[:120]}")
        candles = (r.json.get("series") or [{}])[0].get("candles") or []
        rows = [(asset, int(c["timestamp"]), float(c["close"])) for c in candles
                if int(c["timestamp"]) < now and int(c.get("tickCount") or 0) > 0]   # skip in-progress / gap-filled
        self.conn.executemany("INSERT OR REPLACE INTO index_ticks(asset, ts, close) VALUES (?,?,?)", rows)
        if rows:
            self.last_index_ts[asset] = max(r_[1] for r_ in rows)
            self.stats["index"] += len(rows)

    # ------------------------------------------------------------ per-market
    def service(self, m: Tracked, now: float) -> None:
        if m.settled:
            return
        if now < m.window_end + 2 and now >= m.next_book:
            self.record_book(m, now)
            live = self.feed is not None and self.feed.connected
            fast = m.window_end - now <= self.cfg.fast_window_s and not live
            interval = self.cfg.fast_s if fast else self.cfg.slow_s
            m.next_book = now + interval
        if m.price_to_beat is None and now >= m.window_start and now >= m.next_meta:
            self.refresh_meta(m)
            m.next_meta = now + 5
        if now >= m.window_end + 20 and now >= m.next_settle:
            self.check_settlement(m)
            m.next_settle = now + self.cfg.settle_poll_s
            if not m.settled and now - m.window_end > self.cfg.settle_give_up_s:
                db.log_event(self.conn, "WARN", f"gave up waiting for settlement of {m.slug}")
                m.settled = True
        if m.settled:
            self.tracked.pop(m.slug, None)

    def record_book(self, m: Tracked, now: float) -> None:
        r = self.rest.public_get(f"/v1/markets/{m.slug}/book")
        if r.status != 200:
            db.log_event(self.conn, "WARN", f"book {m.slug} HTTP {r.status}")
            return
        md = r.json.get("marketData", {})
        n = self.cfg.book_levels
        bids = [[_f(l["px"]), _f(l["qty"])] for l in (md.get("bids") or [])[:n]]
        offers = [[_f(l["px"]), _f(l["qty"])] for l in (md.get("offers") or [])[:n]]
        self.conn.execute(
            "INSERT INTO book_snapshots(slug, ts, secs_to_close, state, best_bid, best_ask, bid_qty, "
            "ask_qty, bids_json, offers_json, latency_ms, source, cache_age_s) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (m.slug, now, m.window_end - now, md.get("state"),
             bids[0][0] if bids else None, offers[0][0] if offers else None,
             bids[0][1] if bids else None, offers[0][1] if offers else None,
             json.dumps(bids), json.dumps(offers), r.elapsed_ms, "rest", r.cache_age))
        self.stats["books"] += 1

    def drain_feed(self) -> None:
        if not self.feed_queue:
            return
        while True:
            try:
                item = self.feed_queue.get_nowait()
            except queue.Empty:
                return
            kind = item[0]
            if kind == "event":
                db.log_event(self.conn, item[1], item[2])
            elif kind == "book":
                _, slug, ts, state, bids, offers = item
                m = self.tracked.get(slug)
                end = m.window_end if m else (self.conn.execute(
                    "SELECT window_end FROM markets WHERE slug=?", (slug,)).fetchone() or [None])[0]
                if end is None:
                    continue
                self.conn.execute(
                    "INSERT INTO book_snapshots(slug, ts, secs_to_close, state, best_bid, best_ask, "
                    "bid_qty, ask_qty, bids_json, offers_json, latency_ms, source, cache_age_s) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,NULL,'ws',NULL)",
                    (slug, ts, end - ts, state, bids[0][0] if bids else None,
                     offers[0][0] if offers else None, bids[0][1] if bids else None,
                     offers[0][1] if offers else None, json.dumps(bids), json.dumps(offers)))
                self.stats["ws_books"] += 1
            elif kind == "trade":
                _, slug, ts, trade_time, price, qty, maker, taker = item
                self.conn.execute(
                    "INSERT INTO trades(slug, trade_time, ts, price, quantity, maker_intent, taker_intent) "
                    "VALUES (?,?,?,?,?,?,?)", (slug, trade_time, ts, price, qty, maker, taker))
                self.stats["trades"] += 1

    def _market(self, slug: str) -> dict:
        r = self.rest.public_get(f"/v1/market/slug/{slug}")
        if r.status != 200 or not isinstance(r.json, dict):
            return {}
        return r.json.get("market", r.json) or {}

    def _market_terms(self, slug: str) -> dict:
        return self._market(slug).get("assetPriceTerms") or {}

    def refresh_meta(self, m: Tracked) -> None:
        ptb = _f(self._market_terms(m.slug).get("priceToBeat"))
        if ptb is not None:
            m.price_to_beat = ptb
            self.conn.execute("UPDATE markets SET price_to_beat=?, updated=? WHERE slug=?",
                              (ptb, time.time(), m.slug))

    def check_settlement(self, m: Tracked) -> None:
        market = self._market(m.slug)
        terms = market.get("assetPriceTerms") or {}
        resolved = market.get("status") == "MARKET_STATUS_RESOLVED"
        close = _f(terms.get("settlementPrice"))
        ptb = _f(terms.get("priceToBeat")) or m.price_to_beat
        r = self.rest.public_get(f"/v1/markets/{m.slug}/settlement")
        contract = _f(r.json.get("settlement")) if r.status == 200 and r.json else None
        if contract is None and close is None:
            return
        out = None
        if close is not None and ptb is not None:
            out = settle_outcome(ptb, close)
        elif contract is not None:
            out = "UP" if contract >= 0.5 else "DOWN"
        self.conn.execute(
            "UPDATE markets SET settlement_price=COALESCE(?, settlement_price), "
            "contract_settlement=COALESCE(?, contract_settlement), price_to_beat=COALESCE(?, price_to_beat), "
            "outcome=?, updated=? WHERE slug=?", (close, contract, ptb, out, time.time(), m.slug))
        # The contract settlement endpoint can lag the index close; a resolved market
        # with a published close is final.
        if contract is not None or (resolved and close is not None and out is not None):
            m.settled = True
            self.stats["settled"] += 1
            db.log_event(self.conn, "INFO", f"settled {m.slug}: {out} close={close} ptb={ptb} contract={contract}")
