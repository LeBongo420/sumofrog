#!/usr/bin/env python3
"""Offline checks for the miner's address and network guards (Ribbit's 2 Nov 2026 review).
No network, no keys: a fake RPC answers. Run: python3 tests/miner_checks.py"""
import os
import shutil
import stat
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "miner"))
import sumo_miner as m  # noqa: E402
from solders.keypair import Keypair  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402


def load_test_settings():
    """Load miner settings, falling back to the example config in a temp folder
    when sumo_config.json is missing (a fresh checkout). Honour SUMO_CONFIG if set."""
    here = os.path.dirname(os.path.abspath(m.__file__))
    override = os.environ.get("SUMO_CONFIG")
    cfg = override if override else os.path.join(here, "sumo_config.json")
    example = os.path.join(here, "sumo_config.example.json")
    if os.path.isfile(cfg):
        work = os.path.dirname(os.path.abspath(cfg))
        name = os.path.basename(cfg)
        if name != "sumo_config.json":
            tmp = tempfile.mkdtemp()
            shutil.copy(cfg, os.path.join(tmp, "sumo_config.json"))
            work = tmp
    else:
        if override:
            raise SystemExit(f"SUMO_CONFIG not found: {cfg}")
        if not os.path.isfile(example):
            raise SystemExit("miner checks need miner/sumo_config.example.json")
        work = tempfile.mkdtemp()
        shutil.copy(example, os.path.join(work, "sumo_config.json"))
    old = m.HERE
    m.HERE = work
    try:
        return m.load_settings()
    finally:
        m.HERE = old


S = load_test_settings()
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

# ---- apply_network: refuse bad types; warn (do not stop) on a genesis mismatch ----
base = {k: S[k] for k in ("program_id", "config", "mint", "rpc", "private_genesis", "devnet_rpc") if k in S}


def net_settings(**kw):
    t = dict(base)
    t.update(kw)
    return t


ok("missing network defaults to private", m.apply_network(net_settings())["network"] == "private")
ok("private kept", m.apply_network(net_settings(network="private"))["network"] == "private")
dev = m.apply_network(net_settings(network="devnet"))
ok("devnet selects devnet_rpc", dev["network"] == "devnet" and dev["rpc"] == base["devnet_rpc"])
for bad in (False, 0, 1, [], {}, True):
    msg = refused(m.apply_network, net_settings(network=bad)).lower()
    ok(f"non-string network {bad!r} refused", "network" in msg and "private" in msg and "devnet" in msg)
ok("empty network refused", "network" in refused(m.apply_network, net_settings(network="")).lower())
ok("unknown network refused", "Unknown network" in refused(m.apply_network, net_settings(network="mainnet")))
ok("non-string devnet_rpc refused", "devnet_rpc" in refused(m.apply_network, net_settings(devnet_rpc=443)).lower())
ok("empty devnet_rpc refused", "devnet_rpc" in refused(m.apply_network, net_settings(devnet_rpc="")).lower())
missing = net_settings(network="devnet")
missing.pop("devnet_rpc")
ok("missing devnet_rpc defaults to public devnet",
   m.apply_network(missing)["rpc"] == "https://api.devnet.solana.com")


def check_shown(genesis, url, settings):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        label = m.check_devnet(FakeRpc(genesis), url, settings)
    return label, out.getvalue()


priv = m.apply_network(net_settings(network="private"))
label, shown = check_shown(S["private_genesis"], S["rpc"], priv)
ok("private + matching genesis: no warning", label == "private Sumo test network" and "Warning" not in shown)
label, shown = check_shown(m.DEVNET_GENESIS, "https://api.devnet.solana.com", priv)
ok("private label on a devnet chain: warns, still runs",
   label == "devnet" and "Warning" in shown and "devnet" in shown)
# network=devnet but the chain is the private genesis (e.g. devnet_rpc pointed at the private gateway)
s = dict(base, network="devnet", devnet_rpc="https://example-for-test.invalid")
s = m.apply_network(s)
# Use the shipped private http link with the private genesis so check_devnet accepts it,
# after apply_network has labelled the settings as devnet.
s["_shipped_rpc"] = S["rpc"]
label, shown = check_shown(S["private_genesis"], S["rpc"], s)
ok("devnet label on the private chain: warns, still runs",
   label == "private Sumo test network" and "Warning" in shown and "private" in shown)
label, shown = check_shown(LOCAL_GENESIS, "http://127.0.0.1:8899", priv)
ok("private label on localhost: warns, still runs",
   label == "local test validator" and "Warning" in shown)


# ---- 19 Nov: a refused address asks again (set-payout and withdraw) instead of dumping back to the menu ----
import builtins  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402


class Tty:
    def isatty(self):
        return True


