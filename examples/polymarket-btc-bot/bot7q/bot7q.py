"""Bot 7Q: MAKER bot for Polymarket US crypto Up/Down markets. Posts its own buy prices early and waits for others
to sell to it. Uses REAL orders in "live" mode, so start in "dry_run" (default) and keep the tiny limits.

How it works (every second):
  * Bot 7's odds math (from ../bot7/lab/finalmin.py, unchanged) estimates the chance of Up from the live Coinbase
    price, for every BTC/ETH/SOL/XRP market (5m, and 15m/1h when they end at the same time).
  * From QUOTE_START seconds left until QUOTE_END seconds left, it keeps two POST-ONLY limit orders per market:
        buy Up   at  floor(fair - margin)          (YES price)
        buy Down at  1 - ceil(fair + margin)        (sent as BUY_SHORT at YES price ceil(fair + margin))
    Post-only (participateDontInitiate) means Polymarket rejects the order rather than let it take someone else's
    price, so the bot is always the maker (maker rebate, no taker fee).
  * When its fair price moves by REQUOTE or more, it cancels and re-posts. Orders also carry a good-till time that
    ends EXPIRE_BEFORE_END seconds before the market closes, and the bot itself cancels everything in a market at
    QUOTE_END seconds left (two layers of protection).
  * Once any order in a market fills, it stops quoting that market (one position per market).
  * Skips markets that are nearly decided (fair outside fair_min..fair_max).
Safety: dry_run by default; tiny per-order size; daily spend and loss limits; STOP file; cancels all its open orders
at start and at exit; keys only from ~/.bot7live/keys.json or the environment, never printed.
Usage: python3 -I bot7q.py
"""
import json, math, os, sys, time, signal, collections, concurrent.futures as cf

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(D, "..", "bot7live")))
import bot7live as L                       # checks bot 7's fingerprints; signed API client; keys loader
F, PB = L.F, L.PB                          # bot 7 itself (unchanged) and its book reader
CONF_DEFAULT = dict(mode="dry_run", usd_per_order=2.0, margin=0.06, requote=0.02, min_requote_s=3, quote_start_s=90, quote_end_s=8,
                    expire_before_end_s=5, fair_min=0.08, fair_max=0.92, max_open_orders=16, max_new_orders_per_s=4,
                    daily_max_spend_usd=50.0, daily_max_loss_usd=10.0)
FILLS = os.path.join(D, "maker_fills.jsonl"); EVENTS = os.path.join(D, "maker_events.jsonl")


def say(m): print(time.strftime("%Y-%m-%d %H:%M:%S UTC ", time.gmtime()) + m, flush=True)


def load_conf():
    c = dict(CONF_DEFAULT); p = os.path.join(D, "config.json")
    if os.path.exists(p): c.update(json.load(open(p)))
    if c["mode"] not in ("dry_run", "live"): sys.exit('config.json: "mode" must be "dry_run" or "live".')
    return c


def fair_up(hist_a, E, t0, basis_a, P):
    """Bot 7's model for r <= 60 s; for r > 60 s the 60-s settlement average lies wholly in the future."""
    r = E - t0
    w = [p for t, p in hist_a if E - 60 <= t <= t0]; full = [p for t, p in hist_a if t >= t0 - 75]
    if len(full) < 40: return None
    S = full[-1]; diffs = [y - x for x, y in zip(full, full[1:])]
    sig = max((sum(d * d for d in diffs) / len(diffs)) ** 0.5, 1e-9)
    if r <= 60:
        mean = (sum(w) + S * r) / (len(w) + r) + basis_a; sd = (r / 60) * sig * math.sqrt(r / 3)
    else:
        mean = S + basis_a; sd = sig * math.sqrt((r - 60) + 20)
    return F.Ncdf((mean - P) / max(sd, 1e-12))


def quotes(fair, conf):
    """Returns {"UP": (yes_price, pay_per_share), "DOWN": (yes_price, pay_per_share)} for prices inside 1c..99c."""
    q = {}
    up = math.floor((fair - conf["margin"]) * 100 + 1e-9) / 100
    if 0.01 <= up <= 0.99: q["UP"] = (round(up, 2), round(up, 2))
    dn_yes = math.ceil((fair + conf["margin"]) * 100 - 1e-9) / 100
    if 0.01 <= dn_yes <= 0.99: q["DOWN"] = (round(dn_yes, 2), round(1 - dn_yes, 2))
    return q


def order_body(slug, side, yes_px, qty, expire_ts):
    return dict(marketSlug=slug, type="ORDER_TYPE_LIMIT", price={"value": L.px_str(yes_px), "currency": "USD"},
                quantity=qty, tif="TIME_IN_FORCE_GOOD_TILL_DATE",
                goodTillTime=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expire_ts)),
                participateDontInitiate=True,
                intent="ORDER_INTENT_BUY_LONG" if side == "UP" else "ORDER_INTENT_BUY_SHORT",
                manualOrderIndicator="MANUAL_ORDER_INDICATOR_AUTOMATIC")


