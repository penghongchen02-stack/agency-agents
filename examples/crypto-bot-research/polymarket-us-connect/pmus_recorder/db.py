"""SQLite storage for recorded Polymarket US crypto Up/Down data."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    slug TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    horizon TEXT NOT NULL,
    window_start REAL NOT NULL,          -- epoch seconds
    window_end REAL NOT NULL,            -- settlement instant T
    price_to_beat REAL,                  -- open value (null until stamped)
    settlement_price REAL,               -- close value of the index (null until settled)
    contract_settlement REAL,            -- exchange settlement of the Up contract (1 or 0)
    outcome TEXT,                        -- 'UP' | 'DOWN' | null
    tick_size REAL,
    first_seen REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS book_snapshots (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL,
    ts REAL NOT NULL,                    -- local receive time, epoch seconds
    secs_to_close REAL NOT NULL,
    state TEXT,
    best_bid REAL,                       -- best bid for UP (Yes/long)
    best_ask REAL,                       -- best offer for UP (Yes/long)
    bid_qty REAL,
    ask_qty REAL,
    bids_json TEXT,                      -- top levels [[px, qty], ...]
    offers_json TEXT,
    latency_ms REAL,
    source TEXT,                         -- 'ws' (live) or 'rest' (CDN-cached, up to 30 s old)
    cache_age_s REAL                     -- CDN Age header for REST snapshots
);
CREATE INDEX IF NOT EXISTS ix_book_slug_ts ON book_snapshots(slug, ts);
CREATE TABLE IF NOT EXISTS index_ticks (
    asset TEXT NOT NULL,
    ts INTEGER NOT NULL,                 -- 1-second candle start, epoch seconds
    close REAL NOT NULL,
    PRIMARY KEY (asset, ts)
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL,
    trade_time TEXT,
    ts REAL NOT NULL,
    price REAL,
    quantity REAL,
    maker_intent TEXT,
    taker_intent TEXT
);
CREATE INDEX IF NOT EXISTS ix_trades_slug ON trades(slug, ts);
CREATE TABLE IF NOT EXISTS events (
    ts REAL NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(book_snapshots)")}
    for col, typ in (("source", "TEXT"), ("cache_age_s", "REAL")):
        if col not in cols:                           # migrate recordings from older versions
            conn.execute(f"ALTER TABLE book_snapshots ADD COLUMN {col} {typ}")
    return conn


def log_event(conn: sqlite3.Connection, level: str, message: str) -> None:
    conn.execute("INSERT INTO events(ts, level, message) VALUES (?,?,?)",
                 (time.time(), level, message[:1000]))
