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


from pmus_recorder.study import PRICE_DELAY_S  # noqa: E402


def _synthetic_backfill(tmp_path, n=90):
    from pmus_recorder.backfill import SCHEMA
    conn = db.connect(tmp_path / "s.sqlite")
    conn.executescript(SCHEMA)
    base = 1_800_000_000
    for i in range(n):
        we = base + i * 900
        up = i % 3 != 0                       # 2/3 of markets resolve UP
        close = 101.0 if up else 99.0
        conn.execute("INSERT INTO markets(slug, asset, horizon, window_start, window_end, price_to_beat, "
                     "settlement_price, outcome, first_seen, updated) VALUES (?,?,?,?,?,?,?,?,0,0)",
                     (f"m{i}", "btc", "15m", we - 900, we, 100.0, close, "UP" if up else "DOWN"))
        # index sits at the final value for the last 200 s (leader is right)
        conn.executemany("INSERT OR REPLACE INTO index_ticks VALUES ('btc',?,?)",
                         [(t, close) for t in range(we - 200, we)])
        # price points at T-180/-120/-60: leader buyable at 0.95, except every 5th market at 0.99
        lead_px = 0.99 if i % 5 == 0 else 0.95
        for d in (180, 120, 60):
            upp, dnp = (lead_px, 1 - lead_px + 0.01) if up else (1 - lead_px + 0.01, lead_px)
            # stored stamps run PRICE_DELAY_S early, as on the real endpoint
            conn.execute("INSERT INTO price_points VALUES (?,?,?,?)",
                         (f"m{i}", we - d - PRICE_DELAY_S, upp, dnp))
        conn.execute("INSERT INTO backfill_done VALUES (?,3,0)", (f"m{i}",))
    conn.commit()
    return conn


def test_price_points_are_used_only_after_the_delay(tmp_path):
    from pmus_recorder.study import load
    from pmus_recorder.strategies_extra import load_markets
    conn = _synthetic_backfill(tmp_path)
    raw = {ts for (ts,) in conn.execute("SELECT ts FROM price_points WHERE slug='m1'")}
    _, _, points = load(conn)
    assert {p[0] for p in points["m1"]} == {t + PRICE_DELAY_S for t in raw}
    m1 = next(m for m in load_markets(conn) if m["slug"] == "m1")
    assert {p[0] for p in m1["pts"]} == {t + PRICE_DELAY_S for t in raw}


def test_study_excludes_unbuyable_and_has_no_lookahead(tmp_path):
    from pmus_recorder.study import run_study, evaluate, observations, load
    conn = _synthetic_backfill(tmp_path)
    rows = observations(*load(conn))
    assert all(r["won"] for r in rows)                      # leader always right in this fixture
    res = evaluate(rows, 60, 0, 0.98, 0.095)
    assert res["n"] == sum(1 for r in rows if r["offset"] == 60 and r["price"] < 0.99)
    assert abs(res["avg_price"] - 0.95) < 1e-9              # the 0.99 points were never "filled"
    out = run_study(conn)
    assert out["availability"][60]["leader_price>=0.99"] > 0
    assert out["test_result"]["n"] > 0


def test_projection_ignores_future_ticks():
    ticks = {t: 100.0 for t in range(900, 1000)}
    ticks.update({t: 200.0 for t in range(961, 1000)})       # jump AFTER decision time 960
    assert projected_close(ticks, 1000, 960) == 100.0


def test_model_probability_shrinks_with_time_and_grows_with_margin():
    from pmus_recorder.strategies import model_probability
    T = 10_000
    p_far = model_probability(0.0005, 1e-4, T, T - 180)
    p_near = model_probability(0.0005, 1e-4, T, T - 10)
    assert 0.5 < p_far < p_near <= 1.0
    assert model_probability(0.002, 1e-4, T, T - 180) > p_far


def test_compare_runs_on_synthetic(tmp_path):
    from pmus_recorder.strategies import compare
    conn = _synthetic_backfill(tmp_path)
    # add noise to the index so volatility is defined
    import random
    random.seed(1)
    rows = conn.execute("SELECT asset, ts, close FROM index_ticks").fetchall()
    conn.executemany("UPDATE index_ticks SET close=? WHERE asset=? AND ts=?",
                     [(c * (1 + random.gauss(0, 1e-5)), a, t) for a, t, c in rows])
    conn.commit()
    res = compare(conn, min_trades=5)
    assert "btc 15m" in res["segments"]
    fav = res["segments"]["btc 15m"]["families"]["favourite"]
    assert fav["test"]["n"] > 0 and fav["test"]["avg_price"] < 0.99


def test_extra_families_on_synthetic():
    from pmus_recorder.strategies_extra import (simulate_both_sides, simulate_longshot,
                                                simulate_momentum, simulate_neversmiling)
    T = 10_000
    m = {"ws": T - 300, "t_end": T, "won_up": True, "pts": [
        (T - 240, 0.45, 0.56), (T - 180, 0.60, 0.42), (T - 120, 0.80, 0.21), (T - 60, 0.97, 0.04)]}
    # legged pair: Up at 0.45, then Down at 0.42 -> pair 0.87 + fees < 1: locked profit
    n, pnl, _ = simulate_both_sides(m, {"entry": 0.45, "edge": 0.0}, 0.095)
    assert n == 2 and abs(pnl - (1 - 0.45 - 0.42 - taker_fee(0.45) - taker_fee(0.42))) < 1e-9
    # longshot at T-60 buys Down at 0.04 and loses it
    n, pnl, px = simulate_longshot(m, {"offset": 60, "max_price": 0.05}, 0.095)
    assert n == 1 and px == 0.04 and pnl < 0
    # momentum: Up rose 0.37 over 2 min to 0.97 -> buy Up, wins
    n, pnl, px = simulate_momentum(m, {"offset": 60, "lookback_min": 2, "rise": 0.30}, 0.095)
    assert px == 0.97 and pnl > 0
    # neversmiling: buys in-band sides inside 10%-90% of the window
    n, pnl, px = simulate_neversmiling(m, {"tilt": 2}, 0.095)
    assert n >= 3 and 0.30 <= px <= 0.70
    # $0.99 is never bought
    m2 = {"ws": T - 300, "t_end": T, "won_up": True, "pts": [(T - 60, 0.99, 0.01)]}
    assert simulate_momentum(m2, {"offset": 60, "lookback_min": 1, "rise": 0.0}, 0.095) is None
