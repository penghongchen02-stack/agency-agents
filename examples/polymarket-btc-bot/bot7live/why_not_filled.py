"""Explains the last not-filled orders in plain words. Shows no keys. Usage: python3 -I why_not_filled.py [count]"""
import json, os, sys
D = os.path.dirname(os.path.abspath(__file__)); N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
rows = [json.loads(l) for l in open(os.path.join(D, "live_trades.jsonl")) if l.strip()]
miss = [r for r in rows if r.get("status") in ("not_filled", "rejected")][-N:]
print(f"{len(rows)} signals; showing the last {len(miss)} not filled / rejected\n")
for r in miss:
    o = r.get("final_order") or {}; b = r.get("book_after_miss") or {}; req = r.get("order_request") or {}
    print(f"{r['time_utc']}  {r['asset'].upper()} {r['h']} {r['side']} at {r['price']} ({r['checkpoint']}s left)  -> {r['status']}")
    print(f"  sent: {req.get('intent')} {req.get('quantity')} at YES price {(req.get('price') or {}).get('value')}  http {r.get('http')}")
    print(f"  Polymarket says: state {o.get('state')}, filled {o.get('cumQuantity')}, left {o.get('leavesQuantity')}")
    if r.get("response"): print(f"  reject details: {json.dumps(r['response'])[:300]}")
    if b: print(f"  book right after: bid {b.get('bid')} ask {b.get('ask')} -> our price still shown: {b.get('price_still_shown')}")
    print()
