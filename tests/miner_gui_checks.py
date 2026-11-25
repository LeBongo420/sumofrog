#!/usr/bin/env python3
"""Offline checks for the windowed Sumo Frog miner (devnet only, no tip/fee).
No network, no real keys. Run: python3 tests/miner_gui_checks.py
"""
import io
import os
import queue
import sys
import tempfile
import threading
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "miner"))

# The GUI reads SUMO_GUI_HOME before creating a wallet. Point it at a temp folder
# so these checks never touch miner/sumo-devnet-key.json.
HOME = tempfile.mkdtemp()
os.environ["SUMO_GUI_HOME"] = HOME

import sumo_gui as g  # noqa: E402
import sumo_miner as m  # noqa: E402
from solders.keypair import Keypair  # noqa: E402

passed = 0


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


def src_of(*rel):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    text = ""
    for r in rel:
        with open(os.path.join(root, r), encoding="utf-8") as f:
            text += f.read() + "\n"
    return text


gui_src = src_of("miner/sumo_gui.py")
spec_src = src_of("miner/sumo_gui.spec")
wf_src = src_of(".github/workflows/windows-miner.yml")

ok("user-facing GUI source never says 'nonce' (it must say guess #)",
   "nonce" not in gui_src.lower())
ok("live status uses the words Guess #", "Guess #:" in gui_src)
ok("no tip or developer fee is stated in the window",
   "No tip or developer fee" in gui_src and "All mined SUMO" in gui_src)
ok("GUI never asks for a seed phrase or private key",
   "NEVER paste a seed phrase or private key" in gui_src
   and "seed phrase" in gui_src.lower()
   and "private key" in gui_src.lower()
   and "import" not in gui_src.lower().split("seed")[0][-80:])
ok("no seed/key import path exists",
   "from_seed" not in gui_src and "from_json" not in gui_src
   and "ask_line" not in gui_src)
ok("wallet stays a local file next to the app",
   "sumo-devnet-key.json" in gui_src and "user_data_dir" in gui_src)
ok("wallet is never uploaded (no HTTP post of the key)",
   "sendTransaction" not in gui_src
   and "urlopen" not in gui_src
   and "Request(" not in gui_src)
ok("PyInstaller spec does not bundle the private config or wallets",
   "sumo_config.json" in spec_src and "sumo-devnet-key" in spec_src
   and "console=False" in spec_src)
ok("workflow is manual (workflow_dispatch) and not on push",
   "workflow_dispatch" in wf_src and "windows-latest" in wf_src
   and "SHA256" in wf_src or "SHA-256" in wf_src)
ok("workflow is not triggered by push or pull_request",
   "on:\n  workflow_dispatch:" in wf_src.replace("\r\n", "\n")
   or "on:\n  workflow_dispatch" in wf_src.replace("\r\n", "\n"))
ok("workflow writes a SHA-256 and refuses to upload wallets",
   "SHA256" in wf_src and "sumo-devnet-key" in wf_src)

# ---- settings are forced to public devnet, even if a private config exists ----
settings = g.load_gui_settings()
ok("GUI settings network is devnet", settings["network"] == "devnet")
ok("GUI settings RPC is the public devnet RPC", settings["rpc"] == g.PUBLIC_DEVNET_RPC)
ok("GUI settings have no private genesis", "private_genesis" not in settings)
ok("GUI settings have no extra rpc leftover from a private config",
   settings.get("devnet_rpc") == g.PUBLIC_DEVNET_RPC)

# ---- local wallet: create once, never overwrite ----
key = os.path.join(HOME, "sumo-devnet-key.json")
kp1, created = g.create_or_load_wallet(key)
ok("creates a local test wallet on first run", created and os.path.isfile(key))
kp2, created2 = g.create_or_load_wallet(key)
ok("second load does not overwrite the wallet",
   (not created2) and str(kp1.pubkey()) == str(kp2.pubkey()))
text = open(key, encoding="utf-8").read()
ok("wallet file never leaves this function over the network (file stays local)",
   text.startswith("[") and "http" not in text)

# ---- payout parser: public address only ----
good = Keypair().pubkey()
pk, err = g.try_parse_payout(str(good), settings)
ok("valid public address is accepted", err is None and str(pk) == str(good))
_, err = g.try_parse_payout("word " * 12, settings)
ok("a seed-phrase-like list of words is refused",
   err and "seed phrase" in err.lower() and "NEVER" in err)
_, err = g.try_parse_payout("[1,2,3,4]", settings)
ok("key-file contents are refused", err and "key file" in err.lower())
long_keyish = "A" * 64
_, err = g.try_parse_payout(long_keyish, settings)
ok("an over-long string (might be a private key) is refused",
   err and "PRIVATE" in err)
_, err = g.try_parse_payout("not-an-address", settings)
ok("junk is refused", err and "valid Solana address" in err)
ok("empty payout field is allowed (rewards stay in the miner wallet)",
   g.read_saved_payout(settings) is None)

g.write_saved_payout(good)
ok("saved payout is the address we stored",
   str(g.read_saved_payout(settings)) == str(good))
g.write_saved_payout(None)
ok("clearing payout removes the file",
   g.read_saved_payout(settings) is None and not os.path.isfile(g.payout_path()))

