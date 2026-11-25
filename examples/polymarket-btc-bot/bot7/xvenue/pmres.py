"""Polymarket US market results only (no Kalshi). Cached in pm_settled.json."""
import json, os, sys
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import xscan as X
F = os.path.join(D, "pm_settled.json")
cache = json.load(open(F)) if os.path.exists(F) else {}
def pm_result(slug):
    if slug in cache: return cache[slug]
    m = (X.get(f"{X.PM}/v1/market/slug/{slug}") or {}).get("market") or {}
    if m.get("status") != "MARKET_STATUS_RESOLVED": return None
    op = json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices")
    cache[slug] = "yes" if float(op[0]) > 0.5 else "no"; return cache[slug]
def save(): json.dump(cache, open(F, "w"))
