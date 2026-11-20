"""Live PAPER trading: run all seven strategy bots forward on live public data. No orders, ever.

Each bot trades all four coins; per coin it uses the window length where it did best in the
45-day walk-forward test (RESULTS-2026-11-20-all-strategies.md, 90 s price delay). It uses the same rules and
settings as the backtest, so live results can be compared with what the backtest predicted.

Live public data (no API key):
  * best bid / ask: `GET /v1/market/slug/{slug}` (bestBidQuote / bestAskQuote). Unlike the
    CDN-cached /book and /bbo (max-age=30), this updates about every 1-2 s.
    Up buy price = best ask; Down buy price = 1 - best bid; a missing side shows as $0.99
    (unbuyable), like the backtest's display prices.
  * settlement index: 1 s BRTI candles from `/v1/asset-prices/history`, as they publish.

Same timing as the backtest: quotes are polled every few seconds, and one "minute point" is
kept at second :30 of each minute (the backtest's points were really seen at :30). Price-only
bots read the minute points; index bots decide at the latest minute point at or before
T - offset, with whatever index candles had arrived by then (the live index lag is logged).

Fills are assumed at the quoted price, size unknown, 1 contract (tilt for NeverSmiling),
Tier 1 taker fee. Paper results are an upper bound on what a real bot would get.
"""

from __future__ import annotations

import signal
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pmus_connect.clients import RestClient

from .settlement import outcome as settle_outcome
from .settlement import projected_close, taker_fee
from .strategies import _select, _sigma, model_probability
from .strategies_extra import LEGS
from .strategies_variants import VARIANTS

INDEX_FAMILIES = ("favourite", "model_edge", "disagreement", "model_edge_strict")
ALL_LEGS = {**LEGS, **{name: legs for name, (legs, _) in VARIANTS.items()}}


@dataclass(frozen=True)
class Bot:
    name: str
    asset: str
    horizon: str
    params: dict
    backtest_ev: float          # test-period EV per contract after fee, 90 s delay
    k: float = 12.0             # model fit (model_edge only), fitted on that segment's train set
    basis_bps: float = 0.0
    variant_of: str = ""        # set for a new bot built from an original that lost


