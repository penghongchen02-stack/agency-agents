"""Minimal Polymarket US helper for bot 7 (read-only public data, no keys, no Kalshi).
Same get() as the research copy of xscan.py, with everything bot 7 does not use removed."""
import json, time, urllib.request, urllib.error

PM = "https://gateway.polymarket.us"
UA = {"User-Agent": "market-research/1.0", "Accept": "application/json"}

def get(url, t=10):
    for a in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(1 + a)
        except Exception:
            time.sleep(0.5)
    return None
