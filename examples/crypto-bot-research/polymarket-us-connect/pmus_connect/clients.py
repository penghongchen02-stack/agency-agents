"""Thin REST and WebSocket clients with timing, rate limiting, and the read-only guard."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import websockets

from . import config
from .auth import load_private_key, sign_headers
from .safety import assert_allowed

USER_AGENT = "pmus-connect/1.0 (read-only connectivity check)"


@dataclass
class Response:
    status: int
    json: Any
    text: str
    elapsed_ms: float
    server_time: float | None   # epoch seconds from the Date header
    cache_age: float | None = None   # CDN Age header, seconds (None if not cached)


class _RateLimiter:
    def __init__(self, rps: float) -> None:
        self._interval = 1.0 / rps
        self._next = 0.0
        self._lock = threading.Lock()      # safe to share across worker threads

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self._interval
        if slot > now:
            time.sleep(slot - now)


class RestClient:
    """Synchronous client for both the public gateway and the authenticated API."""

    def __init__(self, credentials: config.Credentials | None = None, timeout: float = 15.0,
                 rps: float = 5.0) -> None:
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})
        self._limiter = _RateLimiter(min(rps, config.PUBLIC_RATE_LIMIT_RPS))
        self._creds = credentials
        self._key = load_private_key(credentials.secret_key) if credentials else None

    def close(self) -> None:
        self._http.close()

    def _send(self, method: str, url: str, headers: dict[str, str] | None = None,
              params: Any = None, body: Any = None, retries: int = 3) -> Response:
        for attempt in range(retries):
            self._limiter.wait()
            start = time.perf_counter()
            r = self._http.request(method, url, headers=headers, params=params, json=body)
            elapsed = (time.perf_counter() - start) * 1000
            if r.status_code == 429 and attempt < retries - 1:
                time.sleep(2 ** attempt)        # docs: wait >= 1 s, exponential backoff
                continue
            try:
                payload = r.json()
            except ValueError:
                payload = None
            server_time = None
            if "date" in r.headers:
                try:
                    server_time = parsedate_to_datetime(r.headers["date"]).timestamp()
                except (TypeError, ValueError):
                    server_time = None
            try:
                age = float(r.headers["age"]) if "age" in r.headers else None
            except ValueError:
                age = None
            return Response(r.status_code, payload, r.text.strip()[:500], elapsed, server_time, age)
        raise RuntimeError("unreachable")

    def public_get(self, path: str, params: Any = None) -> Response:
        return self._send("GET", f"{config.GATEWAY_URL}{path}", params=params)

    def auth_request(self, method: str, path: str, body: Any = None,
                     allow_preview: bool = False, unsigned: bool = False) -> Response:
        assert_allowed(method, path, allow_preview=allow_preview)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if not unsigned:
            if not (self._creds and self._key):
                raise RuntimeError("credentials required")
            headers |= sign_headers(self._creds.key_id, self._key, method, path)
        return self._send(method, f"{config.API_URL}{path}", headers=headers, body=body)


async def ws_probe(credentials: config.Credentials | None, path: str,
                   subscription: dict[str, Any] | None, wait_s: float = 10.0) -> dict[str, Any]:
    """Open a websocket, optionally subscribe, and wait for the first data message.

    Returns a dict with handshake status, latencies, and the first message keys.
    Without credentials it only proves the endpoint is reachable (expects HTTP 401).
    """
    assert_allowed("GET", path)
    url = f"{config.WS_URL}{path}"
    headers: dict[str, str] = {"User-Agent": USER_AGENT}
    if credentials:
        key = load_private_key(credentials.secret_key)
        headers |= sign_headers(credentials.key_id, key, "GET", path)
    result: dict[str, Any] = {"url": url, "handshake": None, "first_message_ms": None,
                              "message_keys": [], "heartbeats": 0, "error": None}
    t0 = time.perf_counter()
    try:
        async with websockets.connect(url, additional_headers=headers, open_timeout=10,
                                      close_timeout=3) as ws:
            result["handshake"] = 101
            result["handshake_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            if subscription is None:
                return result
            t_sub = time.perf_counter()
            await ws.send(json.dumps({"subscribe": subscription}))
            deadline = t_sub + wait_s
            while time.perf_counter() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.perf_counter())
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                if "heartbeat" in msg:
                    result["heartbeats"] += 1
                    continue
                if "error" in msg:
                    result["error"] = str(msg.get("error"))[:200]
                    break
                result["first_message_ms"] = round((time.perf_counter() - t_sub) * 1000, 1)
                result["message_keys"] = sorted(msg.keys())
                break
            await ws.send(json.dumps({"unsubscribe": {"requestId": subscription["requestId"]}}))
    except websockets.InvalidStatus as exc:
        result["handshake"] = exc.response.status_code
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return result
