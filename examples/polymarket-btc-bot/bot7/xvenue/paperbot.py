"""Minimal Polymarket US order-book reader for bot 7 (read-only, places no orders).
Same pm_read() as the research copy of paperbot.py, with everything bot 7 does not use removed."""
import os, sys
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import xscan as X

BOOKS = {}
def pm_read(s):
    md = ((X.get(f"{X.PM}/v1/markets/{s}/book", t=4) or {}).get("marketData") or {})
    b = [(float(l["px"]["value"]), float(l["qty"])) for l in md.get("bids", [])]
    o = [(float(l["px"]["value"]), float(l["qty"])) for l in md.get("offers", [])]
    BOOKS[("PM", s)] = dict(yes=sorted(o), no=sorted((round(1 - p, 4), q) for p, q in b))   # ascending cost ladders
    bb = max(b) if b else (0, 0); ba = min(o) if o else (0, 0)
    return [bb[0], bb[1], ba[0], ba[1]]