class Maker:
    def __init__(self, api, conf):
        self.api, self.conf = api, conf
        self.live = conf["mode"] == "live"
        self.orders = {}          # (slug, side) -> dict(id, yes_px, pay, qty, fair)
        self.filled_mkts = set()
        self.ev = open(EVENTS, "a"); self.fl = open(FILLS, "a")
        self.pool = cf.ThreadPoolExecutor(6)

    def log(self, **k):
        k["t"] = round(time.time(), 2); self.ev.write(json.dumps(k) + "\n"); self.ev.flush()

    # ---- limits ----
    def today_fills(self):
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if not os.path.exists(FILLS): return []
        return [r for r in (json.loads(l) for l in open(FILLS) if l.strip()) if r["time_utc"][:10] == day and r.get("mode") == "live"]

    def blocked(self):
        if os.path.exists(os.path.join(D, "STOP")): return "STOP file present"
        if time.time() - getattr(self, "_lim_t", 0) < 20: return getattr(self, "_lim_v", None)
        self._lim_t = time.time(); self._lim_v = self._limits(); return self._lim_v

    def _limits(self):
        rows = self.today_fills(); spent = sum(r["cost_usd"] for r in rows)
        sys.path.insert(0, os.path.join(L.B7, "xvenue")); import pmres as S
        pnl = 0.0
        for r in rows:
            res = S.pm_result(r["slug"])
            if res is not None: pnl += (r["filled"] if (res == "yes") == (r["side"] == "UP") else 0) - r["cost_usd"]
        S.save()
        if spent >= self.conf["daily_max_spend_usd"]: return f"daily spend limit reached (${spent:.2f})"
        if pnl <= -self.conf["daily_max_loss_usd"]: return f"daily loss limit reached (${pnl:.2f})"
        return None

    # ---- order actions ----
    def place(self, slug, side, yes_px, pay, qty, expire_ts, fair):
        body = order_body(slug, side, yes_px, qty, expire_ts)
        if not self.live:
            self.orders[(slug, side)] = dict(id="dry", yes_px=yes_px, pay=pay, qty=qty, fair=fair, at=self.now)
            self.log(kind="quote_dry", slug=slug, side=side, pay=pay, qty=qty, fair=round(fair, 4)); return
        code, resp = self.api.call("POST", "/v1/orders", body)
        if code == 200 and resp.get("id"):
            self.orders[(slug, side)] = dict(id=resp["id"], yes_px=yes_px, pay=pay, qty=qty, fair=fair, at=self.now)
            self.log(kind="posted", slug=slug, side=side, pay=pay, qty=qty, fair=round(fair, 4), order_id=resp["id"])
        else:
            self.log(kind="post_rejected", slug=slug, side=side, pay=pay, http=code, response=resp)

    def cancel(self, slug, side, why):
        o = self.orders.pop((slug, side), None)
        if not o: return
        if self.live and o["id"] != "dry":
            code, resp = self.api.call("POST", f"/v1/order/{o['id']}/cancel", {"marketSlug": slug})
            self.log(kind="canceled", slug=slug, side=side, why=why, http=code, order_id=o["id"])
            self.check_final(slug, side, o)                 # it may have (partly) filled just before the cancel
        else:
            self.log(kind="cancel_dry", slug=slug, side=side, why=why)

    def cancel_all(self, why):
        for k in list(self.orders): self.cancel(k[0], k[1], why)
        if self.live:
            code, _ = self.api.call("POST", "/v1/orders/open/cancel", {})
            self.log(kind="cancel_all", why=why, http=code)

    def record_fill(self, slug, side, o, filled, avg_yes):
        if filled <= 0: return
        pay = (avg_yes if side == "UP" else 1 - avg_yes) if avg_yes else o["pay"]
        rec = dict(time_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), mode="live", slug=slug, side=side,
                   filled=round(filled, 4), pay=round(pay, 4), cost_usd=round(filled * pay, 4), fair_at_post=round(o["fair"], 4), order_id=o["id"])
        self.fl.write(json.dumps(rec) + "\n"); self.fl.flush(); self.filled_mkts.add(slug)
        say(f"FILLED: {slug} {side} {filled} at {pay:.2f} (bot's fair {o['fair'] if side == 'UP' else 1 - o['fair']:.2f})")

    def check_final(self, slug, side, o):
        c, r = self.api.call("GET", f"/v1/order/{o['id']}")
        if c != 200: return
        od = (r or {}).get("order") or {}; q = float(od.get("cumQuantity") or 0)
        if q > 0 and not o.get("recorded"):
            o["recorded"] = True; ap = float((od.get("avgPx") or {}).get("value") or 0) or None
            self.record_fill(slug, side, o, q, ap)

    def sync_fills(self):
        """One request per second: open orders. Orders that left the book or show fills are checked."""
        if not self.live or not self.orders: return
        c, r = self.api.call("GET", "/v1/orders/open")
        if c != 200: return
        openo = {o.get("id"): o for o in (r or {}).get("orders", [])}
        for (slug, side), o in list(self.orders.items()):
            od = openo.get(o["id"])
            if od is None or float(od.get("cumQuantity") or 0) > 0:
                self.orders.pop((slug, side), None); self.check_final(slug, side, o)
                if slug in self.filled_mkts:
                    other = "DOWN" if side == "UP" else "UP"
                    self.cancel(slug, other, "market already filled")

    # ---- main step ----
    def step(self, now, mkts):
        """mkts: list of (slug, E, fair or None)."""
        self.now = now
        why = self.blocked()
        if why:
            if self.orders: self.cancel_all(why); say(f"paused: {why}")
            return
        self.sync_fills()
        c = self.conf; budget = c["max_new_orders_per_s"]     # each new order is up to 3 requests; Polymarket allows 25/s
        for slug, E, fair in mkts:
            r = E - now
            in_window = c["quote_end_s"] <= r <= c["quote_start_s"]
            ok = in_window and fair is not None and c["fair_min"] <= fair <= c["fair_max"] and slug not in self.filled_mkts
            want = quotes(fair, c) if ok else {}
            for side in ("UP", "DOWN"):
                have = self.orders.get((slug, side))
                if side not in want:
                    if have: self.cancel(slug, side, "outside window or fair range")
                    continue
                yes_px, pay = want[side]
                if have and abs(have["fair"] - fair) < c["requote"]: continue
                if have and now - have.get("at", 0) < c["min_requote_s"] and abs(have["fair"] - fair) < 2 * c["requote"]: continue
                if have: self.cancel(slug, side, "requote")
                if len(self.orders) >= c["max_open_orders"] or budget <= 0: continue
                budget -= 1
                qty = math.floor(c["usd_per_order"] / pay * 100) / 100
                if qty <= 0: continue
                self.place(slug, side, yes_px, pay, qty, E - c["expire_before_end_s"], fair)


