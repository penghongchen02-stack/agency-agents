"""Offline tests for the paper trader: fake exchange, no network, no orders."""

import sqlite3

from pmus_recorder.paper import BOTS, Bot, PaperTrader, paper_report
from pmus_recorder.strategies_extra import LEGS, settle_legs, simulate_both_sides


class _Resp:
    def __init__(self, json, status=200):
        self.json, self.status, self.elapsed_ms, self.cache_age = json, status, 5.0, None


class FakeRest:
    """Serves /v1/market/slug quotes and a resolved settlement; records every path asked."""

    def __init__(self, quotes, outcome_close, ptb=100.0):
        self.quotes, self.settle_px, self.ptb, self.paths, self.resolved = quotes, outcome_close, ptb, [], False

    def public_get(self, path, params=None):
        self.paths.append(path)
        if path.startswith("/v1/market/slug/"):
            bid, ask = self.quotes()
            terms = {"priceToBeat": {"value": str(self.ptb)}}
            if self.resolved:
                terms["settlementPrice"] = {"value": str(self.settle_px)}
            return _Resp({"market": {"bestBidQuote": {"value": str(bid)}, "bestAskQuote": {"value": str(ask)},
                                     "assetPriceTerms": terms,
                                     "status": "MARKET_STATUS_RESOLVED" if self.resolved else "MARKET_STATUS_OPEN"}})
        return _Resp({"markets": [], "series": [{"candles": []}]})

    def close(self):
        pass


def _trader(bots, quotes, close=101.0):
    rest = FakeRest(quotes, close)

    pt = PaperTrader(sqlite3.connect(":memory:"), bots=bots, rest=rest, log=lambda s: None)
    return pt, rest


def test_index_bot_buys_leader_at_t_minus_90_and_settles():
    bot = Bot("favourite", "btc", "5m", {"offset": 60, "margin_bps": 5, "max_price": 0.95}, 0.0)
    pt, rest = _trader([bot], lambda: (0.89, 0.90))
    t_end = 1_800_000_000                                   # a minute boundary
    m = pt._track("m1", "btc", "5m", t_end - 300, t_end, 100.0)
    pt.ticks["btc"] = {t: 100.2 for t in range(t_end - 400, t_end - 85)}   # 20 bps above the open
    for now in range(t_end - 300, t_end + 1, 3):            # quotes every 3 s through the window
        pt.poll_quote(m, now)
    trades = pt.conn.execute("SELECT bot, ts, side, price FROM paper_trades").fetchall()
    assert trades == [("favourite", t_end - 90, "UP", 0.90)]
    rest.resolved = True
    pt.check_settlement(m)
    pnl = pt.conn.execute("SELECT pnl FROM paper_trades").fetchone()[0]
    assert abs(pnl - (1 - 0.90 - 0.095 * 0.90 * 0.10)) < 1e-9
    assert "favourite" in paper_report(pt.conn, bots=[bot])


def test_paper_never_calls_a_trading_endpoint():
    pt, rest = _trader(list(BOTS), lambda: (0.48, 0.52))
    t_end = 1_800_000_000
    m = pt._track("m2", "xrp", "1h", t_end - 3600, t_end, 100.0)
    for now in range(t_end - 600, t_end + 30, 3):
        pt.poll_quote(m, now)
    assert all(p.startswith(("/v1/market/slug/", "/v1/markets", "/v1/asset-prices")) for p in rest.paths)
    assert not any("order" in p for p in rest.paths)


def test_live_legs_match_the_backtest_simulator():
    pts = [(1000 + 60 * i, up, round(1.02 - up, 2)) for i, up in enumerate((0.55, 0.29, 0.40, 0.60, 0.70))]
    m = {"ws": 900, "t_end": 1400, "pts": pts, "won_up": True}
    params = {"entry": 0.3, "edge": 0.0}
    assert settle_legs(LEGS["both_sides"](m, params, 0.095), True, 0.095) == simulate_both_sides(m, params, 0.095)
