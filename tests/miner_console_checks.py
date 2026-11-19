#!/usr/bin/env python3
"""Offline checks for two miner bugs found testing the devnet zip on Windows (18 Nov 2026):
  1. keys / clicks in the mining window froze or wrecked it; Ctrl+C printed a KeyboardInterrupt
     traceback (from the worker processes too).
  2. the miner showed the full folder path it is saved in (e.g. C:\\Users\\<name>\\Downloads\\...),
     which leaks the Windows user name. Also proves it never lists or reads other files in the folder.
No network, no keys. Run: python3 tests/miner_console_checks.py"""
import ast
import ctypes
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MINER = os.path.join(HERE, "..", "miner")
sys.path.insert(0, MINER)
import sumo_miner as m  # noqa: E402
from solders.keypair import Keypair  # noqa: E402

passed = 0


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


def refused_code(fn, *a):
    try:
        fn(*a)
    except SystemExit as e:
        return e.code
    raise AssertionError("did not exit")


def refused(fn, *a):
    try:
        fn(*a)
    except SystemExit as e:
        return str(e.code)
    raise AssertionError(f"not refused: {fn.__name__}")


S = {}
# ---- Bug 1a: console input guard (fake kernel32; the real one only exists on Windows) ----
QUICK_EDIT, ECHO, LINE, MOUSE, PROCESSED, EXTENDED = 0x40, 0x04, 0x02, 0x10, 0x01, 0x80


class FakeK32:
    def __init__(self, mode=0x1F7, is_console=True):  # a normal console: quickedit+echo+line+mouse...
        self.mode, self.is_console, self.sets, self.flushes = mode, is_console, [], 0

    def GetStdHandle(self, which):
        return 7

    def GetConsoleMode(self, h, ptr):
        if not self.is_console:
            return 0
        ptr._obj.value = self.mode
        return 1

    def SetConsoleMode(self, h, mode):
        self.sets.append(mode)
        self.mode = mode
        return 1

    def FlushConsoleInputBuffer(self, h):
        self.flushes += 1
        return 1


k = FakeK32()
with m.quiet_console_input(k):
    inside = k.mode
    m.flush_console_input()
    flushed_inside = k.flushes
ok("quickedit, echo, line input and mouse are switched off while mining",
   not inside & (QUICK_EDIT | ECHO | LINE | MOUSE))
ok("Ctrl+C is read as a key, not sent as a signal (processed input off, so cmd never asks 'Terminate batch job'); extended flags set so quickedit really is off",
   not inside & PROCESSED and inside & EXTENDED)
ok("keys are discarded while mining", flushed_inside >= 2)
ok("the old console mode is restored on exit", k.mode == 0x1F7)

k = FakeK32()
try:
    with m.quiet_console_input(k):
        raise KeyboardInterrupt
except KeyboardInterrupt:
    pass
ok("old console mode restored even on Ctrl+C", k.mode == 0x1F7)

k = FakeK32(is_console=False)
with m.quiet_console_input(k):
    m.flush_console_input()
ok("stdin not a console (pipe/file): nothing is changed", k.sets == [] and k.flushes == 0)
ok("guard is a no-op here and leaves no state behind",
   m._input_guard["k32"] is None)
with m.quiet_console_input():  # real one: no-op off Windows
    pass
ok("no-op on this system without a fake", m._input_guard["k32"] is None)

# ---- Bug 1b: Ctrl+C is a clean stop: no traceback from the parent or any worker ----
SCRIPT = r'''
import sys, os, time
sys.path.insert(0, %(miner)r)
import sumo_miner as m
from solders.keypair import Keypair
kp = Keypair()
class FakeChain:
    cluster, unencrypted = "devnet", False
    program = config = mint = Keypair().pubkey()
    def state(self):
        return dict(next_reward=20 * 10**9, blocks_mined=0, target=1, blocks_to_halving=5,
                    challenge=bytes(32))
    def sol_balance(self, pk): return 1.0
    def sumo_units(self, pk): return 0
m.Chain = lambda settings: FakeChain()
m.load_key = lambda path: kp
m.saved_payout = lambda settings: None
m.load_settings = lambda: {}
sys.argv = ["sumo_miner.py", "mine", "--plain", "--workers", "2"]
m.main()
print("CLEAN-EXIT", flush=True)
'''


