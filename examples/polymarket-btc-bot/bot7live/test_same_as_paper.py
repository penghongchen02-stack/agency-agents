"""Proves bot 7 LIVE makes the same decisions as bot 7 PAPER and sends orders that match them.

Both bots are fed the SAME simulated prices, start prices and order books on a simulated clock (no network,
no orders, no keys). Every paper trade must appear in LIVE with the same market, time, side, price and size,
and LIVE's order must buy that side at exactly that price for that many shares.
Runs on temporary copies, so the real bot7 folder and its trade log are never touched.
Usage: python3 -I test_same_as_paper.py [simulated_hours]"""
import json, math, os, random, shutil, subprocess, sys, tempfile, zlib
sys.dont_write_bytecode = True
D = os.path.dirname(os.path.abspath(__file__))
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
T0 = 1795600800.0                                   # a fixed UTC start time, a multiple of 1 hour

FEED = r'''
import math, random, sys, time, zlib
T = [__T0__]; START = int(__T0__) - 120; END = __T0__ + __SECS__
time.time = lambda: T[0]
def _sleep(x):
    T[0] += x
    if T[0] > END: raise SystemExit(0)
time.sleep = _sleep
VOL = {"btc": 6.0, "eth": 0.35, "sol": 0.012, "xrp": 0.00012}; BASE = {"btc": 60000.0, "eth": 1700.0, "sol": 70.0, "xrp": 0.92}
PATH = {}
for _a in VOL:                                     # same random walk for both bots: depends only on (coin, second)
    _r = random.Random(zlib.crc32(_a.encode())); _p = BASE[_a]; PATH[_a] = []
    for _ in range(int(END - START) + 400): PATH[_a].append(_p); _p += _r.gauss(0, VOL[_a])
def px(a, t): return PATH[a][max(0, int(t) - START)]
CACHE = {}
def tick(a):
    k = (a, int(T[0]))
    if k not in CACHE: CACHE[k] = px(a, T[0])
    return CACHE[k]
def p0(slug):                                      # Polymarket start price = price at window start + a small index offset
    a = {"cpc-btc": "btc", "cpceth-eth": "eth", "cpcsol-sol": "sol", "cpcxrp-xrp": "xrp"}[slug.split("-updown-")[0]]
    st = time.mktime(time.strptime(slug[-16:], "%Y-%m-%d-%H%Mz")) - time.timezone
    return round(px(a, st) + VOL[a] * 0.3, 6)
def pm_read(slug):                                 # order book: deterministic per (market, second)
    rng = random.Random(zlib.crc32(f"{slug}|{int(T[0])}".encode()))
    ask = round(min(0.99, max(0.01, rng.random())), 2); bid = round(max(0.0, ask - rng.choice([0.01, 0.02, 0.05])), 2)
    return [bid, round(rng.uniform(1, 400), 2), ask, round(rng.uniform(1, 400), 2)]
'''