def scripted(answers, fn, *a):
    """Run fn with ask_line (and input) answering from `answers`; returns (result, printed text, answers left)."""
    left, out, old = list(answers), io.StringIO(), (m.ask_line, builtins.input, sys.stdin)

    def nxt(prompt=""):
        out.write("<" + prompt + ">")
        if not left:
            raise EOFError
        return left.pop(0)
    m.ask_line, builtins.input, sys.stdin = nxt, nxt, Tty()
    try:
        with contextlib.redirect_stdout(out):
            try:
                res = fn(*a)
            except SystemExit as e:
                res = ("EXIT", str(e.code))
    finally:
        m.ask_line, builtins.input, sys.stdin = old
    return res, out.getvalue(), left


ISSUE = ("SUMO", "x" * 50, "word " * 12, "")
res, shown, left = scripted([*ISSUE, "back"], m.ask_address, "ask: ", lambda t: m.parse_payout(t, S))
ok("ask_address: bad answers (short text, too long, seed words, empty) each ask again; back gives None",
   res is None and left == [] and shown.count("Try again, or type  back  to cancel.") == 3
   and "isn't a valid Solana address" in shown and "Paste an address, or type  back" in shown)
res, shown, left = scripted(["SUMO", " " + str(WALLET) + " ", "unused"], m.ask_address, "ask: ", lambda t: m.parse_payout(t, S))
ok("ask_address: after a bad one the right address is accepted (spaces trimmed) and nothing more is asked",
   res == WALLET and left == ["unused"])
ok("ask_address: end of input (no keyboard) stops with a plain message instead of looping",
   scripted([], lambda: m.ask_address("ask: ", lambda t: t))[0][0] == "EXIT")

with tempfile.TemporaryDirectory() as td:
    old_file, old_chain = m.PAYOUT_FILE, m.Chain
    m.PAYOUT_FILE = os.path.join(td, "payout-address.txt")

    def no_net(settings):
        raise OSError("offline")
    m.Chain = no_net
    sp_args = types.SimpleNamespace(address=None, yes=True)
    try:
        res, shown, left = scripted(["SUMO", str(WALLET)], m.cmd_set_payout, sp_args, S)
        ok("set-payout: 'SUMO' is refused, asked again, and the right address is then saved",
           res is None and left == [] and "Nothing was saved." in shown
           and open(m.PAYOUT_FILE).read().strip() == str(WALLET))
        res, shown, left = scripted(["SUMO", "back"], m.cmd_set_payout, sp_args, S)
        ok("set-payout: 'back' cancels cleanly and leaves the saved address alone",
           res == ("EXIT", "Cancelled. Nothing was saved.") and open(m.PAYOUT_FILE).read().strip() == str(WALLET))
        res, shown, left = scripted(["none"], m.cmd_set_payout, sp_args, S)
        ok("set-payout: 'none' still removes the payout address", not os.path.exists(m.PAYOUT_FILE) and "removed" in shown)
        res, shown, left = scripted([str(PROGRAM), str(WALLET)], m.cmd_set_payout, sp_args, S)
        ok("set-payout: a program address is refused and asked again too",
           "Sumo Frog program address" in shown and open(m.PAYOUT_FILE).read().strip() == str(WALLET))
        ok("set-payout: an address given on the command line is still refused outright (no prompt)",
           "isn't a valid" in refused(m.cmd_set_payout, types.SimpleNamespace(address="SUMO", yes=True), S))
    finally:
        m.PAYOUT_FILE, m.Chain = old_file, old_chain

miner_kp = Keypair()
fake_chain = types.SimpleNamespace(program=PROGRAM, config=CONFIG, mint=MINT)
old_acct, old_saved = m._account, m.saved_payout
m._account = lambda chain, pk: None
wd_args = types.SimpleNamespace(address=None, yes=False)
try:
    m.saved_payout = lambda settings: None
    res, shown, left = scripted(["SUMO", str(miner_kp.pubkey()), str(WALLET)], m.withdraw_destination, wd_args, S, miner_kp, fake_chain)
    ok("withdraw, no payout saved: no 'Enter = payout address', one prompt that asks again until it's a valid wallet",
       res == (WALLET, None) and left == [] and "No payout address saved yet" in shown and "Enter =" not in shown
       and "isn't a valid" in shown and "miner's own wallet" in shown and shown.count("<Paste your wallet's PUBLIC address to send to") == 3)
    res, shown, left = scripted([""], m.withdraw_destination, wd_args, S, miner_kp, fake_chain)
    ok("withdraw, no payout saved: an empty answer asks again (it is not read as 'no address given')",
       left == [] and res == ("EXIT", "No address given.") and "Paste an address, or type  back" in shown)
    res, shown, left = scripted(["back"], m.withdraw_destination, wd_args, S, miner_kp, fake_chain)
    ok("withdraw: 'back' cancels with Nothing was sent", res == ("EXIT", "Cancelled. Nothing was sent."))
    m.saved_payout = lambda settings: WALLET
    res, shown, left = scripted(["y"], m.withdraw_destination, wd_args, S, miner_kp, fake_chain)
    ok("withdraw, payout saved: shows it and 'y' uses it", res == (WALLET, None) and left == [])
    res, shown, left = scripted(["n", "SUMO", "back"], m.withdraw_destination, wd_args, S, miner_kp, fake_chain)
    ok("withdraw, payout saved but 'n': asks for another address, again on a bad one",
       res == ("EXIT", "Cancelled. Nothing was sent.") and "isn't a valid" in shown)
    ok("withdraw: an address given on the command line is still refused outright",
       "isn't a valid" in refused(m.withdraw_destination, types.SimpleNamespace(address="SUMO", yes=True), S, miner_kp, fake_chain))
