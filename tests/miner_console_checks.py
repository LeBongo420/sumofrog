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
ok("Ctrl+C stays on (processed input) and extended flags set so quickedit really is off",
   inside & PROCESSED and inside & EXTENDED)
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
for fname in ("sumo_miner.py", "sumo_art.py"):
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

print(f"miner console checks: {passed} passed")
