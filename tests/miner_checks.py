#!/usr/bin/env python3
"""Offline checks for the miner's address and network guards (Ribbit's 2 Nov 2026 review).
No network, no keys: a fake RPC answers. Run: python3 tests/miner_checks.py"""
import os
import stat
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "miner"))
import sumo_miner as m  # noqa: E402
from solders.keypair import Keypair  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402

S = m.load_settings()
PROGRAM = Pubkey.from_string(S["program_id"])
CONFIG = Pubkey.find_program_address([b"config"], PROGRAM)[0]
MINT = Pubkey.find_program_address([b"mint"], PROGRAM)[0]
WALLET = Keypair().pubkey()
ATA = Pubkey.find_program_address([bytes(WALLET), bytes(m.TOKEN_PROGRAM), bytes(MINT)], m.ATA_PROGRAM)[0]
passed = 0


def refused(fn, *a):
    try:
        fn(*a)
    except SystemExit as e:
        return str(e.code)
    raise AssertionError(f"not refused: {fn.__name__}{a!r}")


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


class FakeRpc:
    def __init__(self, genesis, accounts=None):
        self.genesis, self.accounts, self.calls = genesis, accounts or {}, 0

    def call(self, method, *params):
        self.calls += 1
        if method == "getGenesisHash":
            return self.genesis
        if method == "getAccountInfo":
            return {"value": self.accounts.get(params[0])}
        raise AssertionError(method)


# ---- payout addresses: every path goes through parse_payout ----
ok("plain wallet accepted", m.parse_payout(str(WALLET), S) == WALLET)
for bad in (PROGRAM, CONFIG, MINT):
    ok(f"sumo address refused {bad}", "Sumo Frog program address" in refused(m.parse_payout, str(bad), S))
ok("token account (ATA, off-curve) refused", "program-controlled" in refused(m.parse_payout, str(ATA), S))
ok("system program refused", "system address" in refused(m.parse_payout, str(m.SYSTEM_PROGRAM), S))
ok("seed phrase refused", "seed phrase" in refused(m.parse_payout, "word " * 12, S))

# config-file "payout" and payout-address.txt both go through saved_payout -> parse_payout
m.PAYOUT_FILE = os.path.join(tempfile.mkdtemp(), "payout-address.txt")
ok("config payout: ATA refused", "Set payout address" in refused(m.saved_payout, dict(S, payout=str(ATA))))
ok("config payout: mint refused", "program address" in refused(m.saved_payout, dict(S, payout=str(MINT))))
ok("config payout: wallet ok", m.saved_payout(dict(S, payout=str(WALLET))) == WALLET)
with open(m.PAYOUT_FILE, "w") as f:
    f.write(str(CONFIG) + "\n")
ok("payout file: config refused", "program address" in refused(m.saved_payout, S))
os.remove(m.PAYOUT_FILE)

# with a network: an on-curve address that's a token or program account is refused
tok_owner = Keypair().pubkey()  # a non-ATA token account has an ordinary on-curve address
chain = types.SimpleNamespace(rpc=FakeRpc(S["private_genesis"], {
    str(tok_owner): {"owner": str(m.TOKEN_PROGRAM), "executable": False},
    str(WALLET): {"owner": str(m.SYSTEM_PROGRAM), "executable": False},
}))
ok("token account (on-curve) refused", "token account" in refused(m.check_wallet_account, chain, tok_owner, "x"))
ok("existing wallet ok", m.check_wallet_account(chain, WALLET, "x")["owner"] == str(m.SYSTEM_PROGRAM))
ok("new wallet ok", m.check_wallet_account(chain, Keypair().pubkey(), "x") is None)

# ---- network: exact host match and https ----
for u in ("http://localhost:8899", "http://127.0.0.1:8899", "http://[::1]:8899", "https://LOCALHOST/"):
    ok(f"local {u}", m.is_local_url(u))
for u in ("http://localhost.example.com", "https://x.com/?localhost", "http://127.0.0.1.evil.io",
          "https://evil.io/127.0.0.1", "http://user@evil.io#localhost"):
    ok(f"not local {u}", not m.is_local_url(u))

LOCAL_GENESIS = "11111111111111111111111111111111"
ok("localhost http ok", m.check_devnet(FakeRpc(LOCAL_GENESIS), "http://127.0.0.1:8899", S) == "local test validator")
for u in ("http://localhost.example.com", "https://x.com/?localhost", "https://evil.io/127.0.0.1"):
    refused(m.check_devnet, FakeRpc(LOCAL_GENESIS), u, S)
    passed += 1
