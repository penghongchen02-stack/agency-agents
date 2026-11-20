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


def test_index_bot_buys_leader_at_t_minus_60_and_settles():
    bot = Bot("favourite", "btc", "5m", {"offset": 60, "margin_bps": 5, "max_price": 0.95}, 0.0)
    pt, rest = _trader([bot], lambda: (0.89, 0.90))
    t_end = 1_800_000_000                                   # a minute boundary
    m = pt._track("m1", "btc", "5m", t_end - 300, t_end, 100.0)
    pt.ticks["btc"] = {t: 100.2 for t in range(t_end - 400, t_end - 55)}   # 20 bps above the open
    for now in range(t_end - 300, t_end + 1, 3):            # quotes every 3 s through the window
        pt.poll_quote(m, now)
    trades = pt.conn.execute("SELECT bot, ts, side, price FROM paper_trades").fetchall()
    assert trades == [("favourite", t_end - 60, "UP", 0.90)]     # minute point at :00 -> T-60
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


def test_variants_are_causal_and_registered():
    from pmus_recorder.paper import ALL_LEGS, BOTS
    from pmus_recorder.strategies_variants import legs_longshot_close, legs_neversmiling_favourite
    from pmus_recorder.paper import INDEX_FAMILIES
    assert all(b.name in ALL_LEGS or b.name in INDEX_FAMILIES for b in BOTS)
    assert {b.name for b in BOTS if b.variant_of and b.variant_of != "search"} == {
        "model_edge_strict", "both_sides_strict", "neversmiling_favourite",
        "longshot_close", "momentum_confirmed", "momentum_fade"}
    t_end = 2000
    m = {"ws": 1100, "t_end": t_end, "ptb": 100.0,
         "pts": [(t_end - 90, 0.85, 0.16)], "ticks": {t: 100.01 for t in range(t_end - 200, t_end - 90)}}
    # close race (1 bps): the cheap Down side is bought; outcome is never read
    legs = legs_longshot_close(m, {"offset": 60, "max_price": 0.2, "max_margin_bps": 3}, 0.095)
    assert legs == [(t_end - 90, False, 0.16, 1)]
    # ticks after the decision must not change it
    m["ticks"].update({t: 105.0 for t in range(t_end - 89, t_end)})
    assert legs_longshot_close(m, {"offset": 60, "max_price": 0.2, "max_margin_bps": 3}, 0.095) == legs
    fav = legs_neversmiling_favourite(m, {"offset": 60, "lo": 0.7, "hi": 0.9}, 0.095)
    assert fav == [(t_end - 90, True, 0.85, 1)]


def test_dominance_pair_always_pays_at_least_one():
    from pmus_recorder.strategies_cross import pair_trades
    for close, a_up, b_up in ((99.0, False, False), (100.5, True, False), (102.0, True, True)):
        A = {"slug": "a", "horizon": "1h", "ptb": 100.0, "won_up": a_up, "pts": {900: (0.40, 0.61)}}
        B = {"slug": "b", "horizon": "5m", "ptb": 101.0, "won_up": b_up, "pts": {900: (0.45, 0.50)}}
        trades = pair_trades({("btc", 1000): [A, B]}, max_cost=1.0)
        assert len(trades) == 1 and trades[0]["pay"] >= 1     # Up(A) 0.40 + Down(B) 0.50 + fees < 1


def test_arb_paper_records_and_settles_pairs():
    import time as _t
    from pmus_recorder.arb_paper import ArbPaper, arb_report

    class Rest:
        def __init__(self):
            self.resolved = False
            self.q = {"a": (0.40, 0.41), "b": (0.48, 0.50)}       # Up(a) 0.41 + Down(b) 1-0.48 = 0.93

        def public_get(self, path, params=None):
            slug = path.rsplit("/", 1)[-1]
            if path.startswith("/v1/market/slug/"):
                bid, ask = self.q[slug]
                close = {"a": "100.5", "b": "100.5"}[slug]
                ptb = {"a": "100.0", "b": "101.0"}[slug]
                terms = {"priceToBeat": {"value": ptb}}
                if self.resolved:
                    terms["settlementPrice"] = {"value": close}
                return _Resp({"market": {"bestBidQuote": {"value": str(bid)}, "bestAskQuote": {"value": str(ask)},
                                         "assetPriceTerms": terms,
                                         "status": "MARKET_STATUS_RESOLVED" if self.resolved else "MARKET_STATUS_OPEN"}})
            return _Resp({"marketData": {"bids": [], "offers": []}, "markets": []})

    rest = Rest()
    ap = ArbPaper(sqlite3.connect(":memory:"), rest=rest, log=lambda s: None)
    now = _t.time()
    t_end = int(now) + 200
    for slug, h, ptb in (("a", "1h", 100.0), ("b", "5m", 101.0)):
        ap.markets[slug] = {"slug": slug, "asset": "btc", "horizon": h, "t_end": t_end, "ptb": ptb, "next_settle": 0}
        ap.conn.execute("INSERT INTO arb_markets(slug, asset, horizon, window_end, price_to_beat) VALUES (?,?,?,?,?)",
                        (slug, "btc", h, t_end, ptb))
    for g in ap._groups(now):
        for m in g:
            ap.poll(m, now)
        ap.check_pairs(g, now)
    assert ap.conn.execute("SELECT COUNT(*) FROM arb_trades").fetchone()[0] == 1
    rest.resolved = True
    for m in list(ap.markets.values()):
        ap.settle(m, now)
    pay, pnl = ap.conn.execute("SELECT pay, pnl FROM arb_trades").fetchone()
    assert pay == 2.0 and pnl > 1.0                       # close between the opens: both legs win
    assert "pair" in arb_report(ap.conn)


def test_bankroll_shares_money_and_caps_size():
    from pmus_recorder.bankroll import replay
    # two bets open at once at $0.90: 5% of $1,000 = $50 -> 55 contracts, capped at 50
    r = replay([(0, 100, 0.90, 0.10, "bet"), (10, 100, 0.90, 0.10, "bet")], start=1000, cap=50)
    assert r["trades"] == 2 and r["avg_contracts"] == 50 and abs(r["end"] - 1010) < 1e-9
    # a tiny bankroll cannot afford a contract worth more than 5% of it
    assert replay([(0, 100, 0.90, 0.10, "bet")], start=10)["skipped"] == 1
    # a loss takes the whole stake
    assert abs(replay([(0, 100, 0.90, -0.90, "bet")], start=1000, cap=50)["end"] - 955) < 1e-9
