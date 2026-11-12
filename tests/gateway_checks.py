#!/usr/bin/env python3
"""Offline path checks for the Sumo gateway's GET handler.
No network and no live validator: a temp www/ plus a short-lived loopback server.
Run: python3 tests/gateway_checks.py
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import sumo_gateway as g  # noqa: E402

passed = 0


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


def main():
    tmp = tempfile.mkdtemp()
    www = os.path.join(tmp, "www")
    os.makedirs(os.path.join(www, "stats"))
    open(os.path.join(www, "index.html"), "w").write("HOME")
    open(os.path.join(www, "stats", "index.html"), "w").write("STATS")
    secret = os.path.join(www, ".secret")
    open(secret, "w").write("HIDDEN")
    outside = os.path.join(tmp, "outside.txt")
    open(outside, "w").write("OUTSIDE")
    link = os.path.join(www, "escape")
    os.symlink(outside, link)
    # A non-hidden name inside www/ that resolves to a hidden file still in www/.
    hidden_link = os.path.join(www, "shortcut")
    os.symlink(secret, hidden_link)
    hidden_dir = os.path.join(www, ".hidden")
    os.makedirs(hidden_dir)
    open(os.path.join(hidden_dir, "file.html"), "w").write("HIDDENDIR")
    dir_link = os.path.join(www, "sneaky")
    os.symlink(os.path.join(hidden_dir, "file.html"), dir_link)

    ok("home is served", os.path.basename(g.safe_www_file(www, "/")) == "index.html")
    ok("stats is served", g.safe_www_file(www, "/stats/").endswith(os.path.join("stats", "index.html")))
    ok("dotfile refused", g.safe_www_file(www, "/.secret") is None)
    ok("nested dot segment refused", g.safe_www_file(www, "/stats/.secret") is None)
    ok("dot-slash refused", g.safe_www_file(www, "/./index.html") is None)
    ok("parent path refused", g.safe_www_file(www, "/../outside.txt") is None)
    ok("encoded parent path refused", g.safe_www_file(www, "/%2e%2e/outside.txt") is None)
    ok("symlink out of www refused", g.safe_www_file(www, "/escape") is None)
    ok("symlink inside www to a hidden file refused", g.safe_www_file(www, "/shortcut") is None)
    ok("symlink inside www to a hidden-dir file refused", g.safe_www_file(www, "/sneaky") is None)
    ok("missing file refused", g.safe_www_file(www, "/no-such-file") is None)

    g.WWW = www
    # bind loopback only; a throwaway port
    srv = ThreadingHTTPServer(("127.0.0.1", 0), g.H)
    srv.daemon_threads = True
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    code, body = get("/")
    ok("http home 200", code == 200 and body == b"HOME")
    code, body = get("/stats/")
    ok("http stats 200", code == 200 and body == b"STATS")
    code, body = get("/.secret")
    ok("http dotfile 404, not the hidden bytes", code == 404 and body == b"not found")
    code, body = get("/escape")
    ok("http symlink 404, not the outside bytes", code == 404 and body == b"not found")
    code, body = get("/shortcut")
    ok("http hidden-file symlink 404, not the hidden bytes", code == 404 and body == b"not found")
    code, body = get("/sneaky")
    ok("http hidden-dir symlink 404, not the hidden bytes", code == 404 and body == b"not found")

    # JSON-RPC path still answers (upstream will fail; we only check the method is accepted
    # and a well-formed error comes back, not a GET-style 404).
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getHealth", "params": []}).encode()
    req = urllib.request.Request(base + "/", payload, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            post_status, post_body = r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        post_status, post_body = e.code, json.loads(e.read())
    ok("POST getHealth is still accepted as JSON-RPC",
       post_status == 200 and post_body.get("jsonrpc") == "2.0"
       and ("result" in post_body or "error" in post_body))

    srv.shutdown()
    print(f"gateway checks: {passed} passed")


if __name__ == "__main__":
    main()
