"""Bot 7 LIVE: places REAL orders on Polymarket US using exactly bot 7's paper rules.

Decision rules are bot 7's (../bot7/lab/finalmin.py): the same helper functions are imported from that file
unchanged, and the loop below is a copy of its main() in which only the paper-trade write is replaced by a
real order. Bot 7's fingerprints (../bot7/SHA256SUMS) are checked before anything starts.

Safety:
  * mode "dry_run" (default): signs in, checks the account, and for each signal calls Polymarket's
    PREVIEW endpoint only. No order is placed.
  * mode "live": places LIMIT + IMMEDIATE-OR-CANCEL orders at bot 7's price, so it can never pay more than
    the price bot 7 saw; anything not available right away is cancelled by the exchange.
  * Hard limits from config.json: max dollars per trade, max shares per trade, max dollars spent per UTC
    day, and a daily loss limit (counted from Polymarket's official results). Hitting a limit stops new orders.
  * In live mode, Down (NO) orders stay OFF until "down_price_confirmed": true, because Polymarket prices every
    order on the YES side. Dry run previews Down orders too, so you can confirm the price first (see GUIDE.md).
  * Create a file named STOP in this folder to stop new orders at once.
  * Keys are read from ~/.bot7live/keys.json (permissions 600) or the environment, never from this folder,
    and are never printed or logged.
Usage: python3 -I bot7live.py
"""
import json, math, os, sys, time, base64, threading, subprocess, collections, urllib.request, urllib.error
import concurrent.futures as cf

D = os.path.dirname(os.path.abspath(__file__))
B7 = os.path.normpath(os.path.join(D, "..", "bot7"))
API = os.environ.get("BOT7LIVE_API", "https://api.polymarket.us")
CONF_DEFAULT = dict(mode="dry_run", max_usd_per_trade=5.0, max_shares_per_trade=100, daily_max_spend_usd=100.0,
                    daily_max_loss_usd=50.0, down_price_confirmed=False)
LOG = os.path.join(D, "live_trades.jsonl")
ERR = os.path.join(D, "live_errors.log")
ULOCK = threading.Lock()


def say(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S UTC ", time.gmtime()) + msg, flush=True)


def note_error(msg):
    with ULOCK, open(ERR, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S UTC ", time.gmtime()) + msg + "\n")


# ---------- bot 7 itself, checked and imported unchanged ----------
def check_bot7():
    r = subprocess.run(["bash", os.path.join(B7, "verify.sh")], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("STOP: bot 7's code does not match its fingerprints. Re-download the bot7 folder. Nothing was traded.")
    say(r.stdout.strip())


check_bot7()
sys.path.insert(0, os.path.join(B7, "lab"))
import finalmin as F          # bot 7: PRE, tick, Ncdf, p0, fee (unchanged)
PB, X = F.PB, F.X              # bot 7's own book reader and web helper


# ---------- config and keys ----------
def load_conf():
    c = dict(CONF_DEFAULT)
    p = os.path.join(D, "config.json")
    if os.path.exists(p):
        c.update(json.load(open(p)))
    if c["mode"] not in ("dry_run", "live"):
        sys.exit('config.json: "mode" must be "dry_run" or "live".')
    return c


def load_keys():
    kid, sec = os.environ.get("POLYMARKET_KEY_ID"), os.environ.get("POLYMARKET_SECRET_KEY")
    if not (kid and sec):
        p = os.path.expanduser("~/.bot7live/keys.json")
        if not os.path.exists(p):
            sys.exit("No API keys found. Put them in ~/.bot7live/keys.json (see GUIDE.md). Nothing was traded.")
        if os.name == "posix" and os.stat(p).st_mode & 0o077:
            sys.exit("~/.bot7live/keys.json can be read by other users. Run: chmod 600 ~/.bot7live/keys.json")
        k = json.load(open(p)); kid, sec = k.get("key_id"), k.get("secret_key")
    if not (kid and sec):
        sys.exit("keys.json needs both key_id and secret_key.")
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        sys.exit("Missing package. Run: python3 -m pip install --user cryptography")
    return kid, ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(sec)[:32])


# ---------- signed Polymarket US API calls (official docs: docs.polymarket.us/api-reference/authentication) ----------
class Api:
    def __init__(self, kid, key):
        self.kid, self.key = kid, key

    def call(self, method, path, body=None, t=6):
        ts = str(int(time.time() * 1000))
        sig = base64.b64encode(self.key.sign(f"{ts}{method}{path}".encode())).decode()
        h = {"X-PM-Access-Key": self.kid, "X-PM-Timestamp": ts, "X-PM-Signature": sig,
             "Content-Type": "application/json", "User-Agent": "bot7live/1.0"}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=t) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read() or b"{}")
            except Exception: return e.code, {}
        except Exception as e:
            return 0, {"error": type(e).__name__}


