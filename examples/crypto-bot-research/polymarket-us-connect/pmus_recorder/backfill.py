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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                 rest: RestClient | None = None, workers: int = 8) -> None:
        self.workers = workers
        self.conn = conn
        conn.executescript(SCHEMA)
        self.assets, self.horizons, self.days = set(assets), set(horizons), days
        self.hist_lb, self.idx_lb = history_lookback_s, index_lookback_s
        self.rest = rest or RestClient(None, rps=min(rps, 15.0))
        self.stats = {"markets": 0, "new": 0, "price_points": 0, "index_ticks": 0, "skipped": 0}

    # -------------------------------------------------- discovery
    def _discover_chunk(self, lo: datetime, hi: datetime) -> list[dict]:
        out, offset = [], 0
        while True:
            r = self.rest.public_get("/v1/markets", params={
                "closed": "true", "categories": "crypto", "limit": 200, "offset": offset,
                "endDateMin": _iso(lo), "endDateMax": _iso(hi)})
            if r.status != 200:
                raise RuntimeError(f"discovery HTTP {r.status}: {r.text[:120]}")
            ms = r.json.get("markets", [])
            for m in ms:
                a = m.get("assetPriceTerms") or {}
                if (a.get("marketType") == "ASSET_PRICE_MARKET_TYPE_UP_DOWN"
                        and (a.get("asset") or {}).get("symbol") in self.assets
                        and a.get("horizon") in self.horizons
                        and m.get("status") == "MARKET_STATUS_RESOLVED"):
                    out.append(m)
            if len(ms) < 200:
                return out
            offset += 200

    def discover(self) -> list[dict]:
        found: dict[str, dict] = {}
        end = datetime.now(timezone.utc)
        t, chunks = end - timedelta(days=self.days), []
        while t < end:
            chunks.append((t, min(t + timedelta(hours=6), end)))
            t += timedelta(hours=6)
        with ThreadPoolExecutor(self.workers) as pool:
            futs = [pool.submit(self._discover_chunk, lo, hi) for lo, hi in chunks]
            for i, f in enumerate(as_completed(futs), 1):
                for m in f.result():
                    found[m["slug"]] = m
                if i % 20 == 0:
                    print(f"  discovery {i}/{len(chunks)} chunks, {len(found)} markets so far", flush=True)
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

    def get_prices(self, slug: str, t_end: int) -> list[tuple]:
        r = self.rest.public_get("/v1/price-history", params={
            "symbol": slug, "timestamp.startTimestamp": t_end - self.hist_lb,
            "timestamp.endTimestamp": t_end + 30, "fidelity": 1})
        if r.status != 200:
            raise RuntimeError(f"price-history {slug} HTTP {r.status}: {r.text[:120]}")
        return [(slug, int(p["timestamp"]), p.get("longPrice"), p.get("shortPrice"))
                for p in r.json.get("history", [])]

    def save_prices(self, slug: str, rows: list[tuple]) -> int:
        self.conn.executemany("INSERT OR REPLACE INTO price_points VALUES (?,?,?,?)", rows)
        self.conn.execute("INSERT OR REPLACE INTO backfill_done VALUES (?,?,?)",
                          (slug, len(rows), time.time()))
        return len(rows)

    def need_index(self, asset: str, t_end: int) -> bool:
        have = self.conn.execute("SELECT COUNT(*) FROM index_ticks WHERE asset=? AND ts>=? AND ts<?",
                                 (asset, t_end - self.idx_lb, t_end)).fetchone()[0]
        return have < self.idx_lb - 2

    def get_index(self, asset: str, t_end: int) -> list[tuple]:
        r = self.rest.public_get("/v1/asset-prices/history", params={
            "assets": f"crypto:{asset}", "from": t_end - self.idx_lb, "to": t_end,
            "bucket": "ASSET_PRICE_BUCKET_1S"})
        if r.status != 200:
            raise RuntimeError(f"index HTTP {r.status}: {r.text[:120]}")
        candles = (r.json.get("series") or [{}])[0].get("candles") or []
        return [(asset, int(c["timestamp"]), float(c["close"])) for c in candles
                if int(c.get("tickCount") or 0) > 0 and int(c["timestamp"]) < t_end]

    def save_index(self, rows: list[tuple]) -> int:
        self.conn.executemany("INSERT OR REPLACE INTO index_ticks(asset, ts, close) VALUES (?,?,?)", rows)
        return len(rows)

    def run(self, progress_every: int = 250) -> dict:
        print(f"Discovering closed {sorted(self.assets)} {sorted(self.horizons)} Up/Down markets "
              f"over the last {self.days:g} days...", flush=True)
        markets = self.discover()
        self.stats["markets"] = len(markets)
        print(f"Found {len(markets)} resolved markets.", flush=True)
        done = {s for (s,) in self.conn.execute("SELECT slug FROM backfill_done")}
        jobs, index_keys = [], set()
        for m in markets:
            stored = self.store_market(m)
            if not stored:
                self.stats["skipped"] += 1
                continue
            slug, asset, t_end = stored
            if slug not in done:
                jobs.append(("prices", slug, t_end))
            if (asset, t_end) not in index_keys and self.need_index(asset, t_end):
                index_keys.add((asset, t_end))
                jobs.append(("index", asset, t_end))
        self.conn.commit()
        print(f"{len(jobs)} requests to make ({len(index_keys)} index windows).", flush=True)
        t0 = time.time()

        def work(job):
            kind, key, t_end = job
            return job, (self.get_prices(key, t_end) if kind == "prices" else self.get_index(key, t_end))

        with ThreadPoolExecutor(self.workers) as pool:
            futs = [pool.submit(work, j) for j in jobs]
            for i, f in enumerate(as_completed(futs), 1):
                try:
                    (kind, key, t_end), rows = f.result()
                    if kind == "prices":
                        self.stats["price_points"] += self.save_prices(key, rows)
                        self.stats["new"] += 1
                    else:
                        self.stats["index_ticks"] += self.save_index(rows)
                except Exception as exc:      # keep going; record and move on
                    db.log_event(self.conn, "ERROR", f"backfill: {exc}")
                if i % 100 == 0:
                    self.conn.commit()
                if i % progress_every == 0:
                    rate = i / max(time.time() - t0, 1e-9)
                    eta = (len(jobs) - i) / max(rate, 1e-9)
                    print(f"  {i}/{len(jobs)} requests ({rate:.1f}/s, ~{eta / 60:.0f} min left) "
                          f"{self.stats}", flush=True)
        self.conn.commit()
        self.rest.close()
        return self.stats