def main():
    conf = load_conf(); kid, key = L.load_keys(); api = L.Api(kid, key); L.startup(api, dict(conf, max_usd_per_trade=conf["usd_per_order"],
        max_shares_per_trade="-", daily_max_spend_usd=conf["daily_max_spend_usd"], daily_max_loss_usd=conf["daily_max_loss_usd"], down_price_confirmed=True))
    say(f"Bot 7Q maker | mode {conf['mode'].upper()} | ${conf['usd_per_order']}/order, margin {conf['margin']*100:.0f}c, "
        f"quotes from {conf['quote_start_s']}s to {conf['quote_end_s']}s left")
    m = Maker(api, conf)
    if m.live: m.cancel_all("startup")
    def bye(*_):
        say("stopping: cancelling all open orders"); m.cancel_all("exit"); sys.exit(0)
    signal.signal(signal.SIGINT, bye); signal.signal(signal.SIGTERM, bye)
    PRE, tick, p0 = F.PRE, F.tick, F.p0
    hist = {a: collections.deque(maxlen=400) for a in PRE}; basis = {a: 0.0 for a in PRE}; fitted = set(); p0c = {}
    with cf.ThreadPoolExecutor(8) as ex:
        while True:
            t0 = time.time()
            def safe(a):
                try: return tick(a)
                except Exception: return None
            for a, p in zip(PRE, ex.map(safe, PRE)):
                if p is not None: hist[a].append((t0, p))
            Eprev = int(t0) // 300 * 300                  # bot 7's offset learning, unchanged
            if t0 - Eprev > 20:
                for a in PRE:
                    if (a, Eprev) in fitted: continue
                    fitted.add((a, Eprev)); P = p0(f"{PRE[a]}-updown-5m-{time.strftime('%Y-%m-%d-%H%Mz', time.gmtime(Eprev))}")
                    w = [p for t, p in hist[a] if Eprev - 60 <= t < Eprev]
                    if P and len(w) >= 40: basis[a] = 0.7 * basis[a] + 0.3 * (P - sum(w) / len(w))
            E = (int(t0) // 300 + 1) * 300; mk = []
            for a in PRE:
                for h, Ln in (("5m", 300), ("15m", 900), ("1h", 3600)):
                    if E % Ln: continue
                    slug = f"{PRE[a]}-updown-{h}-{time.strftime('%Y-%m-%d-%H%Mz', time.gmtime(E - Ln))}"
                    if slug not in p0c and E - t0 <= conf["quote_start_s"] + 5: p0c[slug] = p0(slug)
                    P = p0c.get(slug)
                    mk.append((slug, E, fair_up(hist[a], E, t0, basis[a], P) if P else None))
            try: m.step(t0, mk)
            except Exception as e: L.note_error(f"7Q step: {type(e).__name__}: {e}")
            time.sleep(max(0, 1 - (time.time() - t0)))


if __name__ == "__main__":
    main()