finally:
    m._account, m.saved_payout = old_acct, old_saved

# 19 Nov (e): a refusal of the network itself stops set-payout before any question; the account-type check is used by Withdraw
with tempfile.TemporaryDirectory() as td:
    old_file, old_chain = m.PAYOUT_FILE, m.Chain
    m.PAYOUT_FILE = os.path.join(td, "payout-address.txt")

    def mainnet(settings):
        sys.exit("!! This is MAINNET. Test networks only.")
    m.Chain = mainnet
    try:
        res, shown, left = scripted([str(WALLET)], m.cmd_set_payout, types.SimpleNamespace(address=None, yes=True), S)
        ok("set-payout: a mainnet / bad-link refusal stops the command at once: no question, no 'Try again', nothing saved",
           res == ("EXIT", "!! This is MAINNET. Test networks only.") and left == [str(WALLET)]
           and shown == "Checking the network...\n"
           and not os.path.exists(m.PAYOUT_FILE))
    finally:
        m.PAYOUT_FILE, m.Chain = old_file, old_chain

# 20 Nov (f): a progress line before the first question; Ctrl+C while a Withdraw is being sent says so
with tempfile.TemporaryDirectory() as td:
    old_file, old_chain = m.PAYOUT_FILE, m.Chain
    m.PAYOUT_FILE = os.path.join(td, "payout-address.txt")

    def offline(settings):
        raise OSError("offline")
    m.Chain = offline
    try:
        res, shown, left = scripted(["back"], m.cmd_set_payout, types.SimpleNamespace(address=None, yes=True), S)
        ok("set-payout: 'Checking the network...' is printed before the first question",
           shown.startswith("Checking the network...\n") and shown.index("Checking the network") < shown.index("<Paste"))
    finally:
        m.PAYOUT_FILE, m.Chain = old_file, old_chain


class WdRpc:
    def call(self, method, *params):
        return {"getBalance": {"value": 5 * 10**9}, "getMinimumBalanceForRentExemption": 890880}[method]


class WdChain:
    cluster, unencrypted, program, config, mint = "devnet", False, PROGRAM, CONFIG, MINT
    rpc = WdRpc()

    def ata(self, pk):
        return pk

    def sumo_units(self, pk):
        return 0

    def sol_balance(self, pk):
        return 0.0


saved = (m.Chain, m.load_key, m.withdraw_destination, m._account, m._fee, m._send)
m.Chain, m.load_key = (lambda settings: WdChain()), (lambda path: miner_kp)
m.withdraw_destination = lambda args, settings, kp, chain: (WALLET, None)
m._account, m._fee = (lambda chain, pk: None), (lambda chain, kp, ixs: 5000)


def interrupted_send(chain, kp, ixs):
    raise KeyboardInterrupt
m._send = interrupted_send
try:
    res, shown, left = scripted([], m.cmd_withdraw, types.SimpleNamespace(
        address=None, yes=True, sumo=False, keypair="x", plain=True), S)
    ok("withdraw: Ctrl+C while the send is in flight says it may still go through and to check the balance (not 'Nothing is lost')",
       res[0] == "EXIT" and "Stopped while sending. It may still go through. Check balance" in res[1]
       and "Nothing is lost" not in res[1])
finally:
    m.Chain, m.load_key, m.withdraw_destination, m._account, m._fee, m._send = saved

token_owned = Keypair().pubkey()
m._account = lambda chain, pk: ({"executable": False, "owner": str(m.TOKEN_PROGRAM), "lamports": 1}
                                if pk == token_owned else None)
m.saved_payout = lambda settings: None
try:
    res, shown, left = scripted([str(token_owned), str(WALLET)], m.withdraw_destination, wd_args, S, miner_kp, fake_chain)
    ok("withdraw: a destination that is a token or program account (found by the network check) is refused, then the next address works",
       res == (WALLET, None) and "belongs to a program or token account" in shown and left == [])
finally:
    m._account, m.saved_payout = old_acct, old_saved

print(f"miner checks: {passed} passed")
