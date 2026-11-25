"""Offline tests for bot 7Q against a fake Polymarket server (no real orders, no real keys). Usage: python3 -I test_bot7q.py"""
import json, os, sys, tempfile, threading, time, http.server, base64
sys.dont_write_bytecode = True
from cryptography.hazmat.primitives.asymmetric import ed25519
D = os.path.dirname(os.path.abspath(__file__))
SEEN, OPEN, FILLQ = [], {}, {}
class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        SEEN.append(("GET", self.path, None))
        if self.path == "/v1/orders/open": return self._send(200, {"orders": [dict(id=k, cumQuantity=0) for k in OPEN]})
        if self.path.startswith("/v1/order/"):
            oid = self.path.split("/")[3]; return self._send(200, {"order": {"cumQuantity": FILLQ.get(oid, 0), "avgPx": {"value": "0.70"}, "state": "ORDER_STATE_FILLED" if oid in FILLQ else "ORDER_STATE_CANCELED"}})
        self._send(404, {})
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append(("POST", self.path, body))
        if self.path == "/v1/orders":
            oid = f"o{len(SEEN)}"; OPEN[oid] = body; return self._send(200, {"id": oid})
        if self.path.endswith("/cancel"):
            if self.path == "/v1/orders/open/cancel": OPEN.clear()
            else: OPEN.pop(self.path.split("/")[3], None)
            return self._send(200, {})
        self._send(404, {})
srv = http.server.HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["BOT7LIVE_API"] = f"http://127.0.0.1:{srv.server_port}"
sys.path.insert(0, D); import bot7q as Q
tmp = tempfile.mkdtemp(); Q.FILLS = os.path.join(tmp, "f.jsonl"); Q.EVENTS = os.path.join(tmp, "e.jsonl")
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or c
res = []; conf = dict(Q.CONF_DEFAULT)
q = Q.quotes(0.80, conf)
res.append(ok(q["UP"] == (0.74, 0.74) and q["DOWN"] == (0.86, 0.14), "fair 80%: buy Up at 74c, buy Down at 14c (YES 0.86), 6c margin each side"))
b = Q.order_body("s", "DOWN", 0.86, 14.28, 1795600000)
res.append(ok(b["participateDontInitiate"] is True and b["tif"] == "TIME_IN_FORCE_GOOD_TILL_DATE" and b["goodTillTime"].endswith("Z") and b["intent"] == "ORDER_INTENT_BUY_SHORT", "orders are post-only, good-till-date, Down = BUY_SHORT"))
api = Q.L.Api("k", ed25519.Ed25519PrivateKey.generate())
now = time.time(); E = now + 60
m = Q.Maker(api, dict(conf, mode="dry_run")); m.step(now, [("mkt-a", E, 0.80)])
res.append(ok(not [s for s in SEEN if s[1] == "/v1/orders"] and len(m.orders) == 2, "dry run: 2 quotes, no order sent"))
m = Q.Maker(api, dict(conf, mode="live")); m.step(now, [("mkt-a", E, 0.80)])
posts = [s for s in SEEN if s[1] == "/v1/orders"]
res.append(ok(len(posts) == 2 and abs(posts[0][2]["quantity"] * 0.74 - 2) < 0.02, "live: posts Up and Down, about $2 each"))
m.step(now + 1, [("mkt-a", E, 0.81)])
res.append(ok(len([s for s in SEEN if s[1] == "/v1/orders"]) == 2, "small fair move (<2c): no requote"))
m.step(now + 2, [("mkt-a", E, 0.85)])
res.append(ok(len([s for s in SEEN if s[1] == "/v1/orders"]) == 4 and any(s[1].endswith("/cancel") for s in SEEN), "fair jumps 5c within 3 s: cancels and re-posts both"))
up_id = m.orders[("mkt-a", "UP")]["id"]; OPEN.pop(up_id); FILLQ[up_id] = 2.5
m.step(now + 3, [("mkt-a", E, 0.85)])
fl = [json.loads(l) for l in open(Q.FILLS)]
res.append(ok(len(fl) == 1 and fl[0]["side"] == "UP" and fl[0]["filled"] == 2.5 and ("mkt-a", "DOWN") not in m.orders, "fill detected, recorded, other side cancelled, market not quoted again"))
m.step(now + 4, [("mkt-b", E, 0.95)])
res.append(ok(("mkt-b", "UP") not in m.orders, "nearly decided market (95%) is skipped"))
m.step(now + 5, [("mkt-c", now + 5 + 6, 0.5)])
res.append(ok(("mkt-c", "UP") not in m.orders, "no quotes in the last 8 seconds"))
m.step(now + 6, [("mkt-d", E, 0.5)]); open(os.path.join(D, "STOP"), "w").close()
try:
    m._lim_t = 0; m.step(now + 7, [("mkt-d", E, 0.5)])
    res.append(ok(not m.orders and not OPEN, "STOP file: all open orders cancelled"))
finally: os.remove(os.path.join(D, "STOP"))
print("ALL PASSED" if all(res) else "SOME FAILED"); srv.shutdown(); sys.exit(0 if all(res) else 1)
