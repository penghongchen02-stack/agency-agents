"""Bot 7 LIVE report: real fills from live_trades.jsonl with Polymarket US official results, per UTC day.
Usage: python3 -I live_report.py"""
import json, os, sys, collections
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(D, "..", "bot7", "xvenue"))
import pmres as S
F = os.path.join(D, "live_trades.jsonl")
if not os.path.exists(F): print("No signals yet."); raise SystemExit
rows = [json.loads(l) for l in open(F) if l.strip()]
st = collections.Counter(r["status"] for r in rows)
print("Signals:", dict(st))
days, wait = collections.OrderedDict(), 0
for r in rows:
    if r.get("mode") != "live" or not r.get("filled"): continue
    res = S.pm_result(r["market_slug"])
    if res is None: wait += 1; continue
    won = (res == "yes") == (r["side"] == "UP"); pnl = (r["filled"] if won else 0) - r["cost_usd"] - r.get("fee_usd", 0)
    d = days.setdefault(r["time_utc"][:10], [0, 0, 0.0, 0.0]); d[0] += 1; d[1] += won; d[2] += r["cost_usd"]; d[3] += pnl
S.save()
print("REAL results (Polymarket US official outcomes; fees before the weekly rebate):")
for k, d in days.items(): print(f"  {k}: {d[0]} fills, {d[1]} won, spent ${d[2]:.2f}, profit ${d[3]:+.2f}")
print(f"  waiting to settle: {wait}")