ok("devnet https ok", m.check_devnet(FakeRpc(m.DEVNET_GENESIS), "https://api.devnet.solana.com", S) == "devnet")
r = FakeRpc(m.DEVNET_GENESIS)
ok("devnet over plain http refused", "encrypted" in refused(m.check_devnet, r, "http://api.devnet.solana.com", S))
ok("...before any network call", r.calls == 0)
ok("file:// refused", "https" in refused(m.check_devnet, FakeRpc(LOCAL_GENESIS), "file:///etc/passwd", S))
ok("mainnet refused", "MAINNET" in refused(m.check_devnet, FakeRpc(m.MAINNET_GENESIS), "https://api.mainnet-beta.solana.com", S))
# the shipped private network link (plain http) keeps working when the genesis matches
ok("shipped private http ok", m.check_devnet(FakeRpc(S["private_genesis"]), S["rpc"], S) == "private Sumo test network")
ok("shipped http link, wrong network refused", "isn't the private" in refused(
    m.check_devnet, FakeRpc(m.DEVNET_GENESIS), S["rpc"], S))
ok("other http link refused even if it claims the private genesis", "encrypted" in refused(
    m.check_devnet, FakeRpc(S["private_genesis"]), "http://other.example:8080", S))

# ---- private http link: plain warning at startup and before withdraw (Josh, 2 Nov 2026) ----
import contextlib  # noqa: E402
import io  # noqa: E402

NOTE = ("Note: the private test link isn't encrypted. Fine for test coins with no value. "
        "Always check the payout address you type.")
ok("exact wording", m.HTTP_NOTE == NOTE)


def make_chain(url, genesis):
    orig = m.Rpc
    m.Rpc = lambda u: FakeRpc(genesis)
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            c = m.Chain(dict(S, rpc=url))
        return c, out.getvalue()
    finally:
        m.Rpc = orig


c, shown = make_chain(S["rpc"], S["private_genesis"])
ok("private http link: flagged", c.unencrypted)
ok("private http link: note shown at startup", NOTE in shown)
c, shown = make_chain("http://127.0.0.1:8899", LOCAL_GENESIS)
ok("localhost: no note", not c.unencrypted and NOTE not in shown)
c, shown = make_chain("https://api.devnet.solana.com", m.DEVNET_GENESIS)
ok("https devnet: no note", not c.unencrypted and NOTE not in shown)
src = open(m.__file__).read()
w = src[src.index("def cmd_withdraw"):src.index("def _worker")]
ok("withdraw shows the note before asking to send",
   "print(HTTP_NOTE)" in w and w.index("print(HTTP_NOTE)") < w.index('input("Send now?'))
mn = src[src.index("def cmd_mine"):src.index("def cmd_status")]
ok("mine shows the note on the mining screen (plain: full event; colour: pinned footer)",
   "scr.event(HTTP_NOTE)" in mn and "scr.footer_note = HTTP_NOTE_SHORT" in mn)

# ---- colour mining screen: the short note is pinned, whole, at every width (Ribbit, 2 Nov c) ----
import re  # noqa: E402
import shutil  # noqa: E402

SHORT = "Note: test link isn't encrypted. Check your payout address."
ok("short note wording", m.HTTP_NOTE_SHORT == SHORT and len(SHORT) <= 76)
HUD = dict(block=51, rate="21.00 MH/S", guesses=0, diff="24.0 BITS", reward="20 SUMO", mined=0,
           balance="0", halving=525_550, pays_to="Abcd...wxyz", reward_won="")
if m.sumo_art is not None:
    orig_size = shutil.get_terminal_size
    try:
        for cols in (80, 120, 200):
            shutil.get_terminal_size = lambda *_a, c=cols: os.terminal_size((c, 40))
            scr = m.Screen(True)
            scr.footer_note = SHORT
            for e in ("a", "Block #50 went to another frog.", "Another miner got there first.", "b"):
                scr.events = (scr.events + [e])[-3:]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                scr.draw(HUD)
            text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out.getvalue())
            ok(f"colour screen at {cols} columns: whole short note still shown after more events", SHORT in text)
    finally:
        shutil.get_terminal_size = orig_size
else:
    ok("colour screen check skipped: no sumo_art", True)

# ---- block-found time: tenths under 10 s, not "0s" for a sub-second block ----
ok("block time display", (m.secs_text(0.37), m.secs_text(4.04), m.secs_text(9.94), m.secs_text(12.3))
   == ("0.4s", "4.0s", "9.9s", "12s"))

# ---- new-key files are owner-only ----
d = tempfile.mkdtemp()
key = os.path.join(d, "k.json")
m.cmd_new_key(types.SimpleNamespace(keypair=key), S)
mode = stat.S_IMODE(os.stat(key).st_mode)
ok("new key is 600", os.name == "nt" or mode == 0o600)
ok("new-key won't overwrite", "already exists" in refused(m.cmd_new_key, types.SimpleNamespace(keypair=key), S))
os.remove(key)

print(f"miner checks: {passed} passed")
