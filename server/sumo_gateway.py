#!/usr/bin/env python3
"""Sumo Frog gateway: the only public door to the PRIVATE Sumo test validator.

- POST /        JSON-RPC proxy to 127.0.0.1:8899, allowlisted read + sendTransaction methods only.
- requestAirdrop: max 1 test SOL per request, 1 per IP per 10 min, 5 per IP per day, 200 per day total.
- GET /         stats page (+ stats.js, sumo_config.js, sumo_frog.png, metadata.json) from ./www.
Worthless test network. No keys live here. Stdlib only.
"""
import json, os, sys, time, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("SUMO_UPSTREAM", "http://127.0.0.1:8899")
PORT = int(os.environ.get("SUMO_GATEWAY_PORT", "8080"))
WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")
MAX_BODY = 16 * 1024
ALLOWED = {
    "getAccountInfo", "getMultipleAccounts", "getBalance", "getLatestBlockhash", "isBlockhashValid",
    "sendTransaction", "simulateTransaction", "getSignatureStatuses", "getSignaturesForAddress",
    "getTransaction", "getTokenAccountBalance", "getTokenAccountsByOwner", "getTokenLargestAccounts",
    "getTokenSupply", "getSlot", "getBlockHeight", "getEpochInfo", "getGenesisHash", "getHealth",
    "getVersion", "getMinimumBalanceForRentExemption", "getFeeForMessage", "requestAirdrop",
}
AIRDROP_MAX_LAMPORTS = 1_000_000_000
AIRDROP_GAP = 600
AIRDROP_PER_IP_DAY = 5
AIRDROP_GLOBAL_DAY = 200
RATE, BURST = 10.0, 60.0          # requests per second per IP, bucket size
SEND_RATE, SEND_BURST = 2.0, 10.0  # sendTransaction per second per IP
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".png": "image/png", ".json": "application/json", ".jpg": "image/jpeg"}

lock = threading.Lock()
buckets, send_buckets = {}, {}
drops = {"day": None, "global": 0, "ip": {}}


def take(store, ip, rate, burst):
    now = time.monotonic()
    with lock:
        tokens, last = store.get(ip, (burst, now))
        tokens = min(burst, tokens + (now - last) * rate)
        if tokens < 1:
            store[ip] = (tokens, now)
            return False
        store[ip] = (tokens - 1, now)
        if len(store) > 50_000:
            store.clear()
        return True


def airdrop_ok(ip):
    today = time.strftime("%Y-%m-%d")
    now = time.time()
    with lock:
        if drops["day"] != today:
            drops.update({"day": today, "global": 0, "ip": {}})
        last, count = drops["ip"].get(ip, (0, 0))
        if drops["global"] >= AIRDROP_GLOBAL_DAY:
            return "faucet is empty for today, try tomorrow"
        if count >= AIRDROP_PER_IP_DAY:
            return f"limit is {AIRDROP_PER_IP_DAY} faucet requests per day"
        if now - last < AIRDROP_GAP:
            return f"wait {int(AIRDROP_GAP - (now - last))}s before asking the faucet again"
        drops["ip"][ip] = (now, count + 1)
        drops["global"] += 1
        return None


def check(req, ip):
    """Return an error string, or None if the request may go upstream (may rewrite params)."""
    if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
        return "invalid request"
    m = req["method"]
    p = req.get("params", [])
    if not isinstance(p, list):
        return "params must be a list"
    if m not in ALLOWED:
        return f"method {m} is not available on the Sumo gateway"
    if m == "getMultipleAccounts" and (not p or not isinstance(p[0], list) or len(p[0]) > 20):
        return "max 20 accounts"
    if m == "getSignatureStatuses" and (not p or not isinstance(p[0], list) or len(p[0]) > 50):
        return "max 50 signatures"
    if m == "getSignaturesForAddress":
        opts = p[1] if len(p) > 1 and isinstance(p[1], dict) else {}
        opts["limit"] = min(int(opts.get("limit", 25) or 25), 25)
        req["params"] = [p[0] if p else None, opts]
    if m == "sendTransaction" and not take(send_buckets, ip, SEND_RATE, SEND_BURST):
        return "too many transactions, slow down"
    if m == "requestAirdrop":
        if len(p) < 2 or not isinstance(p[1], int) or not 0 < p[1] <= AIRDROP_MAX_LAMPORTS:
            return "faucet gives at most 1 test SOL per request"
        why = airdrop_ok(ip)
        if why:
            return why
        print(f"airdrop {p[1]/1e9:g} SOL to {p[0]} for {ip}", flush=True)
    return None


class H(BaseHTTPRequestHandler):
    timeout = 15
    server_version = "sumo-gateway"
    sys_version = ""

    def log_message(self, *a):
        pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, solana-client")

    def reply(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def rpc_err(self, rid, msg, code=-32601):
        self.reply(200, json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}).encode())

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.end_headers()

    def do_GET(self):
        ip = self.client_address[0]
        if not take(buckets, ip, RATE, BURST):
            return self.reply(429, b"slow down", "text/plain")
        path = self.path.split("?")[0]
        if path in ("/", ""):
            path = "/index.html"
        name = os.path.basename(path)
        f = os.path.join(WWW, name)
        if path != "/" + name or not os.path.isfile(f):
            return self.reply(404, b"not found", "text/plain")
        with open(f, "rb") as fh:
            self.reply(200, fh.read(), TYPES.get(os.path.splitext(name)[1], "application/octet-stream"))

    def do_POST(self):
        ip = self.client_address[0]
        if not take(buckets, ip, RATE, BURST):
            return self.reply(429, b'{"error":"slow down"}')
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if not 0 < n <= MAX_BODY:
            return self.reply(413, b'{"error":"body too large"}')
        try:
            req = json.loads(self.rfile.read(n))
        except Exception:
            return self.rpc_err(None, "parse error", -32700)
        if isinstance(req, list):
            return self.rpc_err(None, "batch requests are not supported", -32600)
        why = check(req, ip)
        if why:
            return self.rpc_err(req.get("id") if isinstance(req, dict) else None, why)
        body = json.dumps({"jsonrpc": "2.0", "id": req.get("id", 1), "method": req["method"],
                           "params": req.get("params", [])}).encode()
        try:
            up = urllib.request.Request(UPSTREAM, body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(up, timeout=20) as r:
                out = r.read()
        except Exception:
            return self.rpc_err(req.get("id"), "test network is unavailable right now", -32000)
        self.reply(200, out)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    srv.daemon_threads = True
    print(f"sumo gateway on :{PORT} -> {UPSTREAM}", flush=True)
    srv.serve_forever()
