"""Bot 7Q results: real maker fills with Polymarket US official outcomes, per UTC day. Usage: python3 -I maker_report.py"""
import json, os, sys, collections
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(D, "..", "bot7", "xvenue"))
import pmres as S
ev = [json.loads(l) for l in open(os.path.join(D, "maker_events.jsonl"))] if os.path.exists(os.path.join(D, "maker_events.jsonl")) else []
print("Order activity:", dict(collections.Counter(e["kind"] for e in ev)))
F = os.path.join(D, "maker_fills.jsonl")
if not os.path.exists(F): print("No fills yet."); raise SystemExit
days, wait = collections.OrderedDict(), 0
for r in (json.loads(l) for l in open(F) if l.strip()):
    res = S.pm_result(r["slug"])
    if res is None: wait += 1; continue
    won = (res == "yes") == (r["side"] == "UP"); pnl = (r["filled"] if won else 0) - r["cost_usd"]
    d = days.setdefault(r["time_utc"][:10], [0, 0, 0.0, 0.0]); d[0] += 1; d[1] += won; d[2] += r["cost_usd"]; d[3] += pnl
S.save()
posted = sum(e["kind"] == "posted" for e in ev)
print("REAL maker results (Polymarket US official outcomes; maker rebates not included, they are paid separately):")
for k, d in days.items(): print(f"  {k}: {d[0]} fills, {d[1]} won, spent ${d[2]:.2f}, profit ${d[3]:+.2f}")
print(f"  waiting to settle: {wait}; orders posted: {posted}")
