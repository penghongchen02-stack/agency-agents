"""Backfill historical Polymarket US crypto Up/Down markets from PUBLIC data (no key).

For each closed Up/Down window it stores:
  * market terms: window, priceToBeat (open), settlementPrice (close), outcome
  * price history: the exchange's stored display prices (`/v1/price-history`, custom
    range, fidelity=1). longPrice = Up (Yes) price from the best ask, shortPrice =
    Down (No) price from 1 - best bid. In practice these are about one point per minute.
  * settlement-index (BRTI) 1-second candles for the last `index_lookback_s` before close

Resumable: markets that already have price points are skipped.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from pmus_connect.clients import RestClient

from . import db
from .settlement import outcome as settle_outcome

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_points (
    slug TEXT NOT NULL,
    ts INTEGER NOT NULL,
    up_price REAL,          -- longPrice: Up (Yes) display price, from best ask
    down_price REAL,        -- shortPrice: Down (No) display price, from 1 - best bid
    PRIMARY KEY (slug, ts)
);
CREATE TABLE IF NOT EXISTS backfill_done (
    slug TEXT PRIMARY KEY,
    points INTEGER NOT NULL,
    ts REAL NOT NULL
);
"""


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(s: str | None) -> float | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def _f(x):
    try:
        return float(x["value"] if isinstance(x, dict) else x)
    except (TypeError, ValueError, KeyError):
        return None


class Backfill:
    def __init__(self, conn, assets=("btc",), horizons=("15m", "1h"), days: float = 45,
                 history_lookback_s: int = 600, index_lookback_s: int = 180, rps: float = 8.0,
                 rest: RestClient | None = None) -> None:
        self.conn = conn
        conn.executescript(SCHEMA)
        self.assets, self.horizons, self.days = set(assets), set(horizons), days
        self.hist_lb, self.idx_lb = history_lookback_s, index_lookback_s
        self.rest = rest or RestClient(None, rps=min(rps, 15.0))
        self.stats = {"markets": 0, "new": 0, "price_points": 0, "index_ticks": 0, "skipped": 0}

    # -------------------------------------------------- discovery
    def discover(self) -> list[dict]:
        found: dict[str, dict] = {}
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.days)
        chunk = timedelta(hours=6)
        t = start
        while t < end:
            offset = 0
            while True:
                r = self.rest.public_get("/v1/markets", params={
                    "closed": "true", "categories": "crypto", "limit": 200, "offset": offset,
                    "endDateMin": _iso(t), "endDateMax": _iso(min(t + chunk, end))})
                if r.status != 200:
                    raise RuntimeError(f"discovery HTTP {r.status}: {r.text[:120]}")
                ms = r.json.get("markets", [])
                for m in ms:
                    a = m.get("assetPriceTerms") or {}
                    if (a.get("marketType") == "ASSET_PRICE_MARKET_TYPE_UP_DOWN"
                            and (a.get("asset") or {}).get("symbol") in self.assets
                            and a.get("horizon") in self.horizons
                            and m.get("status") == "MARKET_STATUS_RESOLVED"):
                        found[m["slug"]] = m
                if len(ms) < 200:
                    break
                offset += 200
            t += chunk
        return sorted(found.values(), key=lambda m: m["assetPriceTerms"]["windowEnd"])

    # -------------------------------------------------- per market
    def store_market(self, m: dict) -> tuple[str, str, int] | None:
        a = m["assetPriceTerms"]
        ws, we = _ts(a.get("windowStart")), _ts(a.get("windowEnd"))
        ptb, close = _f(a.get("priceToBeat")), _f(a.get("settlementPrice"))
        if not (ws and we and ptb is not None and close is not None):
            return None
        out = settle_outcome(ptb, close)
        now = time.time()
        self.conn.execute(
            "INSERT INTO markets(slug, asset, horizon, window_start, window_end, price_to_beat, "
            "settlement_price, outcome, tick_size, first_seen, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(slug) DO UPDATE SET price_to_beat=excluded.price_to_beat, "
            "settlement_price=excluded.settlement_price, outcome=excluded.outcome, updated=excluded.updated",
            (m["slug"], a["asset"]["symbol"], a["horizon"], ws, we, ptb, close, out,
             m.get("orderPriceMinTickSize"), now, now))
        return m["slug"], a["asset"]["symbol"], int(round(we))

    def fetch_prices(self, slug: str, t_end: int) -> int:
        r = self.rest.public_get("/v1/price-history", params={
            "symbol": slug, "timestamp.startTimestamp": t_end - self.hist_lb,
            "timestamp.endTimestamp": t_end + 30, "fidelity": 1})
        if r.status != 200:
            raise RuntimeError(f"price-history {slug} HTTP {r.status}: {r.text[:120]}")
        rows = [(slug, int(p["timestamp"]), p.get("longPrice"), p.get("shortPrice"))
                for p in r.json.get("history", [])]
        self.conn.executemany("INSERT OR REPLACE INTO price_points VALUES (?,?,?,?)", rows)
        self.conn.execute("INSERT OR REPLACE INTO backfill_done VALUES (?,?,?)",
                          (slug, len(rows), time.time()))
        return len(rows)

    def fetch_index(self, asset: str, t_end: int) -> int:
        have = self.conn.execute("SELECT COUNT(*) FROM index_ticks WHERE asset=? AND ts>=? AND ts<?",
                                 (asset, t_end - self.idx_lb, t_end)).fetchone()[0]
        if have >= self.idx_lb - 2:
            return 0
        r = self.rest.public_get("/v1/asset-prices/history", params={
            "assets": f"crypto:{asset}", "from": t_end - self.idx_lb, "to": t_end,
            "bucket": "ASSET_PRICE_BUCKET_1S"})
        if r.status != 200:
            raise RuntimeError(f"index HTTP {r.status}: {r.text[:120]}")
        candles = (r.json.get("series") or [{}])[0].get("candles") or []
        rows = [(asset, int(c["timestamp"]), float(c["close"])) for c in candles
                if int(c.get("tickCount") or 0) > 0 and int(c["timestamp"]) < t_end]
        self.conn.executemany("INSERT OR REPLACE INTO index_ticks(asset, ts, close) VALUES (?,?,?)", rows)
        return len(rows)

    def run(self, progress_every: int = 250) -> dict:
        print(f"Discovering closed {sorted(self.assets)} {sorted(self.horizons)} Up/Down markets "
              f"over the last {self.days:g} days...", flush=True)
        markets = self.discover()
        self.stats["markets"] = len(markets)
        print(f"Found {len(markets)} resolved markets.", flush=True)
        done = {s for (s,) in self.conn.execute("SELECT slug FROM backfill_done")}
        t0 = time.time()
        for i, m in enumerate(markets, 1):
            stored = self.store_market(m)
            if not stored:
                self.stats["skipped"] += 1
                continue
            slug, asset, t_end = stored
            try:
                if slug not in done:
                    self.stats["price_points"] += self.fetch_prices(slug, t_end)
                    self.stats["new"] += 1
                self.stats["index_ticks"] += self.fetch_index(asset, t_end)
            except Exception as exc:          # keep going; record and move on
                db.log_event(self.conn, "ERROR", f"backfill {slug}: {exc}")
            if i % 50 == 0:
                self.conn.commit()
            if i % progress_every == 0:
                rate = i / max(time.time() - t0, 1e-9)
                print(f"  {i}/{len(markets)} markets ({rate:.1f}/s) {self.stats}", flush=True)
        self.conn.commit()
        self.rest.close()
        return self.stats