# Every bot trades all four coins together. For each coin it uses the window length and
# settings where that bot did best on that coin in the 45-day walk-forward test (test-period
# P&L, at least 30 trades, 90 s price delay). backtest_ev = that test's EV per contract.
BOTS = (
    Bot("model_edge", "btc", "5m", {"offset": 60, "edge": 0.0}, +0.0266, k=10.0, basis_bps=2.0),
    Bot("model_edge", "eth", "5m", {"offset": 60, "edge": 0.0}, +0.0472, k=12.0, basis_bps=1.0),
    Bot("model_edge", "sol", "5m", {"offset": 60, "edge": 0.0}, +0.0553, k=12.0, basis_bps=3.0),
    Bot("model_edge", "xrp", "5m", {"offset": 60, "edge": 0.0}, +0.0227, k=12.0, basis_bps=0.0),
    Bot("favourite", "btc", "5m", {"offset": 120, "margin_bps": 5, "max_price": 0.98}, +0.0117),
    Bot("favourite", "eth", "5m", {"offset": 60, "margin_bps": 5, "max_price": 0.95}, +0.0261),
    Bot("favourite", "sol", "1h", {"offset": 120, "margin_bps": 5, "max_price": 0.98}, +0.0595),
    Bot("favourite", "xrp", "1h", {"offset": 60, "margin_bps": 5, "max_price": 0.98}, +0.0593),
    Bot("disagreement", "btc", "5m", {"offset": 60, "margin_bps": 0, "min_price": 0.02}, +0.1909),
    Bot("disagreement", "eth", "5m", {"offset": 60, "margin_bps": 0, "min_price": 0.02}, +0.1694),
    Bot("disagreement", "sol", "5m", {"offset": 120, "margin_bps": 0, "min_price": 0.02}, +0.1062),
    Bot("disagreement", "xrp", "5m", {"offset": 120, "margin_bps": 0, "min_price": 0.02}, +0.1585),
    Bot("momentum", "btc", "1h", {"offset": 180, "lookback_min": 3, "rise": 0.1}, -0.0890),
    Bot("momentum", "eth", "15m", {"offset": 180, "lookback_min": 5, "rise": 0.3}, +0.0302),
    Bot("momentum", "sol", "15m", {"offset": 180, "lookback_min": 5, "rise": 0.3}, -0.0550),
    Bot("momentum", "xrp", "1h", {"offset": 120, "lookback_min": 2, "rise": 0.2}, -0.1923),
    Bot("longshot", "btc", "1h", {"offset": 120, "max_price": 0.05}, -0.0060),
    Bot("longshot", "eth", "1h", {"offset": 180, "max_price": 0.03}, -0.0171),
    Bot("longshot", "sol", "1h", {"offset": 300, "max_price": 0.03}, -0.0177),
    Bot("longshot", "xrp", "15m", {"offset": 300, "max_price": 0.05}, +0.0027),
    Bot("both_sides", "btc", "1h", {"entry": 0.3, "edge": 0.04}, -0.0204),
    Bot("both_sides", "eth", "1h", {"entry": 0.3, "edge": 0.0}, -0.0499),
    Bot("both_sides", "sol", "1h", {"entry": 0.3, "edge": 0.0}, -0.0401),
    Bot("both_sides", "xrp", "1h", {"entry": 0.3, "edge": 0.0}, -0.0143),
    Bot("neversmiling", "btc", "1h", {"tilt": 1}, -0.0179),
    Bot("neversmiling", "eth", "1h", {"tilt": 1}, -0.1460),
    Bot("neversmiling", "sol", "1h", {"tilt": 1}, -0.1383),
    Bot("neversmiling", "xrp", "1h", {"tilt": 1}, -0.0862),
    # ---- variants: NEW bots built from the originals (the originals keep running) ----
    Bot("model_edge_strict", "btc", "5m", {"offset": 60, "edge": 0.03}, +0.0475, k=10.0, basis_bps=2.0, variant_of="model_edge"),
    Bot("model_edge_strict", "eth", "5m", {"offset": 60, "edge": 0.03}, +0.0808, k=12.0, basis_bps=1.0, variant_of="model_edge"),
    Bot("model_edge_strict", "sol", "5m", {"offset": 60, "edge": 0.03}, +0.0743, k=12.0, basis_bps=3.0, variant_of="model_edge"),
    Bot("model_edge_strict", "xrp", "5m", {"offset": 60, "edge": 0.03}, +0.0347, k=12.0, basis_bps=0.0, variant_of="model_edge"),
    Bot("both_sides_strict", "btc", "1h", {"entry": 0.15, "edge": 0.06}, -0.0136, variant_of="both_sides"),
    Bot("both_sides_strict", "eth", "1h", {"entry": 0.15, "edge": 0.06}, -0.0375, variant_of="both_sides"),
    Bot("both_sides_strict", "sol", "1h", {"entry": 0.2, "edge": 0.06}, -0.0353, variant_of="both_sides"),
    Bot("both_sides_strict", "xrp", "1h", {"entry": 0.15, "edge": 0.08}, -0.0019, variant_of="both_sides"),
    Bot("neversmiling_favourite", "btc", "1h", {"offset": 180, "lo": 0.7, "hi": 0.9}, -0.0803, variant_of="neversmiling"),
    Bot("neversmiling_favourite", "eth", "15m", {"offset": 180, "lo": 0.55, "hi": 0.7}, -0.0623, variant_of="neversmiling"),
    Bot("neversmiling_favourite", "sol", "1h", {"offset": 420, "lo": 0.6, "hi": 0.8}, -0.1422, variant_of="neversmiling"),
    Bot("neversmiling_favourite", "xrp", "15m", {"offset": 180, "lo": 0.55, "hi": 0.7}, -0.0343, variant_of="neversmiling"),
    Bot("longshot_close", "btc", "15m", {"offset": 60, "max_price": 0.3, "max_margin_bps": 3}, +0.0369, variant_of="longshot"),
    Bot("longshot_close", "eth", "15m", {"offset": 120, "max_price": 0.3, "max_margin_bps": 3}, +0.1361, variant_of="longshot"),
    Bot("longshot_close", "sol", "5m", {"offset": 60, "max_price": 0.2, "max_margin_bps": 5}, +0.0886, variant_of="longshot"),
    Bot("longshot_close", "xrp", "5m", {"offset": 60, "max_price": 0.3, "max_margin_bps": 3}, +0.0330, variant_of="longshot"),
    Bot("momentum_confirmed", "btc", "1h", {"offset": 120, "lookback_min": 2, "rise": 0.1}, -0.0337, variant_of="momentum"),
    Bot("momentum_confirmed", "eth", "15m", {"offset": 60, "lookback_min": 5, "rise": 0.1}, -0.0119, variant_of="momentum"),
    Bot("momentum_confirmed", "sol", "15m", {"offset": 60, "lookback_min": 2, "rise": 0.2}, -0.0323, variant_of="momentum"),
    Bot("momentum_confirmed", "xrp", "15m", {"offset": 60, "lookback_min": 5, "rise": 0.1}, -0.0192, variant_of="momentum"),
    Bot("momentum_fade", "btc", "15m", {"offset": 180, "lookback_min": 3, "drop": 0.3}, -0.0465, variant_of="momentum"),
    Bot("momentum_fade", "eth", "15m", {"offset": 60, "lookback_min": 2, "drop": 0.2}, -0.0047, variant_of="momentum"),
    Bot("momentum_fade", "sol", "15m", {"offset": 60, "lookback_min": 2, "drop": 0.3}, -0.0450, variant_of="momentum"),
    Bot("momentum_fade", "xrp", "15m", {"offset": 120, "lookback_min": 3, "drop": 0.3}, -0.0281, variant_of="momentum"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_markets (
    slug TEXT PRIMARY KEY, asset TEXT, horizon TEXT, window_start REAL, window_end REAL,
    price_to_beat REAL, settlement_price REAL, outcome TEXT, settled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS paper_quotes (            -- every poll
    slug TEXT, ts REAL, best_bid REAL, best_ask REAL, latency_ms REAL);
CREATE TABLE IF NOT EXISTS paper_points (            -- minute points the bots read
    slug TEXT, ts INTEGER, up_price REAL, down_price REAL, PRIMARY KEY (slug, ts));
CREATE TABLE IF NOT EXISTS paper_index (asset TEXT, ts INTEGER, close REAL, PRIMARY KEY (asset, ts));
CREATE TABLE IF NOT EXISTS paper_trades (
    bot TEXT, slug TEXT, ts INTEGER, side TEXT, price REAL, contracts REAL, fee REAL,
    decided_at REAL, index_age_s REAL, note TEXT, outcome TEXT, pnl REAL,
    PRIMARY KEY (bot, slug, ts, side));
CREATE TABLE IF NOT EXISTS paper_decisions (         -- index bots: one row per market, traded or not
    bot TEXT, slug TEXT, ts INTEGER, leader TEXT, price REAL, margin_bps REAL, p_model REAL,
    index_age_s REAL, traded INTEGER, PRIMARY KEY (bot, slug));
"""


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def _f(x):
    try:
        return float(x["value"] if isinstance(x, dict) else x)
    except (TypeError, ValueError, KeyError):
        return None


@dataclass
class Live:
    slug: str
    asset: str
    horizon: str
    ws: float
    t_end: int
    ptb: float | None
    bots: list = field(default_factory=list)
    pts: list = field(default_factory=list)         # (ts, up, down) minute points
    next_quote: float = 0.0
    next_settle: float = 0.0
    decided: set = field(default_factory=set)
    logged: set = field(default_factory=set)
    settled: bool = False


class PaperTrader:
    def __init__(self, conn: sqlite3.Connection, bots=BOTS, rest: RestClient | None = None,
                 quote_s: float = 3.0, history_s: int = 600, theta: float = 0.095,
                 rps: float = 10.0, log=print) -> None:
        self.conn, self.bots, self.theta, self.log = conn, list(bots), theta, log
        conn.executescript(SCHEMA)
        self.rest = rest or RestClient(None, rps=rps)
        self.quote_s, self.history_s = quote_s, history_s
        self.pairs = {(b.asset, b.horizon) for b in self.bots}
        self.assets = sorted({b.asset for b in self.bots})
        self.live: dict[str, Live] = {}
        self.ticks: dict[str, dict[int, float]] = {a: {} for a in self.assets}
        self.next_disc = self.next_index = 0.0
        self.running = True
        self.stats = {"quotes": 0, "trades": 0, "settled": 0, "errors": 0}
        self._restore()

    # -------------------------------------------------------------- state
    def _restore(self) -> None:
        for slug, a, h, ws, we, ptb in self.conn.execute(
                "SELECT slug, asset, horizon, window_start, window_end, price_to_beat "
                "FROM paper_markets WHERE settled=0"):
            m = self._track(slug, a, h, ws, we, ptb, insert=False)
            m.pts = [tuple(r) for r in self.conn.execute(
                "SELECT ts, up_price, down_price FROM paper_points WHERE slug=? ORDER BY ts", (slug,))]
            m.logged = {(b, ts, s) for b, ts, s in self.conn.execute(
                "SELECT bot, ts, side FROM paper_trades WHERE slug=?", (slug,))}
            m.decided = {b for (b,) in self.conn.execute("SELECT bot FROM paper_decisions WHERE slug=?", (slug,))}
        for a, ts, c in self.conn.execute("SELECT asset, ts, close FROM paper_index WHERE ts > ?",
                                          (int(time.time()) - 900,)):
            self.ticks.setdefault(a, {})[ts] = c

    def _track(self, slug, asset, horizon, ws, we, ptb, insert=True) -> Live:
        m = Live(slug, asset, horizon, ws, int(round(we)), ptb,
                 bots=[b for b in self.bots if (b.asset, b.horizon) == (asset, horizon)])
        self.live[slug] = m
        if insert:
            self.conn.execute("INSERT OR IGNORE INTO paper_markets(slug, asset, horizon, window_start, "
                              "window_end, price_to_beat) VALUES (?,?,?,?,?,?)", (slug, asset, horizon, ws, we, ptb))
        return m

    def stop(self, *_):
        self.running = False

    # -------------------------------------------------------------- data
    def discover(self, now: float) -> None:
        offset = 0
        while offset <= 5000:
            r = self.rest.public_get("/v1/markets", params={
                "active": "true", "closed": "false", "categories": "crypto", "limit": 200, "offset": offset})
            if r.status != 200:
                raise RuntimeError(f"discovery HTTP {r.status}")
            ms = r.json.get("markets", [])
            for x in ms:
                t = x.get("assetPriceTerms") or {}
                if t.get("marketType") != "ASSET_PRICE_MARKET_TYPE_UP_DOWN":
                    continue
                key = ((t.get("asset") or {}).get("symbol"), t.get("horizon"))
                ws, we = _ts(t.get("windowStart")), _ts(t.get("windowEnd"))
                if key in self.pairs and x["slug"] not in self.live and ws and we and we > now + 5:
                    self._track(x["slug"], key[0], key[1], ws, we, _f(t.get("priceToBeat")))
            if len(ms) < 200:
                break
            offset += 200

    def poll_index(self) -> None:
        now = int(time.time())
        for a in self.assets:
            r = self.rest.public_get("/v1/asset-prices/history", params={
                "assets": f"crypto:{a}", "from": now - 300, "to": 0, "bucket": "ASSET_PRICE_BUCKET_1S"})
            if r.status != 200:
                continue
            rows = [(a, int(c["timestamp"]), float(c["close"]))
                    for c in (r.json.get("series") or [{}])[0].get("candles") or []
                    if int(c["timestamp"]) < now and int(c.get("tickCount") or 0) > 0]
            for _, ts, c in rows:
                self.ticks[a][ts] = c
            self.conn.executemany("INSERT OR REPLACE INTO paper_index VALUES (?,?,?)", rows)
            cut = now - 1200
            self.ticks[a] = {t: v for t, v in self.ticks[a].items() if t > cut}

    def poll_quote(self, m: Live, now: float) -> None:
        r = self.rest.public_get(f"/v1/market/slug/{m.slug}")
        if r.status != 200 or not isinstance(r.json, dict):
            return
        x = r.json.get("market", r.json) or {}
        bid, ask = _f(x.get("bestBidQuote")), _f(x.get("bestAskQuote"))
        ptb = _f((x.get("assetPriceTerms") or {}).get("priceToBeat"))
        if ptb is not None and m.ptb is None:
            m.ptb = ptb
            self.conn.execute("UPDATE paper_markets SET price_to_beat=? WHERE slug=?", (ptb, m.slug))
        self.conn.execute("INSERT INTO paper_quotes VALUES (?,?,?,?,?)", (m.slug, now, bid, ask, r.elapsed_ms))
        self.stats["quotes"] += 1
        # one minute point per minute, at the first quote from second :30 on
        mark = int(now // 60 * 60 + 30)
        if now >= mark and (not m.pts or m.pts[-1][0] < mark) and now - mark < 30:
            up = ask if ask is not None else 0.99
            down = round(1 - bid, 4) if bid is not None else 0.99
            m.pts.append((mark, up, down))
            self.conn.execute("INSERT OR REPLACE INTO paper_points VALUES (?,?,?,?)", (m.slug, mark, up, down))
            self.run_bots(m, now)

    # -------------------------------------------------------------- bots
    def _market_dict(self, m: Live) -> dict:
        return {"slug": m.slug, "ws": int(round(m.ws)), "t_end": m.t_end, "pts": list(m.pts),
                "ptb": m.ptb, "ticks": self.ticks.get(m.asset, {})}

    def run_bots(self, m: Live, now: float) -> None:
        for b in m.bots:
            if b.name in INDEX_FAMILIES:
                self._index_bot(b, m, now)
            else:
                for ts, side_up, p, q in ALL_LEGS[b.name](self._market_dict(m), b.params, self.theta):
                    if ts != m.pts[-1][0]:
                        continue            # decide only on the point that just arrived (no hindsight)
                    key = (b.name, ts, "UP" if side_up else "DOWN")
                    if key not in m.logged:
                        m.logged.add(key)
                        self._trade(b, m, ts, key[2], p, q, now, None, "")

    def _index_bot(self, b: Bot, m: Live, now: float) -> None:
        target = m.t_end - b.params["offset"]
        if b.name in m.decided or not m.pts or m.pts[-1][0] > target or target - m.pts[-1][0] > 60:
            return
        if now < target - 60 or m.ptb is None:
            return
        # the latest minute point at or before target: decide only if no later one can still come
        if m.pts[-1][0] + 60 <= target:
            return
        ts, up, down = m.pts[-1]
        tk = {t: v for t, v in self.ticks.get(m.asset, {}).items() if t <= ts}
        m.decided.add(b.name)
        latest = max(tk) if tk else None
        age = ts - latest if latest else None
        est = projected_close(tk, m.t_end, ts)
        if est is None:
            self.conn.execute("INSERT OR REPLACE INTO paper_decisions VALUES (?,?,?,?,?,?,?,?,?)",
                              (b.name, m.slug, ts, None, None, None, None, age, 0))
            return
        margin = (est - m.ptb) / m.ptb
        leader = "UP" if margin >= 0 else "DOWN"
        price = up if leader == "UP" else down
        sig = _sigma(tk, ts)
        p_model = (model_probability(margin, sig, m.t_end, ts, b.k, b.basis_bps / 1e4) if sig else None)
        row = {"offset": b.params["offset"], "price": price, "margin_bps": abs(margin) * 1e4, "p_model": p_model}
        traded = bool(_select([row], b.name, b.params, self.theta))
        self.conn.execute("INSERT OR REPLACE INTO paper_decisions VALUES (?,?,?,?,?,?,?,?,?)",
                          (b.name, m.slug, ts, leader, price, row["margin_bps"], p_model, age, int(traded)))
        if traded:
            note = f"margin {row['margin_bps']:.1f} bps" + (f", model {p_model:.3f}" if p_model else "")
            self._trade(b, m, ts, leader, price, 1, now, age, note)

    def _trade(self, b, m, ts, side, price, q, now, age, note) -> None:
        fee = q * taker_fee(price, theta=self.theta)
        self.conn.execute("INSERT OR IGNORE INTO paper_trades(bot, slug, ts, side, price, contracts, fee, "
                          "decided_at, index_age_s, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (b.name, m.slug, ts, side, price, q, fee, now, age, note))
        self.stats["trades"] += 1
        self.log(f"PAPER BUY  {b.name:12s} {m.slug}  {side:4s} x{q:g} @ {price:.2f}  "
                 f"(T-{m.t_end - ts}s{', ' + note if note else ''})")

    # -------------------------------------------------------------- settlement
    def check_settlement(self, m: Live) -> None:
        r = self.rest.public_get(f"/v1/market/slug/{m.slug}")
        x = (r.json.get("market", r.json) if r.status == 200 and isinstance(r.json, dict) else {}) or {}
        t = x.get("assetPriceTerms") or {}
        close, ptb = _f(t.get("settlementPrice")), _f(t.get("priceToBeat")) or m.ptb
        if x.get("status") != "MARKET_STATUS_RESOLVED" or close is None or ptb is None:
            return
        out = settle_outcome(ptb, close)
        self.conn.execute("UPDATE paper_markets SET settlement_price=?, price_to_beat=?, outcome=?, settled=1 "
                          "WHERE slug=?", (close, ptb, out, m.slug))
        self.conn.execute("UPDATE paper_trades SET outcome=?, pnl=contracts*((CASE WHEN side=? THEN 1.0 ELSE 0.0 END)"
                          " - price) - fee WHERE slug=?", (out, out, m.slug))
        m.settled = True
        self.stats["settled"] += 1
        for bot, side, pnl in self.conn.execute("SELECT bot, side, pnl FROM paper_trades WHERE slug=?", (m.slug,)):
            self.log(f"SETTLED    {bot:12s} {m.slug}  {out}: {side} {pnl:+.3f}")

    # -------------------------------------------------------------- loop
    def step(self, now: float) -> None:
        if now >= self.next_disc:
            self.discover(now)
            self.next_disc = now + 60
        if now >= self.next_index:
            self.poll_index()
            self.next_index = now + 5
        for m in list(self.live.values()):
            if m.settled:
                self.live.pop(m.slug, None)
                continue
            if m.t_end - self.history_s - 5 <= now <= m.t_end + 30 and now >= m.next_quote:
                self.poll_quote(m, now)
                m.next_quote = now + self.quote_s
            if now >= m.t_end + 20 and now >= m.next_settle:
                self.check_settlement(m)
                m.next_settle = now + 30
                if not m.settled and now > m.t_end + 3600:
                    m.settled = True        # give up; trades stay unsettled in the table
        self.conn.commit()

    def run(self, duration_s: float | None = None, status_every: float = 300) -> dict:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        t0 = last = time.time()
        for b in self.bots:
            self.log(f"bot {b.name:12s} -> {b.asset.upper()} {b.horizon:3s} {b.params}")
        while self.running and (duration_s is None or time.time() - t0 < duration_s):
            now = time.time()
            try:
                self.step(now)
            except Exception as exc:            # network blips: log, back off, continue
                self.stats["errors"] += 1
                self.log(f"error: {exc}")
                time.sleep(5)
            if now - last >= status_every:
                last = now
                self.log(f"status {datetime.now(timezone.utc):%H:%M:%S}Z tracking {len(self.live)} markets {self.stats}")
            time.sleep(0.5)
        self.conn.commit()
        self.rest.close()
        return self.stats


def paper_report(conn: sqlite3.Connection, bots=BOTS) -> str:
    conn.executescript(SCHEMA)
    L = ["Paper trading (live public Polymarket US data, no orders)", "=" * 72]
    first = conn.execute("SELECT MIN(ts), MAX(ts) FROM paper_quotes").fetchone()
    if first[0]:
        L.append(f"recorded {datetime.fromtimestamp(first[0], timezone.utc):%Y-%m-%d %H:%M} to "
                 f"{datetime.fromtimestamp(first[1], timezone.utc):%Y-%m-%d %H:%M} UTC "
                 f"({(first[1] - first[0]) / 3600:.1f} h)")
    L.append(f"\n  {'bot':12s} {'coin':9s} {'mkts':>5s} {'trades':>6s} {'open':>5s} {'win':>6s} {'px':>6s} "
             f"{'EV/ct':>8s} {'backtest':>9s} {'total':>8s}")

    def line(label, coin, group):
        mk = trades = open_ = 0
        c = tot = wins = paid = 0.0
        for b in group:
            mk += conn.execute("SELECT COUNT(*) FROM paper_markets WHERE asset=? AND horizon=? AND settled=1",
                               (b.asset, b.horizon)).fetchone()[0]
            rows = conn.execute("SELECT t.price, t.contracts, t.pnl FROM paper_trades t JOIN paper_markets m "
                                "ON m.slug = t.slug WHERE t.bot=? AND m.asset=? AND m.horizon=?",
                                (b.name, b.asset, b.horizon)).fetchall()
            done = [r for r in rows if r[2] is not None]
            trades += len(done)
            open_ += len(rows) - len(done)
            c += sum(r[1] for r in done)
            tot += sum(r[2] for r in done)
            wins += sum(1 for r in done if r[2] > 0)
            paid += sum(r[0] * r[1] for r in done)
        bt = sum(b.backtest_ev for b in group) / len(group)
        ev = f"{tot / c:+8.4f}" if c else f"{'-':>8s}"
        win = wins / trades if trades else 0
        L.append(f"  {label:12s} {coin:9s} {mk:>5d} {trades:>6d} {open_:>5d} {win:>6.1%} "
                 f"{paid / c if c else 0:>6.3f} {ev} {bt:>+9.4f} {tot:>+8.2f}")

    names = list(dict.fromkeys(b.name for b in bots))
    for name in names:
        group = [b for b in bots if b.name == name]
        line(name, "ALL", group)
        if len(group) > 1:
            for b in group:
                line("", f"{b.asset.upper()} {b.horizon}", [b])
    lag = conn.execute("SELECT AVG(index_age_s), MAX(index_age_s), COUNT(*) FROM paper_decisions "
                       "WHERE index_age_s IS NOT NULL").fetchone()
    if lag[2]:
        L.append(f"\nIndex lag at decision time (index bots): avg {lag[0]:.1f} s, max {lag[1]:.0f} s "
                 f"over {lag[2]} decisions. The backtest assumed 0 s.")
    q = conn.execute("SELECT AVG(latency_ms), COUNT(*) FROM paper_quotes").fetchone()
    if q[1]:
        L.append(f"Quotes polled: {q[1]}, avg latency {q[0]:.0f} ms.")
    L.append("\nALL = the bot's four coins together (backtest = their average); mkts = settled markets;\n"
             "trades = settled buys; open = awaiting settlement;\n"
             "EV/ct = P&L per contract after the Tier 1 taker fee; backtest = what the 45-day test predicted.\n"
             "Fills are assumed at the quoted price with unknown size: an upper bound. Many weeks of\n"
             "trades are needed before a difference of a few cents per contract means anything.")
    return "\n".join(L)
