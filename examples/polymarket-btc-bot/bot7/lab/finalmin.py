"""Bot 7: final-minute settlement bot (read-only, paper). Up/Down markets settle on the average of the last 60 s.
Coinbase spot is read every second for BTC, ETH, SOL, XRP. With r seconds left, the average so far is known; the rest is
modelled as a random walk using the last minute's per-second volatility. A running Coinbase-vs-index offset is learned
from each window's published start price. Fair P(Up) = N((expected final average - start price) / sd).
At 45, 30 and 15 s left, read the 5m (and 15m / 1h when they also end then) Up/Down books; signal when fair - ask >= 3c
for Up or Down. Paper-buy 100 shares at the real ask. Output: finalmin.jsonl.  Usage: python3 -I finalmin.py <seconds>"""
import json, math, os, sys, time, urllib.request, collections, concurrent.futures as cf
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(D, "..", "xvenue"))
import xscan as X, paperbot as PB
PRE = {"btc": "cpc-btc", "eth": "cpceth-eth", "sol": "cpcsol-sol", "xrp": "cpcxrp-xrp"}
UA = {"User-Agent": "market-research/1.0"}
def tick(a):
    with urllib.request.urlopen(urllib.request.Request(f"https://api.exchange.coinbase.com/products/{a.upper()}-USD/ticker", headers=UA), timeout=3) as r:
        d = json.load(r); return (float(d["bid"]) + float(d["ask"])) / 2
def Ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def p0(slug):
    m = (X.get(f"{X.PM}/v1/market/slug/{slug}", t=5) or {}).get("market") or {}
    v = ((m.get("assetPriceTerms") or {}).get("priceToBeat") or {}).get("value"); return float(v) if v else None
def fee(p): return 0.095 * 0.3 * p * (1 - p)
def main(secs):
    out = open(os.path.join(D, "finalmin.jsonl"), "a"); end = time.time() + secs
    hist = {a: collections.deque(maxlen=400) for a in PRE}; basis = {a: 0.0 for a in PRE}; done = set(); fitted = set()
    with cf.ThreadPoolExecutor(8) as ex:
        while time.time() < end:
            t0 = time.time()
            def safe(a):
                try: return tick(a)
                except Exception: return None
            for a, p in zip(PRE, ex.map(safe, PRE)):
                if p is not None: hist[a].append((t0, p))
            Eprev = int(t0) // 300 * 300                 # learn the offset from the window that just started
            if t0 - Eprev > 20:
                for a in PRE:
                    if (a, Eprev) in fitted: continue
                    fitted.add((a, Eprev)); P = p0(f"{PRE[a]}-updown-5m-{time.strftime('%Y-%m-%d-%H%Mz', time.gmtime(Eprev))}")
                    w = [p for t, p in hist[a] if Eprev - 60 <= t < Eprev]
                    if P and len(w) >= 40: basis[a] = 0.7 * basis[a] + 0.3 * (P - sum(w) / len(w))
            E = (int(t0) // 300 + 1) * 300; r = E - t0
            for chk in (45, 30, 15):
                if not (chk - 1.2 <= r <= chk): continue
                for a in PRE:
                    w = [p for t, p in hist[a] if E - 60 <= t <= t0]; full = [p for t, p in hist[a] if t >= t0 - 75]
                    if len(w) < 60 - chk - 6 or len(full) < 40: continue
                    S = full[-1]; diffs = [y - x for x, y in zip(full, full[1:])]
                    sig = max((sum(d * d for d in diffs) / len(diffs)) ** 0.5, 1e-9)
                    mean = (sum(w) + S * r) / (len(w) + r) + basis[a]
                    sd = (r / 60) * sig * math.sqrt(r / 3)
                    for h, L in (("5m", 300), ("15m", 900), ("1h", 3600)):
                        if E % L: continue
                        slug = f"{PRE[a]}-updown-{h}-{time.strftime('%Y-%m-%d-%H%Mz', time.gmtime(E - L))}"
                        P = p0(slug)
                        if not P: continue
                        fair = Ncdf((mean - P) / sd)
                        bid, bs, ask, asz = PB.pm_read(slug)[:4]
                        for side, price, size, f_ in (("UP", ask, asz, fair), ("DOWN", round(1 - bid, 4) if bid > 0 else 0, bs, 1 - fair)):
                            if 0 < price < 1 and f_ - price - fee(price) >= 0.03 and size >= 10 and slug not in done:
                                done.add(slug)        # one trade per market (first signal only), never the other side later
                                out.write(json.dumps(dict(t=round(t0, 2), bot="7-final-minute", asset=a, h=h, slug=slug, checkpoint=chk, side=side,
                                          price=price, size=min(100, size), fair=round(f_, 4), edge=round(f_ - price - fee(price), 4), start_price=P,
                                          est_final=round(mean, 6), sd=round(sd, 6), basis=round(basis[a], 6))) + "\n"); out.flush()
            time.sleep(max(0, 1 - (time.time() - t0)))
if __name__ == "__main__":
    main(float(sys.argv[1]))