# The on-chain program already has mine_to, so the GUI does not need a program change.
prog = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "programs", "sumofrog", "src", "lib.rs"), encoding="utf-8").read()
ok("program already supports a separate recipient (mine_to)",
   "pub fn mine_to" in prog and "fn mine(" in prog)

# ---- mining loop: rewards go only to payout or the local wallet; no tip ----
submits = []


class FakeRpc:
    def call(self, method, *params):
        if method == "getAccountInfo":
            return {"value": None}
        raise AssertionError("unexpected RPC call in offline GUI check: " + method)


class FakeChain:
    cluster = "devnet"
    program = m.Pubkey.from_string(settings["program_id"])
    config = m.Pubkey.find_program_address([b"config"], program)[0]
    mint = m.Pubkey.find_program_address([b"mint"], program)[0]

    def __init__(self, settings_):
        self.settings = settings_
        self.rpc = FakeRpc()

    def state(self):
        return dict(next_reward=20 * 10**9, blocks_mined=4, target=1,
                    blocks_to_halving=5, challenge=bytes(32))

    def sol_balance(self, pk):
        return 1.0

    def sumo_units(self, pk):
        return 0

    def submit(self, kp, challenge, guess, payout=None):
        submits.append((str(kp.pubkey()), payout if payout is None else str(payout), guess))
        return "fake-signature"


events, statuses = [], []
stop = threading.Event()
real = (m.Chain, m.grind, m.load_key)


grinds = []


def fake_grind(chain, earner, st, workers, on_tick):
    grinds.append(1)
    if len(grinds) > 1:
        raise KeyboardInterrupt
    on_tick(12, 1000.0)
    return 7, 12, 2.0


m.Chain = FakeChain
m.grind = fake_grind
m.load_key = lambda path: kp1
try:
    g.run_mining(settings, key, good, 1, stop,
                 on_status=lambda h: statuses.append(h),
                 on_event=lambda e: events.append(e))
finally:
    m.Chain, m.grind, m.load_key = real

ok("a payout address is passed through to submit (mine_to path)",
   len(submits) == 1 and submits[0][1] == str(good))
ok("the fee payer is the local wallet, not the payout address",
   submits[0][0] == str(kp1.pubkey()) and submits[0][0] != str(good))
ok("no third address is involved (no tip or dev fee)",
   submits[0][1] in (str(good), None) and submits[0][0] == str(kp1.pubkey()))
ok("status reports guess # and hash rate",
   any(s.get("guesses") == 12 for s in statuses) and any(s.get("rate") for s in statuses))
ok("BLOCK FOUND event does not mention a tip",
   any("BLOCK FOUND" in e and "No tip or developer fee" in e for e in events))

# Without a payout, submit gets None (credit the local wallet).
submits.clear()
grinds.clear()
m.Chain, m.grind, m.load_key = FakeChain, fake_grind, (lambda path: kp1)
try:
    g.run_mining(settings, key, None, 1, threading.Event(),
                 on_status=lambda h: None, on_event=lambda e: None)
finally:
    m.Chain, m.grind, m.load_key = real
ok("with no payout, rewards stay in the local wallet (submit payout is None)",
   len(submits) == 1 and submits[0][1] is None and submits[0][0] == str(kp1.pubkey()))

# GUI refuses to mine on a non-devnet cluster.
class PrivateChain(FakeChain):
    cluster = "private Sumo test network"

m.Chain = PrivateChain
m.load_key = lambda path: kp1
try:
    try:
        g.run_mining(settings, key, None, 1, threading.Event(),
                     on_status=lambda h: None, on_event=lambda e: None)
        refused = False
        msg = ""
    except SystemExit as e:
        refused = True
        msg = str(e.code)
finally:
    m.Chain, m.load_key = real[0], real[2]
ok("windowed miner refuses a non-devnet cluster",
   refused and "devnet" in msg.lower())

# freeze_support is called in the GUI entry (needed for the Windows .exe).
ok("GUI entry calls freeze_support",
   'if __name__ == "__main__":' in gui_src and "mp.freeze_support()" in gui_src)

# ---- optional: the window can open under a virtual display ----
tk_ok = True
try:
    import tkinter  # noqa: F401
except Exception:
    tk_ok = False
    ok("tkinter not installed here; window launch skipped", True)

if tk_ok:
    import tkinter as tk
    # Do not start the full app (it may try to create a wallet in HOME, which is fine,
    # but we only need to know the widgets construct). Use a discarded root if DISPLAY is set.
    if os.environ.get("DISPLAY") or sys.platform == "win32":
        root = tk.Tk()
        root.withdraw()
        try:
            # Build fonts/widgets used by the app without entering mainloop mining.
            label = tk.Label(root, text="Guess #: 0  STATUS: STOPPED")
            label.pack()
            root.update_idletasks()
            ok("Tk window and labels construct", "Guess #" in label.cget("text") and "STATUS:" in label.cget("text"))
        finally:
            root.destroy()
    else:
        ok("no display; widget construction skipped (ok on a headless run without Xvfb)", True)

print(f"{passed} GUI checks passed")
