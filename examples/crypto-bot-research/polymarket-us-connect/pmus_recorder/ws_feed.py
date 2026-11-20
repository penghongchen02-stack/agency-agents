"""Real-time order books and trades from the authenticated markets websocket.

The public REST book (`gateway.polymarket.us/v1/markets/{slug}/book`) is served
through a CDN with `Cache-Control: max-age=30`, so it can be up to 30 s stale. A
late-window strategy needs the live book, which Polymarket US only provides on
`wss://api.polymarket.us/v1/ws/markets` (API key required).

The feed runs in a background thread. It pushes parsed events onto a queue, and the
recorder's main thread writes them to SQLite. It reconnects with backoff, re-signs
on every connect, and resubscribes to every tracked market.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid

import websockets

from pmus_connect import config
from pmus_connect.auth import load_private_key, sign_headers
from pmus_connect.safety import assert_allowed

PATH = "/v1/ws/markets"
MAX_SLUGS_PER_SUB = 100          # docs: max 100 markets per subscription


def _f(x):
    try:
        return float(x["value"] if isinstance(x, dict) else x)
    except (TypeError, ValueError, KeyError):
        return None


class MarketsFeed:
    def __init__(self, creds: config.Credentials, out: queue.Queue) -> None:
        assert_allowed("GET", PATH)
        self.creds = creds
        self.key = load_private_key(creds.secret_key)
        self.out = out
        self.slugs: set[str] = set()
        self._pending: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pmus-ws", daemon=True)
        self.connected = False

    # -------------------------------------------------- public API (main thread)
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def add(self, slug: str) -> None:
        if slug not in self.slugs:
            self.slugs.add(slug)
            self._pending.put(slug)

    # -------------------------------------------------- background thread
    def _run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._session()
                backoff = 1.0
            except Exception as exc:     # reconnect on any failure
                self.connected = False
                self.out.put(("event", "WARN", f"ws disconnected: {type(exc).__name__}: {exc}"))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _subscribe(self, ws, slugs: list[str]) -> None:
        for i in range(0, len(slugs), MAX_SLUGS_PER_SUB):
            chunk = slugs[i:i + MAX_SLUGS_PER_SUB]
            for sub_type in ("SUBSCRIPTION_TYPE_MARKET_DATA", "SUBSCRIPTION_TYPE_TRADE"):
                await ws.send(json.dumps({"subscribe": {
                    "requestId": f"rec-{uuid.uuid4().hex[:8]}",
                    "subscriptionType": sub_type, "marketSlugs": chunk}}))

    async def _session(self) -> None:
        headers = sign_headers(self.creds.key_id, self.key, "GET", PATH)
        async with websockets.connect(f"{config.WS_URL}{PATH}", additional_headers=headers,
                                      open_timeout=10, ping_interval=20, max_size=8 * 2 ** 20) as ws:
            self.connected = True
            self.out.put(("event", "INFO", "ws connected"))
            while not self._pending.empty():          # current slugs are resubscribed below
                self._pending.get_nowait()
            if self.slugs:
                await self._subscribe(ws, sorted(self.slugs))
            last_heartbeat = time.time()
            while not self._stop.is_set():
                new = []
                while not self._pending.empty():
                    new.append(self._pending.get_nowait())
                if new:
                    await self._subscribe(ws, new)
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    if time.time() - last_heartbeat > 90:
                        raise ConnectionError("no messages or heartbeats for 90 s")
                    continue
                last_heartbeat = time.time()
                self._handle(json.loads(raw), time.time())

    def _handle(self, msg: dict, now: float) -> None:
        if "heartbeat" in msg:
            return
        if "error" in msg:
            self.out.put(("event", "WARN", f"ws error: {str(msg['error'])[:200]}"))
            return
        md = msg.get("marketData")
        if md:
            bids = [[_f(l.get("px")), _f(l.get("qty"))] for l in (md.get("bids") or [])[:10]]
            offers = [[_f(l.get("px")), _f(l.get("qty"))] for l in (md.get("offers") or [])[:10]]
            self.out.put(("book", md.get("marketSlug"), now, md.get("state"), bids, offers))
            return
        tr = msg.get("trade")
        if tr:
            self.out.put(("trade", tr.get("marketSlug"), now, tr.get("tradeTime"), _f(tr.get("price")),
                          _f(tr.get("quantity")), (tr.get("maker") or {}).get("intent"),
                          (tr.get("taker") or {}).get("intent")))
