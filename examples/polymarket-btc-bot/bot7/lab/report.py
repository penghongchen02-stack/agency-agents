"""Bot 7 report (paper). Reads lab/finalmin.jsonl, gets each market's official result from Polymarket US,
and prints totals per day and overall. Only the first trade in each market counts. Never changes the bot or its log.
Usage: python3 -I lab/report.py"""
import json, os, sys, time, collections
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(D, "..", "xvenue"))
import pmres as S
F = os.path.join(D, "finalmin.jsonl")
if not os.path.exists(F): print("No trades yet. Bot 7 writes its first trade in the last minute of a market."); raise SystemExit
rows = sorted((json.loads(l) for l in open(F) if l.strip()), key=lambda r: r["t"])
seen, days, wait = set(), collections.OrderedDict(), 0
for r in rows:
    if r["slug"] in seen: continue
    seen.add(r["slug"]); res = S.pm_result(r["slug"])
    if res is None: wait += 1; continue
    p = r["price"]; win = (res == "yes") == (r["side"] == "UP")
    pnl = ((1 if win else 0) - p - 0.095 * 0.3 * p * (1 - p)) * r["size"]
    d = days.setdefault(time.strftime("%Y-%m-%d", time.gmtime(r["t"])), [0, 0, 0.0, 0.0])
    d[0] += 1; d[1] += win; d[2] += pnl; d[3] += r["size"]
S.save()
print("Bot 7 paper results (results from Polymarket US; times UTC)")
T = [0, 0, 0.0, 0.0]
for k, d in days.items():
    print(f"  {k}: {d[0]:4d} markets, {d[1]:4d} won ({100*d[1]/d[0]:3.0f}%), {100*d[2]/d[3]:+5.1f}c/share, paper ${d[2]:+9.2f}")
    T = [a + b for a, b in zip(T, d)]
if T[0]: print(f"  TOTAL     : {T[0]:4d} markets, {T[1]:4d} won ({100*T[1]/T[0]:3.0f}%), {100*T[2]/T[3]:+5.1f}c/share, paper ${T[2]:+9.2f}")
print(f"  waiting for Polymarket to settle: {wait}")
