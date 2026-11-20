"""Offline tests for the recorder's settlement math and report (no network)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pmus_recorder import db  # noqa: E402
from pmus_recorder.report import build_report  # noqa: E402
from pmus_recorder.settlement import outcome, projected_close, taker_fee, window_average  # noqa: E402


def test_outcome_ties_go_up():
    assert outcome(100.0, 100.0) == "UP"
    assert outcome(100.0, 99.99) == "DOWN"
    assert outcome(100.0, 100.01) == "UP"


def test_window_average_uses_half_open_interval():
    ticks = {t: float(t) for t in range(940, 1001)}          # includes t_end=1000
    avg, n = window_average(ticks, 1000)
    assert n == 60                                           # [940, 1000) excludes 1000
    assert avg == round(sum(range(940, 1000)) / 60, 2)


def test_projected_close_before_and_inside_window():
    ticks = {t: 100.0 for t in range(900, 960)}
    assert projected_close(ticks, 1000, 930) == 100.0        # before window: latest price
    ticks.update({t: 110.0 for t in range(940, 970)})        # 30 s of window fixed at 110
    est = projected_close(ticks, 1000, 969)
    assert abs(est - 110.0) < 1e-9                           # remaining filled with latest (110)
    ticks2 = {t: 110.0 for t in range(940, 970)}
    ticks2[969] = 90.0
    est2 = projected_close(ticks2, 1000, 969)
    assert abs(est2 - (110 * 29 + 90 + 90 * 30) / 60) < 1e-9


def test_taker_fee_matches_docs_example():
    # docs: Tier 4 theta 0.0695, 100 contracts at p=0.50 -> $1.74 (rounded)
    assert round(taker_fee(0.50, 100, theta=0.0695), 2) == 1.74
    assert taker_fee(0.97) < 0.003


def test_report_on_synthetic_recording(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    we = 1_000_000
    conn.execute("INSERT INTO markets(slug, asset, horizon, window_start, window_end, price_to_beat, "
                 "settlement_price, contract_settlement, outcome, first_seen, updated) "
                 "VALUES ('m1','btc','15m',?,?,100.0,105.0,1.0,'UP',?,?)",
                 (we - 900, we, time.time(), time.time()))
    conn.executemany("INSERT INTO index_ticks(asset, ts, close) VALUES ('btc',?,105.0)",
                     [(t,) for t in range(we - 200, we)])
    for secs in (100, 70, 40, 20, 5):
        conn.execute("INSERT INTO book_snapshots(slug, ts, secs_to_close, best_bid, best_ask, "
                     "bids_json, offers_json, latency_ms) VALUES ('m1',?,?,0.95,0.97,'[]','[]',40)",
                     (we - secs, secs))
    conn.commit()
    rep = build_report(conn)
    assert rep["coverage"]["markets_settled"] == 1
    assert rep["settlement_check"][0]["error"] == 0.0
    row = rep["late_window"]["15m 30-10s"]
    assert row["leader_win_rate"] == 1.0
    assert row["avg_leader_ask"] == 0.97
    assert abs(row["naive_ev_per_contract_after_taker_fee"] - (1 - 0.97 - taker_fee(0.97))) < 1e-4


def test_ws_messages_flow_into_db(tmp_path):
    import queue
    from pmus_connect.config import Credentials
    from pmus_recorder.recorder import Config, Recorder, Tracked
    from pmus_recorder.ws_feed import MarketsFeed
    import base64, os as _os

    q = queue.Queue()
    feed = MarketsFeed(Credentials("k", base64.b64encode(_os.urandom(32)).decode()), q)
    now = time.time()
    feed._handle({"heartbeat": {}}, now)
    feed._handle({"marketData": {"marketSlug": "m1", "state": "MARKET_STATE_OPEN",
                                 "bids": [{"px": {"value": "0.95"}, "qty": "10"}],
                                 "offers": [{"px": {"value": "0.97"}, "qty": "5"}]}}, now)
    feed._handle({"trade": {"marketSlug": "m1", "price": {"value": "0.97"}, "quantity": {"value": "5"},
                            "tradeTime": "2026-11-20T14:00:00Z",
                            "maker": {"intent": "ORDER_INTENT_SELL_LONG"},
                            "taker": {"intent": "ORDER_INTENT_BUY_LONG"}}}, now)
    feed._handle({"error": "bad slug"}, now)
    assert q.qsize() == 3

    conn = db.connect(tmp_path / "w.sqlite")

    class NoNet:            # recorder must not touch the network in this test
        def close(self):
            pass

    rec = Recorder(conn, Config(), rest=NoNet(), feed=None, feed_queue=q)
    rec.tracked["m1"] = Tracked("m1", "btc", "15m", now - 800, now + 100, 100.0)
    rec.drain_feed()
    row = conn.execute("SELECT source, best_bid, best_ask, round(secs_to_close) FROM book_snapshots").fetchone()
    assert row == ("ws", 0.95, 0.97, 100.0)
    assert conn.execute("SELECT price, quantity, taker_intent FROM trades").fetchone() == (
        0.97, 5.0, "ORDER_INTENT_BUY_LONG")
    assert conn.execute("SELECT COUNT(*) FROM events WHERE level='WARN'").fetchone()[0] == 1