def run(code, cwd):
    r = subprocess.run([sys.executable, "-I", "-c", code], cwd=cwd, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0: sys.exit("simulation failed:\n" + r.stderr[-2000:])


def main():
    tmp = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(D, "..", "bot7"), os.path.join(tmp, "bot7"), ignore=shutil.ignore_patterns("finalmin.jsonl", "logs", "backups", "__pycache__", "pm_settled.json"))
        shutil.copytree(D, os.path.join(tmp, "bot7live"), ignore=shutil.ignore_patterns("live_*", "config.json", "STOP", "__pycache__"))
        feed = FEED.replace("__T0__", repr(T0)).replace("__SECS__", repr(HOURS * 3600))
        lab, live = os.path.join(tmp, "bot7", "lab"), os.path.join(tmp, "bot7live")
        # 1) bot 7 PAPER, unchanged, on the simulated feed
        run(feed + f'''
sys.path.insert(0, {lab!r}); import finalmin as F
F.tick, F.p0, F.PB.pm_read = tick, p0, pm_read
F.main({HOURS * 3600 + 10})
''', lab)
        # 2) bot 7 LIVE on the same feed; act() is replaced by a recorder, so no order can be sent
        run(feed + f'''
import json, os
sys.path.insert(0, {live!r}); import bot7live as L
L.F.tick, L.F.p0, L.F.PB.pm_read = tick, p0, pm_read
L.load_keys = lambda: ("sim", None); L.startup = lambda api, conf: None
out = open(os.path.join({live!r}, "signals.jsonl"), "w")
class Pool:
    def submit(self, fn, api, conf, lim, o, signal): out.write(json.dumps(signal) + "\\n"); out.flush()
import concurrent.futures as cf
_TPE = cf.ThreadPoolExecutor
cf.ThreadPoolExecutor = lambda n: Pool() if n == 4 else _TPE(n)
L.main()
''', live)
        paper = [json.loads(l) for l in open(os.path.join(lab, "finalmin.jsonl"))]
        sig = [json.loads(l) for l in open(os.path.join(live, "signals.jsonl"))]
        sys.path.insert(0, live)
        os.environ.setdefault("BOT7LIVE_API", "http://127.0.0.1:9")
        import bot7live as L
        keys = ("t", "asset", "h", "slug", "checkpoint", "side", "price", "fair", "edge", "start_price", "est_final", "sd", "basis")
        same = len(paper) == len(sig) and all(all(p[k] == s[k] for k in keys) and p["size"] == min(100, s["size_available"]) for p, s in zip(paper, sig))
        print(f"simulated {HOURS:g} hours: paper bot 7 made {len(paper)} trades, LIVE made {len(sig)} signals")
        print(("PASS" if same else "FAIL") + ": every trade identical (time, market, side, price, odds, gap, size)")
        big = dict(L.CONF_DEFAULT, max_usd_per_trade=1e9)
        bad_order, bad_cap = 0, 0
        for p, s in zip(paper, sig):
            b = L.order_body(s["slug"], s["side"], s["price"], L.size_for(s["price"], s["size_available"], big))
            yes = float(b["price"]["value"]); pay = yes if s["side"] == "UP" else 1 - yes
            ok = (b["marketSlug"] == p["slug"] and abs(pay - p["price"]) < 1e-9 and b["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL"
                  and b["type"] == "ORDER_TYPE_LIMIT" and b["intent"] == ("ORDER_INTENT_BUY_LONG" if p["side"] == "UP" else "ORDER_INTENT_BUY_SHORT")
                  and abs(b["quantity"] - math.floor(p["size"] * 100) / 100) < 1e-9)
            bad_order += not ok
            q5 = L.size_for(s["price"], s["size_available"], L.CONF_DEFAULT)
            bad_cap += not (q5 * s["price"] <= 5 + 1e-9 and q5 <= p["size"] + 1e-9)
        print(("PASS" if bad_order == 0 else f"FAIL ({bad_order})") + ": each order buys the same side, same market, at the same price, same shares (limit, immediate-or-cancel)")
        print(("PASS" if bad_cap == 0 else f"FAIL ({bad_cap})") + ": with the default $5 limit, every order is <= $5 and never more shares than paper")
        ups = sum(p["side"] == "UP" for p in paper)
        print(f"  trades: {ups} Up, {len(paper) - ups} Down; checkpoints: " + ", ".join(f"{c}s={sum(p['checkpoint'] == c for p in paper)}" for c in (45, 30, 15)))
        ex = next(((p, s) for p, s in zip(paper, sig) if p["side"] == "DOWN"), None)
        if ex:
            p, s = ex; b = L.order_body(s["slug"], "DOWN", s["price"], L.size_for(s["price"], s["size_available"], big))
            print(f"  example Down: paper bought {p['size']} Down at {p['price']} -> LIVE sends {b['intent']} {b['quantity']} at YES price {b['price']['value']} (= pays {p['price']} per Down share)")
        sys.exit(0 if same and bad_order == 0 and bad_cap == 0 else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