def px_str(p):
    return f"{round(p, 4):.4f}".rstrip("0").rstrip(".")


def order_body(slug, side, price, qty):
    """price = what we pay per share for our side. Polymarket prices every order on the YES side, so a Down
    (NO) buy at price p is sent as intent BUY_SHORT with YES price 1 - p."""
    yes_px = price if side == "UP" else round(1 - price, 4)
    return dict(marketSlug=slug, type="ORDER_TYPE_LIMIT", price={"value": px_str(yes_px), "currency": "USD"},
                quantity=qty, tif="TIME_IN_FORCE_IMMEDIATE_OR_CANCEL",
                intent="ORDER_INTENT_BUY_LONG" if side == "UP" else "ORDER_INTENT_BUY_SHORT",
                manualOrderIndicator="MANUAL_ORDER_INDICATOR_AUTOMATIC")


def size_for(price, avail, conf):
    """Shares to buy: bot 7's min(100, available), then the per-trade dollar and share caps."""
    q = min(100, avail, conf["max_shares_per_trade"], conf["max_usd_per_trade"] / price)
    return math.floor(q * 100) / 100


# ---------- daily limits ----------
class Limits:
    def __init__(self, conf):
        self.conf, self.last, self.blocked = conf, 0, None

    def today(self):
        day = time.strftime("%Y-%m-%d", time.gmtime())
        rows = []
        if os.path.exists(LOG):
            rows = [json.loads(l) for l in open(LOG) if l.strip()]
        return [r for r in rows if r.get("mode") == "live" and r.get("filled", 0) > 0 and r["time_utc"][:10] == day]

    def check(self):
        if os.path.exists(os.path.join(D, "STOP")):
            return "STOP file present"
        if time.time() - self.last < 20 and self.blocked is None:
            return None
        self.last = time.time(); rows = self.today()
        spent = sum(r["cost_usd"] + r.get("fee_usd", 0) for r in rows)
        sys.path.insert(0, os.path.join(B7, "xvenue")); import pmres as S
        pnl = 0.0
        for r in rows:
            res = S.pm_result(r["market_slug"])
            if res is None: continue
            won = (res == "yes") == (r["side"] == "UP")
            pnl += (r["filled"] if won else 0) - r["cost_usd"] - r.get("fee_usd", 0)
        S.save()
        if spent >= self.conf["daily_max_spend_usd"]:
            self.blocked = f"daily spend limit reached (${spent:.2f})"
        elif pnl <= -self.conf["daily_max_loss_usd"]:
            self.blocked = f"daily loss limit reached (${pnl:.2f})"
        else:
            self.blocked = None
        return self.blocked


