"""Offline tests for bot 7 LIVE. Uses a fake Polymarket server on this computer; no real orders, no real keys.
Usage: python3 -I test_bot7live.py"""
import base64, json, os, sys, tempfile, threading, time, http.server
from cryptography.hazmat.primitives.asymmetric import ed25519
D = os.path.dirname(os.path.abspath(__file__))
SEEN = []
class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _auth_ok(self):
        ts, sig = self.headers["X-PM-Timestamp"], base64.b64decode(self.headers["X-PM-Signature"])
        try: PUB.verify(sig, f"{ts}{self.command}{self.path}".encode()); return True
        except Exception: return False
    def do_GET(self):
        SEEN.append((self.command, self.path, None, self._auth_ok()))
        if self.path == "/v1/account/balances": return self._send(200, {"balances": [{"buyingPower": 500, "currency": "USD"}]})
        if self.path.startswith("/v1/order/"): return self._send(200, {"order": {"cumQuantity": 5, "avgPx": {"value": "0.86"}, "state": "ORDER_STATE_FILLED", "commissionNotionalTotalCollected": {"value": "0.04"}}})
        self._send(404, {})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.command, self.path, body, self._auth_ok()))
        if self.path == "/v1/order/preview": return self._send(200, {"order": {"price": body["price"]}})
        if self.path == "/v1/orders": return self._send(200, {"id": "ord-1", "executions": [{"lastShares": "5", "lastPx": {"value": "0.86"}}]})
        self._send(404, {})
key = ed25519.Ed25519PrivateKey.generate(); PUB = key.public_key()
srv = http.server.HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["BOT7LIVE_API"] = f"http://127.0.0.1:{srv.server_port}"
sys.path.insert(0, D); import bot7live as L
L.LOG = os.path.join(tempfile.mkdtemp(), "t.jsonl")
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or c
res = []
api = L.Api("test-key", key)
res.append(ok(api.call("GET", "/v1/account/balances")[0] == 200 and SEEN[-1][3], "signed request accepted by signature check"))
b = L.order_body("s", "UP", 0.86, 5)
res.append(ok(b["intent"] == "ORDER_INTENT_BUY_LONG" and b["price"]["value"] == "0.86" and b["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL", "Up = buy YES at the ask, IOC"))
b = L.order_body("s", "DOWN", 0.14, 5)
res.append(ok(b["intent"] == "ORDER_INTENT_BUY_SHORT" and b["price"]["value"] == "0.86", "Down at 14c = buy NO, sent as YES price 0.86"))
c = dict(L.CONF_DEFAULT)
res.append(ok(L.size_for(0.86, 300, c) == 5.81 and L.size_for(0.05, 300, c) == 100 and L.size_for(0.5, 3, c) == 3, "size: $5 cap, 100-share cap, never more than available"))
out = open(L.LOG, "a"); sig = dict(t=time.time(), asset="btc", h="5m", slug="cpc-btc-updown-5m-x", checkpoint=45, side="UP", price=0.86, size_available=300)
L.act(api, dict(c, mode="dry_run"), L.Limits(c), out, sig)
res.append(ok(SEEN[-1][1] == "/v1/order/preview", "dry run calls PREVIEW only"))
n = len([s for s in SEEN if s[1] == "/v1/orders"])
res.append(ok(n == 0, "dry run placed no order"))
L.act(api, dict(c, mode="dry_run"), L.Limits(c), out, dict(sig, side="DOWN", price=0.14))
r = json.loads(open(L.LOG).read().splitlines()[-1]); res.append(ok(r["status"] == "previewed" and SEEN[-1][2]["intent"] == "ORDER_INTENT_BUY_SHORT", "dry run previews Down too (no order)"))
L.act(api, dict(c, mode="live"), L.Limits(c), out, dict(sig, side="DOWN", price=0.14))
r = json.loads(open(L.LOG).read().splitlines()[-1]); res.append(ok(r["status"] == "skipped", "live: Down is off until confirmed"))
L.act(api, dict(c, mode="live"), L.Limits(c), out, sig)
r = json.loads(open(L.LOG).read().splitlines()[-1])
res.append(ok(r["status"] == "filled" and r["filled"] == 5 and abs(r["cost_usd"] - 4.3) < 1e-9 and r["fee_usd"] == 0.04, "live order: fill, cost and fee recorded"))
open(os.path.join(D, "STOP"), "w").close()
try:
    L.act(api, dict(c, mode="live"), L.Limits(c), out, sig)
    r = json.loads(open(L.LOG).read().splitlines()[-1]); res.append(ok(r["status"] == "skipped" and "STOP" in r["reason"], "STOP file blocks new orders"))
finally: os.remove(os.path.join(D, "STOP"))
lim = L.Limits(dict(c, daily_max_spend_usd=4.0)); lim.last = 0
res.append(ok(lim.check() and "spend" in lim.blocked, "daily spend limit blocks new orders"))
print("ALL PASSED" if all(res) else "SOME FAILED"); srv.shutdown(); sys.exit(0 if all(res) else 1)
