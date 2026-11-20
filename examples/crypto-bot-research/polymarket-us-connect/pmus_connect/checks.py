"""The connectivity checks. Each returns a CheckResult; none of them trade."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import config
from .auth import SecretKeyError, load_private_key
from .clients import RestClient, ws_probe


@dataclass
class CheckResult:
    name: str
    status: str            # PASS | FAIL | WARN | SKIP
    detail: str
    latency_ms: float | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ---------------------------------------------------------------- public (no key)

def check_gateway(rest: RestClient) -> CheckResult:
    r = rest.public_get("/v1/markets", params={"limit": 1})
    if r.status == 200 and isinstance(r.json, dict) and "markets" in r.json:
        return CheckResult("Public gateway reachable", "PASS",
                           f"GET /v1/markets -> 200", r.elapsed_ms,
                           {"server_time": r.server_time})
    return CheckResult("Public gateway reachable", "FAIL", f"HTTP {r.status}: {r.text[:120]}",
                       r.elapsed_ms)


def check_clock(server_time: float | None) -> CheckResult:
    if server_time is None:
        return CheckResult("Clock skew vs server", "WARN", "no Date header to compare")
    skew = time.time() - server_time
    status = "PASS" if abs(skew) < 5 else ("WARN" if abs(skew) < config.MAX_CLOCK_SKEW_S else "FAIL")
    return CheckResult("Clock skew vs server", status,
                       f"{skew:+.1f} s (signatures rejected beyond ±{config.MAX_CLOCK_SKEW_S} s; "
                       "Date header has 1 s resolution)", data={"skew_s": skew})


def discover_crypto_markets(rest: RestClient, asset: str, horizon: str,
                            max_pages: int = 15) -> tuple[CheckResult, dict | None]:
    """Find live crypto markets and pick a tradable Up/Down window to probe."""
    counts: Counter[tuple[str, str]] = Counter()
    candidates: list[dict] = []
    total_ms = 0.0
    now = time.time()
    for page in range(max_pages):
        r = rest.public_get("/v1/markets", params={
            "active": "true", "closed": "false", "categories": "crypto",
            "limit": 200, "offset": page * 200})
        total_ms += r.elapsed_ms
        if r.status != 200:
            return CheckResult("Crypto market discovery", "FAIL", f"HTTP {r.status}", total_ms), None
        markets = r.json.get("markets", [])
        for m in markets:
            terms = m.get("assetPriceTerms") or {}
            mtype = (terms.get("marketType") or "HAND_LISTED").replace("ASSET_PRICE_MARKET_TYPE_", "")
            counts[(mtype, terms.get("horizon") or "-")] += 1
            end = _ts(terms.get("windowEnd"))
            if (mtype == "UP_DOWN" and end and end > now + 30
                    and (terms.get("asset") or {}).get("symbol") == asset
                    and m.get("status") == "MARKET_STATUS_OPEN"):
                candidates.append(m)
        if len(markets) < 200:
            break
    if not counts:
        return CheckResult("Crypto market discovery", "FAIL", "no crypto markets returned", total_ms), None
    preferred = [m for m in candidates if m["assetPriceTerms"].get("horizon") == horizon]
    pool = preferred or candidates
    pool.sort(key=lambda m: _ts(m["assetPriceTerms"]["windowEnd"]))
    chosen = pool[0] if pool else None
    summary = ", ".join(f"{t}/{h}:{n}" for (t, h), n in counts.most_common())
    if chosen:
        t = chosen["assetPriceTerms"]
        detail = (f"{sum(counts.values())} live crypto markets. Probing {chosen['slug']} "
                  f"({t.get('horizon')} window ends {t.get('windowEnd')}, "
                  f"priceToBeat={(t.get('priceToBeat') or {}).get('value')})")
        return CheckResult("Crypto market discovery", "PASS", detail, total_ms,
                           {"by_type": summary}), chosen
    return CheckResult("Crypto market discovery", "WARN",
                       f"no open {asset} Up/Down window found; types seen: {summary}", total_ms,
                       {"by_type": summary}), None


def check_bbo(rest: RestClient, slug: str) -> CheckResult:
    r = rest.public_get(f"/v1/markets/{slug}/bbo")
    if r.status != 200:
        return CheckResult("Market BBO", "FAIL", f"HTTP {r.status}: {r.text[:120]}", r.elapsed_ms)
    md = r.json.get("marketData", {})
    bid = (md.get("bestBid") or {}).get("value")
    ask = (md.get("bestAsk") or {}).get("value")
    return CheckResult("Market BBO", "PASS",
                       f"state={md.get('state')} bid={bid} ask={ask} "
                       f"depth={md.get('bidDepth')}/{md.get('askDepth')}", r.elapsed_ms)


def check_book(rest: RestClient, slug: str) -> CheckResult:
    r = rest.public_get(f"/v1/markets/{slug}/book")
    if r.status != 200:
        return CheckResult("Market order book", "FAIL", f"HTTP {r.status}: {r.text[:120]}", r.elapsed_ms)
    md = r.json.get("marketData", {})
    return CheckResult("Market order book", "PASS",
                       f"{len(md.get('bids') or [])} bid levels, {len(md.get('offers') or [])} offer levels",
                       r.elapsed_ms)


def check_reference_index(rest: RestClient, asset: str) -> CheckResult:
    """Settlement index (CF Benchmarks BRTI for crypto) via the Asset Prices API."""
    now = int(time.time())
    r = rest.public_get("/v1/asset-prices/history", params={
        "assets": f"crypto:{asset}", "from": now - 180, "to": 0, "bucket": "ASSET_PRICE_BUCKET_1M"})
    if r.status != 200:
        return CheckResult("Settlement index feed", "FAIL", f"HTTP {r.status}: {r.text[:120]}", r.elapsed_ms)
    try:
        candles = r.json["series"][0]["candles"]
        last = candles[-1]
    except (KeyError, IndexError, TypeError):
        return CheckResult("Settlement index feed", "FAIL", "unexpected response shape", r.elapsed_ms)
    age = now - int(last["timestamp"])
    status = "PASS" if age <= 120 else "WARN"
    return CheckResult("Settlement index feed", status,
                       f"crypto:{asset} close={last['close']} (candle age {age} s, "
                       f"{last.get('tickCount')} ticks)", r.elapsed_ms)


def check_auth_host_unsigned(rest: RestClient) -> CheckResult:
    """Proves the trading host is reachable even without keys (expects 401)."""
    r = rest.auth_request("GET", "/v1/account/balances", unsigned=True)
    ok = r.status == 401
    return CheckResult("Trading API host reachable", "PASS" if ok else "WARN",
                       f"unsigned request -> HTTP {r.status} ({'expected' if ok else 'unexpected'})",
                       r.elapsed_ms)


# ---------------------------------------------------------------- authenticated

def check_key_format(creds: config.Credentials) -> CheckResult:
    try:
        load_private_key(creds.secret_key)
    except SecretKeyError as exc:
        return CheckResult("API key format", "FAIL", str(exc))
    return CheckResult("API key format", "PASS", f"key {creds.redacted_key_id}, Ed25519 secret decodes")


def check_auth_get(rest: RestClient, name: str, path: str, summarize) -> CheckResult:
    r = rest.auth_request("GET", path)
    if r.status == 200:
        return CheckResult(name, "PASS", summarize(r.json), r.elapsed_ms)
    hint = {401: "signature/key rejected: check key, secret, clock",
            403: "key lacks permission or account not approved"}.get(r.status, "")
    return CheckResult(name, "FAIL", f"HTTP {r.status} {hint}: {r.text[:120]}", r.elapsed_ms)


def summarize_balances(j: Any) -> str:
    bal = (j or {}).get("balances") or []
    if not bal:
        return "authenticated; no balance rows"
    b = bal[0]
    return (f"authenticated; currentBalance={b.get('currentBalance')} "
            f"buyingPower={b.get('buyingPower')} {b.get('currency', '')}".strip())


def summarize_positions(j: Any) -> str:
    pos = (j or {}).get("positions") or {}
    more = "" if (j or {}).get("eof", True) else " (first page; more available)"
    return f"{len(pos)} open position(s){more}"


def summarize_orders(j: Any) -> str:
    return f"{len((j or {}).get('orders') or [])} open order(s)"


def check_preview(rest: RestClient, slug: str) -> CheckResult:
    """Validates an order WITHOUT submitting it (POST /v1/order/preview)."""
    body = {"request": {"marketSlug": slug, "intent": "ORDER_INTENT_BUY_LONG",
                        "type": "ORDER_TYPE_LIMIT", "price": {"value": "0.01", "currency": "USD"},
                        "quantity": 1, "tif": "TIME_IN_FORCE_GOOD_TILL_CANCEL",
                        "participateDontInitiate": True}}
    r = rest.auth_request("POST", "/v1/order/preview", body=body, allow_preview=True)
    if r.status == 200:
        o = (r.json or {}).get("order", {})
        return CheckResult("Order preview (not submitted)", "PASS",
                           f"validated; state={o.get('state')} commissionBps={o.get('commissionsBasisPoints')}",
                           r.elapsed_ms)
    return CheckResult("Order preview (not submitted)", "FAIL",
                       f"HTTP {r.status}: {r.text[:160]}", r.elapsed_ms)


def check_ws(creds: config.Credentials | None, path: str, subscription: dict | None,
             name: str, wait_s: float) -> CheckResult:
    res = asyncio.run(ws_probe(creds, path, subscription, wait_s))
    if creds is None:
        ok = res["handshake"] == 401
        return CheckResult(name, "PASS" if ok else "WARN",
                           f"unsigned handshake -> {res['handshake'] or res['error']} "
                           f"({'expected 401' if ok else 'unexpected'})")
    if res["handshake"] != 101:
        return CheckResult(name, "FAIL", f"handshake -> {res['handshake'] or res['error']}")
    if res["error"]:
        return CheckResult(name, "FAIL", f"subscribed but server error: {res['error']}",
                           res.get("handshake_ms"))
    if res["first_message_ms"] is None:
        return CheckResult(name, "WARN",
                           f"connected, no data within {wait_s:.0f} s ({res['heartbeats']} heartbeats)",
                           res.get("handshake_ms"))
    return CheckResult(name, "PASS",
                       f"handshake {res['handshake_ms']} ms; first message in {res['first_message_ms']} ms "
                       f"keys={res['message_keys']}", res.get("handshake_ms"))


def market_ws_subscription(slug: str) -> dict:
    return {"requestId": f"pmus-connect-{uuid.uuid4().hex[:8]}",
            "subscriptionType": "SUBSCRIPTION_TYPE_MARKET_DATA_LITE", "marketSlugs": [slug]}


def private_ws_subscription() -> dict:
    return {"requestId": f"pmus-connect-{uuid.uuid4().hex[:8]}",
            "subscriptionType": "SUBSCRIPTION_TYPE_ACCOUNT_BALANCE"}