# ---------- the action that replaces bot 7's paper write ----------
def act(api, conf, lim, out, signal):
    """Runs in a worker thread so bot 7's 1-second loop timing stays the same."""
    side, price, avail, slug = signal["side"], signal["price"], signal["size_available"], signal["slug"]
    rec = dict(signal, mode=conf["mode"], time_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(signal["t"])),
               market_slug=slug, filled=0.0, cost_usd=0.0, fee_usd=0.0)
    why = lim.check()
    if why: rec.update(status="skipped", reason=why)
    elif side == "DOWN" and conf["mode"] == "live" and not conf["down_price_confirmed"]: rec.update(status="skipped", reason="Down orders are off until down_price_confirmed is true")
    else:
        qty = size_for(price, avail, conf)
        if qty <= 0: rec.update(status="skipped", reason="size below minimum after limits")
        else:
            body = order_body(slug, side, price, qty); rec["order_request"] = body
            if conf["mode"] == "dry_run":
                code, resp = api.call("POST", "/v1/order/preview", body)
                rec.update(status="previewed" if code == 200 else "preview_failed", http=code, preview=resp)
            else:
                body = dict(body, synchronousExecution=True, maxBlockTime="2")
                code, resp = api.call("POST", "/v1/orders", body)
                rec.update(http=code, order_id=resp.get("id"))
                if code != 200 or not resp.get("id"):
                    rec.update(status="rejected", response=resp)
                else:
                    filled, cost = 0.0, 0.0
                    for ex in resp.get("executions") or []:
                        q = float(ex.get("lastShares") or 0); p = float((ex.get("lastPx") or {}).get("value") or 0)
                        if q > 0:
                            pay = p if side == "UP" else 1 - p      # fills are YES prices; convert to what we paid
                            filled += q; cost += q * pay
                    c2, o = api.call("GET", f"/v1/order/{resp['id']}")
                    o = (o or {}).get("order", o) if c2 == 200 else {}
                    if o.get("cumQuantity") is not None and float(o["cumQuantity"]) > filled and o.get("avgPx"):
                        filled = float(o["cumQuantity"]); ap = float(o["avgPx"]["value"])
                        cost = filled * (ap if side == "UP" else 1 - ap)
                    fee = float((o.get("commissionNotionalTotalCollected") or {}).get("value") or 0) if o else 0.0
                    rec.update(status="filled" if filled > 0 else "not_filled", filled=round(filled, 4),
                               cost_usd=round(cost, 4), fee_usd=round(fee, 4), order_state=o.get("state"))
    with ULOCK:
        out.write(json.dumps(rec) + "\n"); out.flush()
    say(f"{rec['status']}: {signal['asset'].upper()} {signal['h']} {side} at {price} " +
        (f"filled {rec['filled']} for ${rec['cost_usd']:.2f}" if rec.get("filled") else rec.get("reason", f"http {rec.get('http')}")))


def startup(api, conf):
    code, bal = api.call("GET", "/v1/account/balances")
    if code != 200:
        sys.exit(f"Could not sign in to Polymarket US (HTTP {code}). Check your keys and your computer's clock. Nothing was traded.")
    b = (bal.get("balances") or [{}])[0]
    say(f"Signed in. Buying power: {b.get('buyingPower')} {b.get('currency', '')}")
    say(f"Mode: {conf['mode'].upper()} | max ${conf['max_usd_per_trade']}/trade, {conf['max_shares_per_trade']} shares/trade, "
        f"${conf['daily_max_spend_usd']}/day spend, ${conf['daily_max_loss_usd']} daily loss limit | Down orders: "
        f"{'ON' if conf['down_price_confirmed'] else 'OFF'}")


def main():
    conf = load_conf(); kid, key = load_keys(); api = Api(kid, key); startup(api, conf)
    lim, pool = Limits(conf), cf.ThreadPoolExecutor(4)
    out = open(LOG, "a")
    # ----- below: bot 7's main() loop, unchanged except where marked -----
    PRE, tick, Ncdf, p0, fee = F.PRE, F.tick, F.Ncdf, F.p0, F.fee
    hist = {a: collections.deque(maxlen=400) for a in PRE}; basis = {a: 0.0 for a in PRE}; done = set(); fitted = set()
    with cf.ThreadPoolExecutor(8) as ex:
        while True:
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
                                # ----- CHANGED: bot 7 writes a paper trade here; bot 7 LIVE sends it to act() -----
                                pool.submit(act, api, conf, lim, out, dict(
                                    t=round(t0, 2), bot="7-live", asset=a, h=h, slug=slug, checkpoint=chk, side=side,
                                    price=price, size_available=size, fair=round(f_, 4), edge=round(f_ - price - fee(price), 4),
                                    start_price=P, est_final=round(mean, 6), sd=round(sd, 6), basis=round(basis[a], 6)))
            time.sleep(max(0, 1 - (time.time() - t0)))


if __name__ == "__main__":
    main()