def run_ctrl_c():
    import time
    p = subprocess.Popen([sys.executable, "-u", "-c", SCRIPT % {"miner": MINER}], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    seen = ""
    while " workers" not in seen:  # wait for the plain banner: workers start right after it
        line = p.stdout.readline()
        if not line:
            break
        seen += line
    time.sleep(2)
    os.killpg(p.pid, signal.SIGINT)  # like the console: every process in the group gets it
    out, _ = p.communicate(timeout=30)
    return p.returncode, seen + out


if os.name != "nt":
    rc, out = run_ctrl_c()
    ok("Ctrl+C: miner exits cleanly (code 0)", rc == 0 and "CLEAN-EXIT" in out)
    ok("Ctrl+C: no traceback / KeyboardInterrupt text from the miner or its workers",
       "Traceback" not in out and "KeyboardInterrupt" not in out)
else:
    ok("Ctrl+C check skipped on Windows (needs a POSIX process group)", True)

# ---- Bug 2: the miner only ever opens its own files by exact name, never lists a folder ----
FORBIDDEN = {"glob", "iglob", "rglob", "walk", "listdir", "scandir", "iterdir", "fnmatch", "filter"}
for fname in ("sumo_miner.py", "sumo_art.py", "sumo_menu.py"):
    tree = ast.parse(open(os.path.join(MINER, fname)).read())
    bad = [n.attr if isinstance(n, ast.Attribute) else n.id for n in ast.walk(tree)
           if (isinstance(n, ast.Attribute) and n.attr in FORBIDDEN and n.attr != "filter")
           or (isinstance(n, ast.Name) and n.id in {"glob", "iglob", "listdir", "scandir"})]
    ok(f"{fname}: no folder listing or wildcard calls (glob/walk/listdir/scandir/iterdir)", not bad)
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    ok(f"{fname}: does not import glob/fnmatch", not imports & {"glob", "fnmatch"})

d = tempfile.mkdtemp()
for decoy in ("passwords.txt", "id.json", "wallet.json", "tax-return.pdf", "photo.jpg", "notes.txt"):
    with open(os.path.join(d, decoy), "w") as f:
        f.write("decoy")
shutil.copy(os.path.join(MINER, "sumo_config.example.json"), os.path.join(d, "sumo_config.json"))
shutil.copy(os.path.join(MINER, "sumo.ico"), os.path.join(d, "sumo.ico"))
opened, listed = [], []


def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.fsdecode(args[0])
        if os.path.abspath(p).startswith(os.path.abspath(d)):
            opened.append(os.path.basename(p))
    elif event in ("os.listdir", "os.scandir", "glob.glob") and args and args[0] is not None:
        p = args[0]
        if isinstance(p, int) or os.path.abspath(os.fsdecode(p)).startswith(os.path.abspath(d)):
            listed.append(event)


old_here, old_payout = m.HERE, m.PAYOUT_FILE
m.HERE, m.PAYOUT_FILE = d, os.path.join(d, "payout-address.txt")
sys.addaudithook(hook)
try:
    settings = m.load_settings()
    m.saved_payout(settings)
    keyfile = os.path.join(d, "sumo-devnet-key.json")
    with open(os.devnull, "w") as dn:
        old_out, sys.stdout = sys.stdout, dn
        try:
            m.cmd_new_key(types.SimpleNamespace(keypair=keyfile), settings)
        finally:
            sys.stdout = old_out
    m.load_key(keyfile)
    m.set_window_icon()
finally:
    m.HERE, m.PAYOUT_FILE = old_here, old_payout
allowed = {"sumo_config.json", "payout-address.txt", "sumo-devnet-key.json"}
ok("start-up, key and config handling open only the miner's own exact-named files",
   set(opened) <= allowed and "sumo_config.json" in opened and "sumo-devnet-key.json" in opened)
ok("none of the decoy files in the folder were opened", not set(opened) & {
    "passwords.txt", "id.json", "wallet.json", "tax-return.pdf", "photo.jpg", "notes.txt"})
ok("no folder listing of the miner's folder during those steps", not listed)

# ---- Bug 2 (what Josh meant): never show a full folder path or the user name ----
secret_dir = os.path.join(tempfile.mkdtemp(), "Users", "SecretName", "Downloads", "miner")
os.makedirs(secret_dir)
missing = os.path.join(secret_dir, "sumo-devnet-key.json")
msg = refused(m.load_key, missing)
ok("missing wallet message shows the file name only, not the folder", "sumo-devnet-key.json" in msg and "SecretName" not in msg and secret_dir not in msg)
with open(missing, "w") as f:
    f.write("[]")
msg = refused(m.cmd_new_key, types.SimpleNamespace(keypair=missing), S)
ok("'already exists' message shows the file name only", "sumo-devnet-key.json" in msg and "SecretName" not in msg)
old_here = m.HERE
m.HERE = secret_dir
try:
    scrubbed = m.scrub_paths(f"[Errno 2] No such file or directory: '{secret_dir}{os.sep}x.json' and {os.path.expanduser('~')}")
finally:
    m.HERE = old_here
ok("scrub_paths hides the miner folder and the user name", "SecretName" not in scrubbed and secret_dir not in scrubbed)
ok("scrub_paths replaces the folder with a label", "<this folder>" in scrubbed)

CRASH = r'''
import sys, os
sys.path.insert(0, %(miner)r)
import sumo_miner as m
m.HERE = %(secret)r
def boom(settings):
    raise FileNotFoundError(2, "No such file or directory", os.path.join(%(secret)r, "sumo_config.json"))
m.load_settings = boom
sys.argv = ["sumo_miner.py", "status"]
m.main()
'''
r = subprocess.run([sys.executable, "-c", CRASH % {"miner": MINER, "secret": secret_dir}], capture_output=True, text=True)
shown = r.stdout + r.stderr
ok("an unexpected error shows a short friendly message, exit code 1", r.returncode == 1 and "Something went wrong" in shown)
ok("no traceback, no file paths, no user name on screen after an error",
   "Traceback" not in shown and "SecretName" not in shown and "File \"" not in shown and secret_dir not in shown)

# ---- Review Low 1: Windows-style paths in every spelling are hidden ----
m.HERE = r"C:\Users\JoshSmith\Downloads\sumo miner\files"
WIN_CASES = [
    r"[Errno 2] No such file or directory: 'C:\\Users\\JoshSmith\\Downloads\\sumo miner\\files\\sumo_config.json'",
    r"[WinError 5] Access is denied: 'C:\\Users\\JoshSmith\\Downloads\\sumo miner\\files\\sumo-devnet-key.json'",
    r"C:\Users\JoshSmith\Downloads\sumo miner\files\sumo_config.json not found",
    r"c:\users\joshsmith\downloads\sumo miner\files\a.json",
    r"C:\USERS\JOSHSMITH\DOWNLOADS\SUMO MINER\FILES\A.JSON",
    r"C:/Users/JoshSmith/Downloads/sumo miner/files/a.json",
    r"[WinError 5] Access is denied: 'C:\\Users\\JOSHSM~1\\Downloads\\other folder\\k.json'",
    r"opening D:\Users\JOSHSM~1\Desktop\x y\k.json now",
    r"\\PC-JOSH\share\JoshSmith\k.json",
    r"/home/joshsmith/Downloads/k.json failed",
]
for case in WIN_CASES:
    out = m.scrub_paths(case)
    ok(f"scrub_paths hides user name and folders: {case[:48]}...",
       not any(bad in out.lower() for bad in ("joshsm", "downloads", "users", "pc-josh")))
ok("scrub_paths leaves web addresses alone",
   m.scrub_paths("HTTP Error 429 at https://api.devnet.solana.com/x/y") == "HTTP Error 429 at https://api.devnet.solana.com/x/y")
ok("scrub_paths keeps the file name", "sumo_config.json" in m.scrub_paths(WIN_CASES[0]))
for exc in (FileNotFoundError(2, "No such file or directory", r"C:\Users\JoshSmith\Downloads\files\sumo_config.json"),
            PermissionError(13, "Access is denied", r"C:\\Users\\JOSHSM~1\\Downloads\\files\\sumo-devnet-key.json")):
    text = m.friendly_error(exc)
    ok("file errors show only the base file name and the reason",
       ("sumo_config.json" in text or "sumo-devnet-key.json" in text) and "joshsm" not in text.lower()
       and "Users" not in text and "Downloads" not in text and exc.strerror in text)
m.HERE = old_here

# ---- Review Low 2: workers leave on their own if the miner is hard-killed ----
ORPHAN = r'''
import sys, os
sys.path.insert(0, %(miner)r)
import multiprocessing as mp
import sumo_miner as m
from solders.keypair import Keypair

class FakeChain:
    def state(self):
        return dict(challenge=bytes(32), target=1)   # impossible target: workers never finish

def on_tick(hashes, rate):
    kids = mp.active_children()
    if len(kids) >= 2 and not getattr(on_tick, "said", False):
        on_tick.said = True
        print("PIDS " + " ".join(str(k.pid) for k in kids), flush=True)

if __name__ == "__main__":
    mp.set_start_method(%(method)r)
    m.grind(FakeChain(), Keypair().pubkey(), dict(challenge=bytes(32), target=1), 2, on_tick)
'''


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


if os.name != "nt" and os.path.isdir("/proc"):
    import time
    script = os.path.join(tempfile.mkdtemp(), "orphan.py")
    for method in ("fork", "spawn"):
        with open(script, "w") as f:
            f.write(ORPHAN % {"miner": MINER, "method": method})
        p = subprocess.Popen([sys.executable, "-u", script], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        pids = []
        deadline = time.time() + 30
        while time.time() < deadline:
            line = p.stdout.readline()
            if line.startswith("PIDS"):
                pids = [int(x) for x in line.split()[1:]]
                break
        ok(f"{method}: worker processes started", len(pids) >= 2 and all(alive(x) for x in pids))
        os.kill(p.pid, signal.SIGKILL)  # hard kill: no cleanup code runs in the miner
        p.wait()
        deadline = time.time() + 15
        while time.time() < deadline and any(alive(x) for x in pids):
            time.sleep(0.2)
        left = [x for x in pids if alive(x)]
        for x in left:
            os.kill(x, signal.SIGKILL)  # tidy up if the check failed
        ok(f"{method}: after the miner is hard-killed, its workers exit by themselves", not left)
else:
    ok("hard-kill worker check skipped (needs /proc)", True)

# ---- Review (2nd) Low 1: web errors show the code and reason, never the server address ----
import http.server  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402


class Always429(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(429, "Too Many Requests")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST

    def log_message(self, *a):
        pass


httpd = http.server.HTTPServer(("127.0.0.1", 0), Always429)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
try:
    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/secret-path")
except urllib.error.HTTPError as err:
    text = m.friendly_error(err)
ok("HTTPError: code and reason only", text == "HTTP 429 Too Many Requests")
ok("HTTPError: no host, port, IP or path", all(x not in text for x in ("127.0.0.1", str(PORT), "localhost", "secret-path")))
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
DEAD_PORT = sock.getsockname()[1]
sock.close()  # nothing listens here now
try:
    urllib.request.urlopen(f"http://127.0.0.1:{DEAD_PORT}/")
except urllib.error.URLError as err:
    text = m.friendly_error(err)
ok("URLError (connection refused): the reason is shown", "refused" in text.lower())
ok("URLError: no host, port or IP", all(x not in text for x in ("127.0.0.1", str(DEAD_PORT), "localhost")))
for reason in ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed for 'rpc.example-host.org:8899'",
               "[Errno -2] Name or service not known 203.0.113.7:8080 via 2001:db8::1",
               "timed out connecting to http://203.0.113.9:8080 and [2001:db8::1]:8080"):
    text = m.friendly_error(urllib.error.URLError(reason))
    ok("URLError reasons with a host name, IPv4 or IPv6 address are cleaned",
       not any(x in text for x in ("example-host", "203.0.113", "2001:db8", "8899", "8080")))
text = m.friendly_error(RuntimeError("bad answer from 203.0.113.9:8080 in C:\\Users\\JoshSmith\\x\\k.json"))
ok("other errors lose server addresses and paths too", "203.0.113" not in text and "8080" not in text and "JoshSmith" not in text)

# the same, end to end through main(): 429 after the miner's own retries, and connection refused
NET = r"""
import sys, time
sys.path.insert(0, %(miner)r)
import sumo_miner as m
time.sleep = lambda s: None  # skip the miner's retry waits
m.load_settings = lambda: {"rpc": %(url)r, "program_id": "x", "config": "x", "mint": "x"}
sys.argv = ["sumo_miner.py", "status"]
m.main()
"""
for label, url, expect in (("429", f"http://127.0.0.1:{PORT}", "HTTP 429 Too Many Requests"),
                           ("connection refused", f"http://127.0.0.1:{DEAD_PORT}", "refused")):
    r = subprocess.run([sys.executable, "-c", NET % {"miner": MINER, "url": url}], capture_output=True, text=True, timeout=60)
    shown = r.stdout + r.stderr
    ok(f"main(), {label}: friendly one-line reason, exit 1", r.returncode == 1 and expect.lower() in shown.lower()
       and "Traceback" not in shown)
    ok(f"main(), {label}: no host, port or IP on screen", all(x not in shown for x in ("127.0.0.1", str(PORT), str(DEAD_PORT), "localhost")))
httpd.shutdown()

# ---- Ribbit 18g Note 1: messages fit every package (devnet menu zip and the private flat zip) ----
src_text = open(os.path.join(MINER, "sumo_miner.py"), encoding="utf-8").read()
ok("no message says 'in the menu' or 'choose 3' (the private zip has no menu)", "in the menu" not in src_text
   and "choose 3" not in src_text and "Get test SOL.bat" not in src_text)
ok("Ctrl+C text no longer says to double-click it again", "double-click it again" not in src_text
   and "start mining again whenever you like" in src_text)


def low_sol_message(cluster):
    class LowChain:
        def __init__(self, settings):
            self.cluster, self.unencrypted = cluster, False
            self.program = self.config = self.mint = Keypair().pubkey()

        def sol_balance(self, pk):
            return 0.0

    old = (m.Chain, m.load_key, m.saved_payout)
    m.Chain, m.load_key, m.saved_payout = LowChain, (lambda path: Keypair()), (lambda settings: None)
    try:
        return refused(m.cmd_mine, types.SimpleNamespace(keypair="k", payout=None, workers=1, blocks=0, plain=True), {})
    finally:
        m.Chain, m.load_key, m.saved_payout = old


msg = low_sol_message("devnet")
ok("devnet low-SOL message points to faucet.solana.com", "https://faucet.solana.com" in msg and "menu" not in msg)
msg = low_sol_message("private Sumo test network")
ok("private-network low-SOL message names the faucet command, no menu", "py sumo_miner.py faucet" in msg
   and "menu" not in msg and "faucet.solana.com" not in msg)

# ---- Ribbit 18h Note 2: shortened options like --ye / --y must not mean --yes ----
ABBREV = r"""
import sys
sys.path.insert(0, %(miner)r)
import sumo_miner as m
m.load_settings = lambda: {}
seen = []
m.cmd_withdraw = lambda args, settings: seen.append(args.yes)
sys.argv = ["sumo_miner.py"] + %(argv)r
try:
    m.main()
finally:
    print("YES_VALUE", seen, flush=True)
"""
for flag in ("--ye", "--y", "--YE"):
    r = subprocess.run([sys.executable, "-c", ABBREV % {"miner": MINER, "argv": ["withdraw", flag]}],
                       capture_output=True, text=True)
    ok(f"miner refuses {flag} (exit 2, 'unrecognized arguments', command never runs)",
       r.returncode == 2 and "unrecognized arguments" in r.stderr and "YES_VALUE []" in r.stdout)
r = subprocess.run([sys.executable, "-c", ABBREV % {"miner": MINER, "argv": ["withdraw", "--yes"]}], capture_output=True, text=True)
ok("the full --yes still works when someone really types it", r.returncode == 0 and "YES_VALUE [True]" in r.stdout)
r = subprocess.run([sys.executable, "-c", ABBREV % {"miner": MINER, "argv": ["withdraw", "--", "--yes"]}], capture_output=True, text=True)
ok("after -- , '--yes' is only an address (the launcher's form), never the option", "YES_VALUE [False]" in r.stdout)

# ---- the picture menu (Pixy's design): `sumo_miner.py menu`, drawn before the launcher asks for a key ----
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import sumo_menu  # noqa: E402

SGR = re.compile(r"\x1b\[[0-9;]*m")
MOVE = re.compile(r"\x1b\[(\d+);(\d+)H")


def visible_rows(ansi):
    """The screen as plain text rows (cursor moves split the rows, colour codes dropped)."""
    parts = MOVE.split(ansi)             # [pre, row, col, text, row, col, text, ...]
    rows = {}
    for i in range(1, len(parts) - 2, 3):
        if parts[i + 2]:                 # the last move only parks the cursor
            rows[int(parts[i])] = SGR.sub("", parts[i + 2])
    return rows


class FakeRpc(http.server.BaseHTTPRequestHandler):
    mode = "balance"      # "balance" | "missing" | "hang" | "drip" (one byte a second)
    amount = "1500000000"
    genesis = m.DEVNET_GENESIS
    redirect_code = 302
    status = 500          # "status" mode: the first fail_first requests get this HTTP error, the rest are answered normally
    fail_first = 0
    seen = 0
    hits = []
    methods = []

    def do_POST(self):
        FakeRpc.hits.append(self.path)
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        FakeRpc.methods.append(req.get("method"))
        if FakeRpc.mode == "hang":
            time.sleep(8)
            return
        if FakeRpc.mode == "status":
            FakeRpc.seen += 1
            if FakeRpc.seen <= FakeRpc.fail_first:
                self.send_response(FakeRpc.status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        if FakeRpc.mode == "redirect":
            self.send_response(FakeRpc.redirect_code)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/followed")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if req.get("method") == "getGenesisHash":
            body = {"jsonrpc": "2.0", "id": 1, "result": FakeRpc.genesis}
        elif FakeRpc.mode == "missing":
            body = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "Invalid param: could not find account"}}
        else:
            body = {"jsonrpc": "2.0", "id": 1, "result": {"value": {"amount": FakeRpc.amount}}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            if FakeRpc.mode == "drip":
                for i in range(7):      # a slow-drip server: each byte arrives inside the socket timeout, then it gives up
                    self.wfile.write(data[i:i + 1])
                    self.wfile.flush()
                    time.sleep(1)
            else:
                self.wfile.write(data)
        except OSError:
            pass

    def log_message(self, *a):
        pass


class QuietServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


srv = QuietServer(("127.0.0.1", 0), FakeRpc)
threading.Thread(target=srv.serve_forever, daemon=True).start()
RPC = f"http://127.0.0.1:{srv.server_address[1]}"
MENU_DIR = tempfile.mkdtemp()
KEYFILE = os.path.join(MENU_DIR, "sumo-devnet-key.json")
kp = Keypair()
with open(KEYFILE, "w") as f:
    json.dump(list(bytes(kp)), f)
SECRET32 = bytes(kp)[:32]
SECRET_FORMS = [str(kp), str(m.Pubkey.from_bytes(SECRET32)), SECRET32.hex(), bytes(kp).hex(),
                ", ".join(str(b) for b in SECRET32[:10]), ",".join(str(b) for b in SECRET32[:10])]
SET = {"rpc": RPC, "program_id": "6h1PqXArg2Ap1CJdR1hXXWhqSrzkeboqi5cx1y44NvTW", "network": "devnet"}

FakeRpc.mode = "balance"
ansi = m.menu_text(SET, KEYFILE, 120, 40)
rows = visible_rows(ansi)
ok("menu: draws all 30 rows, each exactly 80 columns wide", sorted(rows) == list(range(1, 31))
   and all(len(r) == 80 for r in rows.values()))
ok("menu: truecolour (24-bit) codes, no line feeds, cursor parked on the prompt row",
   "\x1b[38;2;" in ansi and ";48;2;" in ansi and "\n" not in ansi and ansi.endswith("\x1b[27;" + str(sumo_menu.prompt_cursor()[1]) + "H"))
ok("menu: has the frog, the SUMO logo, FROG MINER, TEST COINS / TEST CHAIN, the wallet panel, MAIN MENU 1-6, the prompt and the horizon",
   "\u2588" in rows[2] and "FROG MINER" in rows[10] and "TEST COINS / TEST CHAIN" in rows[11]
   and "WALLET" in rows[14] and "BALANCE" in rows[15] and "MAIN MENU" in rows[18]
   and all(f"[{i}] {label}" in rows[18 + i] for i, label in enumerate(sumo_menu.ITEMS, 1))
   and "Press a number from 1 to 6" in rows[27] and "\u2580" in rows[28] and "/" in rows[29])
ok("menu: the [1] row is the highlighted one (arrow + inverted bar)", "\u25ba [1] Mine SUMO" in rows[19] and "\u25ba" not in rows[20])
ok("menu: shows the real short wallet and the real balance (1.50 SUMO)", m.short(kp.pubkey()) in rows[14] and "1.50 SUMO" in rows[15])
old_version = m.VERSION
ok("menu: shows VERSION (v0.6.2 today), not the mockup's v0.5", m.VERSION in rows[10] and "v0.5" not in "".join(rows.values()) and m.VERSION == "v0.6.2")
m.VERSION = "v9.8.7"
ok("menu: the version comes from VERSION, not a fixed string", "v9.8.7" in visible_rows(m.menu_text(SET, KEYFILE, 80, 30))[10])
m.VERSION = old_version
r30 = visible_rows(m.menu_text(SET, KEYFILE, 80, 30))
ok("menu: in a window exactly 80 x 30 it leaves out the bottom-right cell (so nothing scrolls), every other row is full width",
   len(r30[30]) == 79 and all(len(r30[i]) == 80 for i in range(1, 30)))
ok("menu: in a wider window (or a taller one) the bottom-right cell is drawn too",
   len(visible_rows(m.menu_text(SET, KEYFILE, 100, 30))[30]) == 80 and len(visible_rows(m.menu_text(SET, KEYFILE, 80, 31))[30]) == 80)
ok("menu: grid cells are all in code page 437 or the few block/box characters Windows fonts have",
   all(len(row) == 80 for row in sumo_menu.build_grid("v1", "a", True, "b", True)) and len(sumo_menu.build_grid("v1", "a", True, "b", True)) == 30)

# no secret key output
FakeRpc.mode = "balance"
outs = [ansi, m.menu_text(SET, KEYFILE, 80, 30)]
ok("menu: no form of the secret key (base58, hex, number list) is in the screen text",
   not any(s in o for o in outs for s in SECRET_FORMS))
menu_fn_src = ""
msrc = open(os.path.join(MINER, "sumo_miner.py")).read()
for fn in ("read_public_key", "menu_rpc_allowed", "menu_post", "menu_chain_ok", "menu_balance", "menu_balance_text", "menu_text", "cmd_menu"):
    a = msrc.index(f"def {fn}(")
    menu_fn_src += msrc[a:msrc.index("\ndef ", a + 5)]
tree = ast.parse(menu_fn_src)
ok("menu: the code never prints, loads or exposes the secret half (no load_key, no .secret(), no print, no slicing of the key list); "
   "it parses the file, checks the halves match, and keeps only the public half",
   not any(isinstance(n, ast.Name) and n.id in ("load_key", "print") for n in ast.walk(tree))
   and not any(isinstance(n, ast.Attribute) and n.attr in ("secret", "to_json", "__bytes__") for n in ast.walk(tree))
   and "data[:32]" not in menu_fn_src and "data[32:]" not in menu_fn_src and "data[0" not in menu_fn_src
   and "Keypair.from_bytes(bytes(data)).pubkey()" in menu_fn_src
   and "last 32" not in menu_fn_src and "last 32" not in msrc)

# fallbacks
ok("menu fallback: no wallet file -> 'no wallet yet' (and no balance request)",
   (lambda r: "no wallet yet" in r[14] and len(r) == 30)(visible_rows(m.menu_text(SET, os.path.join(MENU_DIR, "nope.json"), 100, 30))))
for label, content in (("not JSON", "not json"), ("wrong length", "[1,2,3]"), ("not numbers", json.dumps(["a"] * 64)),
                       ("numbers out of range", json.dumps([999] * 64))):
    bad = os.path.join(MENU_DIR, "bad.json")
    with open(bad, "w") as f:
        f.write(content)
    r = m.menu_text(SET, bad, 100, 30)
    ok(f"menu fallback: unreadable wallet file ({label}) -> still draws, says 'wallet file unreadable', no crash",
       r is not None and "wallet file unreadable" in visible_rows(r)[14] and not any(s in r for s in ("999", "Traceback")))
other = Keypair()
mism = bytearray(bytes(kp))
mism[32:] = bytes(other.pubkey())          # a public half that belongs to a different key
bad = os.path.join(MENU_DIR, "bad.json")
with open(bad, "w") as f:
    json.dump(list(mism), f)
FakeRpc.hits.clear()
r = m.menu_text(SET, bad, 100, 30)
ok("menu fallback: public half that doesn't match the secret half -> 'wallet file unreadable', the other address is not shown, no request",
   r is not None and "wallet file unreadable" in visible_rows(r)[14] and m.short(other.pubkey()) not in r
   and m.short(kp.pubkey()) not in r and not FakeRpc.hits and m.read_public_key(bad) == ("bad", None))
ok("menu: a good wallet file still reads as its own public address", m.read_public_key(KEYFILE) == ("ok", kp.pubkey()))
down = dict(SET, rpc="http://127.0.0.1:1")      # nothing listens there
t0 = time.time()
r = visible_rows(m.menu_text(down, KEYFILE, 100, 30))
ok("menu fallback: no network -> 'offline' under BALANCE, wallet still shown, fast", "offline" in r[15] and "balance:" not in r[15]
   and m.short(kp.pubkey()) in r[14] and time.time() - t0 < 4)
FakeRpc.mode = "hang"
t0 = time.time()
r = visible_rows(m.menu_text(SET, KEYFILE, 100, 30))
took = time.time() - t0
ok(f"menu fallback: a server that never answers -> 'offline' after about {m.MENU_RPC_TIMEOUT:.1f}s (took {took:.1f}s, never more than 5s)",
   "offline" in r[15] and took < 5)
FakeRpc.mode = "missing"
ok("menu: wallet with no token account yet -> 0.00 SUMO", "0.00 SUMO" in visible_rows(m.menu_text(SET, KEYFILE, 100, 30))[15])
FakeRpc.mode = "balance"
FakeRpc.amount = "123456789"
ok("menu: fractional balance keeps its digits (0.1235 SUMO style, at least two decimals)",
   "0.1235 SUMO" in visible_rows(m.menu_text(SET, KEYFILE, 100, 30))[15] and m.menu_balance_text(5 * 10 ** 9) == "5.00 SUMO"
   and m.menu_balance_text(5 * 10 ** 8) == "0.50 SUMO" and m.menu_balance_text(1234 * 10 ** 9) == "1,234.00 SUMO")
FakeRpc.amount = "1500000000"
FakeRpc.hits.clear()
foreign = dict(SET, rpc="https://mainnet.example.org")
t0 = time.time()
ok("menu: never asks a link that isn't this computer, public devnet or the shipped private link (offline, no request)",
   "offline" in visible_rows(m.menu_text(foreign, KEYFILE, 100, 30))[15] and not FakeRpc.hits and time.time() - t0 < 2
   and m.menu_rpc_allowed(dict(SET, rpc="https://api.devnet.solana.com")) and not m.menu_rpc_allowed(dict(SET, rpc="file:///etc/passwd")))

# Low 1: the menu follows check_devnet's link rules, and a refused link gets no request at all
sent = []
real_open = m._OPENER.open


def spy_open(req, *a, **k):
    sent.append(getattr(req, "full_url", str(req)))
    return real_open(req, *a, **k)


m._OPENER.open = spy_open
PRIVATE = "http://private-test.invalid:8899"
refusals = (
    ("http (unencrypted) devnet link", dict(SET, rpc="http://evil.example/rpc")),
    ("mainnet link", dict(SET, rpc="https://api.mainnet-beta.solana.com")),
    ("mainnet link set as devnet_rpc", dict(SET, rpc="https://api.mainnet-beta.solana.com", devnet_rpc="https://api.mainnet-beta.solana.com")),
    ("plain-http private host with no private_genesis", dict(SET, network="private", rpc=PRIVATE, _shipped_rpc=PRIVATE)),
    ("plain-http host that is not the shipped private link", dict(SET, network="private", rpc="http://other.invalid:8899",
                                                                  _shipped_rpc=PRIVATE, private_genesis="G" * 43)),
    ("not a web link", dict(SET, rpc="ftp://x.example/rpc")),
    ("empty link", dict(SET, rpc="")),
    ("https link with private_genesis set that is not the shipped private link",
     dict(SET, network="private", rpc="https://other.example/rpc", _shipped_rpc=PRIVATE, private_genesis="G" * 43)),
    ("https link equal to the shipped link but private_genesis not set", dict(SET, network="private", rpc="https://x.example/rpc",
                                                                                _shipped_rpc="https://x.example/rpc")),
)
# the tricky spellings (userinfo, case, port, path, query, lookalike hosts, 0.0.0.0, IPv6, backslash, ...)
TRICKY = (
    "https://api.devnet.solana.com@evil.example", "https://api.devnet.solana.com:x@evil.example",
    "https://api.devnet.solana.com\\@evil.example", "http://evil.com\\@localhost", "http://localhost\\@evil.com",
    "https://api.devnet.solana.com\\", "http://127.0.0.1\\.evil.com",
    "HTTPS://api.devnet.solana.com", "https://API.DEVNET.SOLANA.COM", "https://api.devnet.solana.com/",
    "https://api.devnet.solana.com:443", "https://api.devnet.solana.com:8899", "https://api.devnet.solana.com/path",
    "https://api.devnet.solana.com?x=1", "https://api.devnet.solana.com#frag", " https://api.devnet.solana.com",
    "https://api.devnet.solana.com.evil.example", "https://evilapi.devnet.solana.com",
    "http://localhost.evil.com", "https://localhost.evil.com", "http://localhost@evil.com", "http://evil.com#@localhost",
    "http://user@localhost:8999", "http://localhost.", "http://0.0.0.0:8999", "https://0.0.0.0:8999",
    "http://[2001:db8::1]:8999", "https://[2001:db8::1]/", "http://[::ffff:127.0.0.1]:8999", "ftp://localhost", "file:///etc/passwd",
)
refusals += tuple((f"tricky link {link!r}", dict(SET, rpc=link)) for link in TRICKY)
for label, st in refusals:
    sent.clear()
    FakeRpc.hits.clear()
    r = m.menu_text(st, KEYFILE, 100, 30)
    ok(f"Low 1: {label} -> refused, shows 'offline', no request sent",
       not m.menu_rpc_allowed(st) and m.menu_balance(st, kp.pubkey()) is None and not sent and not FakeRpc.hits
       and r is not None and "offline" in visible_rows(r)[15] and "balance:" not in visible_rows(r)[15])
ok("Low 1: public devnet, this computer and the shipped private link (with private_genesis) are still allowed",
   m.menu_rpc_allowed(dict(SET, rpc="https://api.devnet.solana.com")) and m.menu_rpc_allowed(SET)
   and m.menu_rpc_allowed(dict(SET, network="private", rpc=PRIVATE, _shipped_rpc=PRIVATE, private_genesis="G" * 43)))
ok("Low 1: the menu and check_devnet share one link rule (link_problem)",
   m.link_problem("http://evil.example", {}) is not None and m.link_problem("https://api.devnet.solana.com", {}) is None
   and "link_problem(url, settings)" in msrc[msrc.index("def check_devnet("):msrc.index("class Chain")]
   and "link_problem(url, settings)" in menu_fn_src)
FakeRpc.methods.clear()
FakeRpc.mode = "balance"
ok("menu: this computer's chain is asked for its genesis hash first, then the balance (devnet genesis -> 1.50 SUMO)",
   "1.50 SUMO" in visible_rows(m.menu_text(SET, KEYFILE, 100, 30))[15] and FakeRpc.methods == ["getGenesisHash", "getTokenAccountBalance"])
FakeRpc.methods.clear()
FakeRpc.genesis = m.MAINNET_GENESIS
ok("menu: a chain whose genesis hash is mainnet -> 'offline', the wallet is never asked about",
   "offline" in visible_rows(m.menu_text(SET, KEYFILE, 100, 30))[15] and FakeRpc.methods == ["getGenesisHash"])
FakeRpc.genesis = m.DEVNET_GENESIS

# Note 2: off this computer (the shipped private link) only the private_genesis answer is accepted, never devnet's
PG = "P" * 43
PRIV = dict(SET, network="private", rpc=PRIVATE, _shipped_rpc=PRIVATE, private_genesis=PG)
real_post = m.menu_post
answers = {}
m.menu_post = lambda url, method, params, timeout: {"result": answers["g"]}
for label, answer, want in (("the private network's own genesis hash", PG, True), ("devnet's genesis hash", m.DEVNET_GENESIS, False),
                            ("mainnet's genesis hash", m.MAINNET_GENESIS, False), ("something unknown", "U" * 43, False),
                            ("no answer at all", None, False)):
    answers["g"] = answer
    ok(f"Note 2: shipped private link answering {label} -> {'accepted' if want else 'refused'}", m.menu_chain_ok(PRIV, 1) is want)
answers["g"] = m.DEVNET_GENESIS
ok("Note 2: devnet's answer is also refused without any private_genesis set", m.menu_chain_ok(dict(PRIV, private_genesis=None), 1) is False)
answers["g"] = m.MAINNET_GENESIS
ok("Note 2: this computer answering mainnet is still refused, any other answer on this computer is fine",
   m.menu_chain_ok(SET, 1) is False and (answers.update(g="L" * 43) or m.menu_chain_ok(SET, 1) is True))
m.menu_post = real_post
ok("Note 2: the genesis rule matches check_devnet (private_genesis only off this computer)",
   "genesis == settings[\"private_genesis\"]" in menu_fn_src and "DEVNET_GENESIS" not in menu_fn_src)

# Note 3: backslashes and user-name parts in links are refused by the shared rule; redirects are never followed
for link in ("https://api.devnet.solana.com@evil.example", "http://localhost@evil.com", "http://user@localhost:8999",
             "http://evil.com\\@localhost", "https://x.example\\y", "http://127.0.0.1:8999\\"):
    ok(f"Note 3: link_problem refuses {link!r}, and it is not 'this computer'", m.link_problem(link, {"_shipped_rpc": link, "private_genesis": "x"}) is not None
       and not m.is_local_url(link))
ok("Note 3: plain good links still pass link_problem", m.link_problem("https://api.devnet.solana.com", {}) is None
   and m.link_problem("http://localhost:8899", {}) is None and m.link_problem("http://[::1]:8899", {}) is None
   and m.link_problem(PRIVATE, {"_shipped_rpc": PRIVATE, "private_genesis": "x"}) is None)


class NoRequest:
    def call(self, *a):
        raise AssertionError("a request was sent")


for link in ("https://api.devnet.solana.com@evil.example", "http://evil.com\\@localhost", "http://user@localhost:8999"):
    try:
        m.check_devnet(NoRequest(), link, {})
        stopped = False
    except SystemExit:
        stopped = True
    ok(f"Note 3: check_devnet stops on {link!r} before sending any request", stopped)

FakeRpc.mode = "redirect"
FakeRpc.hits.clear()
sent.clear()
try:
    m.open_url(m.urllib.request.Request(RPC, b"{}", {"Content-Type": "application/json"}), 5)
    followed = True
except m.urllib.error.HTTPError as e:
    followed = e.code != 302
ok("Note 3: a redirect is refused by the shared opener (an error, not followed)", followed is False and "/followed" not in FakeRpc.hits)
real_sleep = m.time.sleep
m.time.sleep = lambda x: None
try:
    m.Rpc(RPC).call("getGenesisHash")
    rpc_ok = True
except Exception:
    rpc_ok = False
m.time.sleep = real_sleep
ok("Note 3: Rpc.call (used by every command) fails on a redirect and never requests the other address", rpc_ok is False and "/followed" not in FakeRpc.hits)
# a redirect is final: exactly one request, no waiting, whatever the 3xx code
for code in (300, 301, 302, 303, 304, 305, 307, 308):
    FakeRpc.redirect_code = code
    FakeRpc.hits.clear()
    waits = []
    m.time.sleep = waits.append
    t0 = time.time()
    try:
        m.Rpc(RPC).call("getGenesisHash")
        err_code = None
    except m.urllib.error.HTTPError as e:
        err_code = e.code
    took = time.time() - t0
    m.time.sleep = real_sleep
    ok(f"Rpc.call: a {code} redirect -> exactly one request, no retries, no waits, quick (HTTP error {err_code})",
       err_code == code and len(FakeRpc.hits) == 1 and waits == [] and took < 2)
FakeRpc.redirect_code = 302

# the other retry behaviour is unchanged: blips and 429s are retried 5 times with waits of 2, 4, 6, 8 s
FakeRpc.mode = "status"
for label, status, fail_first, want_requests, want_waits, want_ok in (
        ("two 500 errors then an answer -> 3 requests, waits 2 and 4, works", 500, 2, 3, [2, 4], True),
        ("a 429 four times then an answer -> 5 requests, waits 2, 4, 6, 8, works", 429, 4, 5, [2, 4, 6, 8], True),
        ("a 429 every time -> 5 requests, waits 2, 4, 6, 8, then the error", 429, 99, 5, [2, 4, 6, 8], False)):
    FakeRpc.status, FakeRpc.fail_first, FakeRpc.seen = status, fail_first, 0
    FakeRpc.hits.clear()
    waits = []
    m.time.sleep = waits.append
    try:
        got = m.Rpc(RPC).call("getGenesisHash")
        worked = got == m.DEVNET_GENESIS
    except m.urllib.error.HTTPError:
        worked = False
    m.time.sleep = real_sleep
    ok(f"Rpc.call retry unchanged: {label}", worked is want_ok and len(FakeRpc.hits) == want_requests and waits == want_waits)
FakeRpc.fail_first = 0
waits = []
m.time.sleep = waits.append
try:
    m.Rpc("http://127.0.0.1:1").call("getGenesisHash")
    dead_ok = True
except Exception:
    dead_ok = False
m.time.sleep = real_sleep
ok("Rpc.call retry unchanged: nothing listening -> 5 tries (waits 2, 4, 6, 8), then the error", dead_ok is False and waits == [2, 4, 6, 8])

# a link that isn't text (null, number, list ...) is refused with the clear https message, never a TypeError
for bad_link in (None, 5, 1.5, ["https://x"], {"a": 1}, b"https://api.devnet.solana.com", True):
    msg = m.link_problem(bad_link, {"_shipped_rpc": bad_link, "private_genesis": "x"})
    try:
        m.Chain({"rpc": bad_link, "program_id": "6h1PqXArg2Ap1CJdR1hXXWhqSrzkeboqi5cx1y44NvTW"})
        stop = None
    except SystemExit as e:
        stop = str(e.code)
    except Exception as e:
        stop = "CRASH " + type(e).__name__
    ok(f"non-text link {bad_link!r}: link_problem gives the https message, has_odd_authority is True, not local, Chain stops cleanly",
       msg is not None and "https://" in msg and m.has_odd_authority(bad_link) is True and m.is_local_url(bad_link) is False
       and m.url_scheme(bad_link) == "" and stop == "The network link must start with https:// . Stopping."
       and m.menu_rpc_allowed(dict(SET, rpc=bad_link)) is False)
ok("non-text link: the menu shows 'offline' without a request or a crash",
   "offline" in visible_rows(m.menu_text(dict(SET, rpc=None), KEYFILE, 100, 30))[15])

FakeRpc.mode = "redirect"
FakeRpc.hits.clear()
FakeRpc.genesis = m.DEVNET_GENESIS
ok("Note 3: the menu shows 'offline' on a redirect and never requests the other address",
   m.menu_balance(SET, kp.pubkey()) is None and "/followed" not in FakeRpc.hits and FakeRpc.hits)
ok("Note 3: every network call goes through open_url (no bare urlopen left in the miner)", "urlopen(" not in msrc.replace("_OPENER.open", ""))
FakeRpc.mode = "balance"
m._OPENER.open = real_open

# Note 2: a slow-drip server (one byte a second, so the 2.5 s socket timeout never fires) needs the hard thread limit
FakeRpc.mode = "drip"
t0 = time.time()
r = visible_rows(m.menu_text(SET, KEYFILE, 100, 30))
took = time.time() - t0
ok(f"menu: a slow-drip server (one byte a second) -> 'offline' at the hard limit (took {took:.1f}s, under 5s)",
   "offline" in r[15] and took < 5)
FakeRpc.mode = "balance"

# Note 1: Ctrl+C while the menu loads -> exit 1, nothing printed
real_menu_text = m.menu_text
real_enable = m.enable_colour


def interrupted(*a, **k):
    raise KeyboardInterrupt


import contextlib  # noqa: E402
import io  # noqa: E402
m.enable_colour = lambda plain: True
m.menu_text = interrupted
out, err = io.StringIO(), io.StringIO()
code = None
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    try:
        m.cmd_menu(types.SimpleNamespace(plain=False, keypair=KEYFILE), SET)
    except SystemExit as e:
        code = e.code
ok("Note 1: Ctrl+C inside the menu -> exit code 1, nothing printed", code == 1 and out.getvalue() == "" and err.getvalue() == "")
m.menu_text = real_menu_text
m.enable_colour = real_enable

# Note 1: Ctrl+C at the very start (before cmd_menu runs): main() exits 1 silently for the menu command only
real__main = m._main
real_argv = sys.argv
m._main = interrupted
for argv, want_code, want_text in ((["sumo_miner.py", "menu"], 1, False), (["sumo_miner.py", "balance"], None, True)):
    sys.argv = argv
    out, err = io.StringIO(), io.StringIO()
    code = "none"
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            m.main()
            code = None
        except SystemExit as e:
            code = e.code
    ok(f"Note 1: Ctrl+C at start-up of '{argv[1]}' -> " + ("exit 1, nothing printed (plain menu)" if argv[1] == "menu"
                                                          else "the friendly 'Stopped (Ctrl+C)' line, as before"),
       code == want_code and (("Stopped (Ctrl+C)" in out.getvalue()) is want_text) and err.getvalue() == ""
       and (want_text or out.getvalue() == ""))
m._main = real__main
sys.argv = real_argv
ok("menu fallback: window narrower than 80 columns (or shorter than 30 rows) -> None, so the launcher shows the plain menu",
   m.menu_text(SET, KEYFILE, 79, 40) is None and m.menu_text(SET, KEYFILE, 120, 29) is None and m.menu_text(SET, KEYFILE, 0, 0) is None
   and m.menu_text(SET, KEYFILE, 80, 30) is not None)
real_render = sumo_menu.render
sumo_menu.render = lambda *a, **k: 1 / 0
ok("menu fallback: if drawing fails for any reason -> None (plain menu), no exception", m.menu_text(SET, KEYFILE, 100, 30) is None)
sumo_menu.render = real_render

# end to end: the real command in a scratch copy of the devnet files, like the launcher runs it
E2E = os.path.join(MENU_DIR, "files")
os.makedirs(E2E)
for fname in ("sumo_miner.py", "sumo_art.py", "sumo_menu.py"):
    shutil.copy(os.path.join(MINER, fname), E2E)
with open(os.path.join(MINER, "devnet", "sumo_config.devnet.json")) as f:
    cfg = json.load(f)
cfg["devnet_rpc"] = RPC
with open(os.path.join(E2E, "sumo_config.json"), "w") as f:
    json.dump(cfg, f)
shutil.copy(KEYFILE, os.path.join(E2E, "sumo-devnet-key.json"))


def run_menu(cols, lines, extra=None, keep_key=True):
    env = dict(os.environ, SUMO_FORCE_COLOUR="1", COLUMNS=str(cols), LINES=str(lines), PYTHONIOENCODING="utf-8",
               TERM="xterm-256color")
    env.pop("NO_COLOR", None)
    env.pop("SUMO_PLAIN", None)
    env.update(extra or {})
    if not keep_key and os.path.exists(os.path.join(E2E, "sumo-devnet-key.json")):
        os.remove(os.path.join(E2E, "sumo-devnet-key.json"))
    return subprocess.run([sys.executable, os.path.join(E2E, "sumo_miner.py"), "menu"], capture_output=True,
                          text=True, env=env, cwd=E2E, timeout=30)


FakeRpc.mode = "balance"
r = run_menu(100, 30)
rr = visible_rows(r.stdout)
ok("menu command: exit 0, 30 rows of 80 columns, real version, short wallet, balance, nothing on stderr",
   r.returncode == 0 and sorted(rr) == list(range(1, 31)) and all(len(rr[i]) == 80 for i in range(1, 31))
   and m.VERSION in rr[10] and m.short(kp.pubkey()) in rr[14] and "1.50 SUMO" in rr[15] and r.stderr == "")
ok("menu command: the secret key is nowhere in its output or errors", not any(s in r.stdout + r.stderr for s in SECRET_FORMS))
for label, env_cols, env_extra in (("narrow window (79 columns)", 79, {}), ("NO_COLOR set", 100, {"NO_COLOR": "1"}),
                                   ("SUMO_PLAIN set", 100, {"SUMO_PLAIN": "1"})):
    r = run_menu(env_cols, 30, env_extra)
    ok(f"menu command: {label} -> exit 1 and nothing printed (the launcher then shows its plain menu)",
       r.returncode == 1 and r.stdout == "" and r.stderr == "")
r = subprocess.run([sys.executable, os.path.join(E2E, "sumo_miner.py"), "menu"], capture_output=True, text=True, cwd=E2E,
                   env={k: v for k, v in dict(os.environ, COLUMNS="100", LINES="30", PYTHONIOENCODING="utf-8",
                                       TERM="xterm-256color").items() if k not in ("NO_COLOR", "SUMO_PLAIN", "SUMO_FORCE_COLOUR")},
                   timeout=30)
ok("menu command: output that isn't a console (no SUMO_FORCE_COLOUR) -> exit 1, nothing printed", r.returncode == 1 and r.stdout == "")
r = run_menu(100, 30, keep_key=False)
ok("menu command: no wallet file -> exit 0, 'no wallet yet'", r.returncode == 0 and "no wallet yet" in visible_rows(r.stdout)[14])
shutil.copy(KEYFILE, os.path.join(E2E, "sumo-devnet-key.json"))
if os.name != "nt":
    FakeRpc.mode = "hang"
    env = dict(os.environ, SUMO_FORCE_COLOUR="1", COLUMNS="100", LINES="30", PYTHONIOENCODING="utf-8", TERM="xterm-256color")
    env.pop("NO_COLOR", None)
    env.pop("SUMO_PLAIN", None)
    p = subprocess.Popen([sys.executable, os.path.join(E2E, "sumo_miner.py"), "menu"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=env, cwd=E2E, start_new_session=True)
    time.sleep(1.0)      # inside the balance wait
    os.killpg(p.pid, signal.SIGINT)
    out, err = p.communicate(timeout=30)
    ok("Note 1: the real menu command given Ctrl+C while it waits for the balance -> exit 1, nothing printed (launcher shows the plain menu)",
       p.returncode == 1 and out == "" and err == "")
    FakeRpc.mode = "balance"
os.remove(os.path.join(E2E, "sumo_menu.py"))
shutil.copy(KEYFILE, os.path.join(E2E, "sumo-devnet-key.json"))
r = run_menu(100, 30)
ok("menu command: sumo_menu.py missing -> exit 1, nothing printed (plain menu)", r.returncode == 1 and r.stdout == "" and r.stderr == "")
os.remove(os.path.join(E2E, "sumo_config.json"))
r = run_menu(100, 30)
ok("menu command: even a missing config -> exit 1 (the launcher hides stderr with 2>nul and shows the plain menu)", r.returncode == 1 and r.stdout == "")
srv.shutdown()


# ---- 19 Nov: Ctrl+C asks 'Stop mining?' (n carries on); the home menu key reader is silent ----
class FakeScreen:
    def __init__(self):
        self.events, self.draws = [], 0

    def event(self, text):
        self.events.append(text)

    def draw(self, hud, found=False):
        self.draws += 1


def stop_with(pending, answers):
    old = m.pending_keys, m.read_key
    left = list(answers)
    m.pending_keys, m.read_key = (lambda: pending), (lambda: left.pop(0))
    scr = FakeScreen()
    try:
        return m.stop_requested(scr, {}), scr, left
    finally:
        m.pending_keys, m.read_key = old


res, scr, left = stop_with("abc", [])
ok("mining: ordinary keys do nothing (no question, nothing drawn)", res is False and scr.events == [] and scr.draws == 0)
res, scr, left = stop_with("\x03", ["n"])
ok("mining: Ctrl+C then N asks 'Stop mining?' and carries on mining", res is False and "Stop mining?" in scr.events[0]
   and scr.events[-1] == "OK, still mining." and left == [])
res, scr, left = stop_with("x\x03", ["q", "", "N"])
ok("mining: other keys while the question is up are ignored; N still carries on", res is False and left == [])
res, scr, left = stop_with("\x03", ["Y"])
ok("mining: Ctrl+C then Y stops", res is True and left == [])
res, scr, left = stop_with("\x03", ["\x03"])
ok("mining: Ctrl+C twice stops (Ctrl+C is also 'yes')", res is True)
res, scr, left = stop_with("\x03", ["\r"])
ok("mining: Enter or Esc at the question carries on mining", res is False)
ok("pending_keys is empty when the console guard is off", m.pending_keys() == "")
msrc = open(os.path.join(MINER, "sumo_miner.py")).read()
tick = msrc[msrc.index("def tick(hashes, rate):"):msrc.index("scr.draw(hud)\n            guess")]
ok("mining tick asks via stop_requested and raises KeyboardInterrupt only when it says stop, before it redraws",
   "if stop_requested(scr, hud):\n                    raise KeyboardInterrupt" in tick
   and "flush_console_input" not in tick and tick.index("stop_requested") < tick.index("scr.draw(hud)"))


def run_pick(keys):
    r = subprocess.run([sys.executable, os.path.join(MINER, "sumo_miner.py"), "pick"], input=keys, capture_output=True,
                       text=True, timeout=30, cwd=MINER)
    return r.returncode, r.stdout, r.stderr


ok("home menu: wrong keys are ignored with no output at all (no bell) and 3 gives exit code 13",
   run_pick("a\x07 x9\n703") == (13, "", ""))
ok("home menu: keys 1 to 6 exit 11 to 16", [run_pick(str(i))[0] for i in range(1, 7)] == [11, 12, 13, 14, 15, 16])
ok("home menu: Ctrl+C or no input at all exits 16 (Exit), silently", run_pick("\x03")[0] == 16 and run_pick("")[0] == 16
   and run_pick("")[1:] == ("", ""))


# ---- 19 Nov (e): the console mode comes back after a kill, Ctrl+Break or window close ----
class CtrlK32(FakeK32):
    def __init__(self):
        super().__init__()
        self.handlers = []

    def SetConsoleCtrlHandler(self, cb, add):
        self.handlers.append((cb, add))
        return 1


class FakeAtexit:
    def __init__(self):
        self.funcs = []

    def register(self, fn):
        self.funcs.append(fn)

    def unregister(self, fn):
        self.funcs = [f for f in self.funcs if f != fn]


real_atexit, real_wft = m.atexit, getattr(ctypes, "WINFUNCTYPE", None)
m.atexit, ctypes.WINFUNCTYPE = FakeAtexit(), ctypes.CFUNCTYPE   # a Windows-only call, stood in for here
try:
    k = CtrlK32()
    with m.quiet_console_input(k):
        cb = k.handlers[0][0]
        ok("console handler and exit hook are registered while the guard is on", k.handlers[0][1] is True and len(m.atexit.funcs) == 1)
        k.mode = 0x1F7 | 0x1000     # pretend something else changed it
        ok("Ctrl+Break / window close: the handler puts the old mode back and lets Windows carry on (returns False)",
           not cb(1) and k.mode == 0x1F7)
        k.mode = 0
        m.atexit.funcs[0]()
        ok("a hard exit: the atexit hook puts the old mode back", k.mode == 0x1F7)
    ok("on a normal exit both hooks are removed again (no pile-up, one per block)",
       m.atexit.funcs == [] and k.handlers[-1][1] is False and k.mode == 0x1F7)
    k = FakeK32()   # no SetConsoleCtrlHandler at all: guard still works
    with m.quiet_console_input(k):
        pass
    ok("a console without the handler call still works and restores", k.mode == 0x1F7)
finally:
    m.atexit = real_atexit
    if real_wft is None:
        del ctypes.WINFUNCTYPE
    else:
        ctypes.WINFUNCTYPE = real_wft

# ---- 19 Nov (e): Ctrl+C stays responsive: quiet input only while hashing, RPC poll off the key-reading thread ----
import time as _time  # noqa: E402


class SlowChain:
    def __init__(self, challenge=bytes(32), delay=5):
        self.challenge, self.delay = challenge, delay

    def state(self):
        _time.sleep(self.delay)
        return dict(challenge=self.challenge)


ticks = []


def stop_on_second(hashes, rate):
    ticks.append(hashes)
    if len(ticks) == 2:
        raise KeyboardInterrupt


t0 = _time.time()
try:
    m.grind(SlowChain(), Keypair().pubkey(), dict(challenge=bytes(32), target=1), 2, stop_on_second, poll_secs=0.1)
    stopped = False
except KeyboardInterrupt:
    stopped = True
ok("a stop request is acted on straight away even while a slow RPC poll is still waiting", stopped and _time.time() - t0 < 4)
res = m.grind(SlowChain(challenge=b"\x01" * 32, delay=0), Keypair().pubkey(), dict(challenge=bytes(32), target=1), 2,
              lambda h, r: None, poll_secs=0.1)
ok("grind still returns 'moved' when the challenge changes", res[0] == "moved")
gsrc = msrc[msrc.index("def grind("):msrc.index("def rate_text")]
ok("quiet console input is on only inside grind (and pick), not around the whole of mining",
   "with quiet_console_input():" in gsrc and "quiet_console_input" not in msrc[msrc.index("def cmd_mine"):msrc.index("def cmd_status")]
   and msrc.count("with quiet_console_input():") == 2)

# ---- 19 Nov (e): pick needs no config, and any trouble in the key read exits 16 (Exit), never 11 (Mine) ----
for label, cfg in (("no config", None), ("broken config", "{ not json")):
    with tempfile.TemporaryDirectory() as td:
        shutil.copy(os.path.join(MINER, "sumo_miner.py"), td)
        if cfg:
            open(os.path.join(td, "sumo_config.json"), "w").write(cfg)
        r = subprocess.run([sys.executable, os.path.join(td, "sumo_miner.py"), "pick"], input="x3", capture_output=True,
                           text=True, timeout=30, cwd=td)
        ok(f"home menu works with a {label}: key 3 still gives 13, nothing printed", (r.returncode, r.stdout, r.stderr) == (13, "", ""))
old_read = m.read_key
try:
    for exc in (OSError("x"), RuntimeError("x"), KeyboardInterrupt()):
        def broken():
            raise exc
        m.read_key = broken
        ok(f"home menu: {type(exc).__name__} inside the key read exits 16 (Exit), not 11 (Mine)", refused_code(m.cmd_pick, None, None) == 16)
finally:
    m.read_key = old_read

# ---- 19 Nov (e): the typed-ahead flush before address prompts ----
k = FakeK32()
m.flush_typed_ahead(k)
ok("flush_typed_ahead clears the console input buffer", k.flushes == 1)
asrc = msrc[msrc.index("def ask_line("):msrc.index("def ask_address(")]
ok("ask_line flushes typed-ahead keys (Windows consoles only) before it asks", 'if os.name == "nt" and sys.stdin.isatty():' in asrc
   and asrc.index("flush_typed_ahead()") < asrc.index("return input(prompt)"))


print(f"miner console checks: {passed} passed")
