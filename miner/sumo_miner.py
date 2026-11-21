#!/usr/bin/env python3
"""Sumo Frog ($SUMO) CPU miner -- Solana test networks ONLY (private Sumo network / devnet), worthless toy token.

Usage:
  py sumo_miner.py new-key                  make a test-network-only fee wallet (sumo-devnet-key.json)
  py sumo_miner.py faucet                   get 1 free test SOL for fees (private Sumo network)
  py sumo_miner.py mine [--blocks N] [--workers N] [--payout ADDRESS] [--plain]
  py sumo_miner.py set-payout ADDRESS       send future rewards to your own wallet's PUBLIC address
  py sumo_miner.py set-payout none          go back to keeping rewards in the miner's own wallet
  py sumo_miner.py withdraw [ADDRESS] [--sumo] [--yes]
                                            send the miner wallet's leftover test SOL (and, with --sumo,
                                            its SUMO) to a PUBLIC address; default: your payout address
  py sumo_miner.py balance                  show your SUMO and test SOL
  py sumo_miner.py status                   show blocks, difficulty, reward, supply

How it works: the miner tries guess numbers (guess #1, #2, ...) and hashes
sha256(challenge || reward address || guess #). When the first 8 bytes, read as a number,
are <= the on-chain target, that guess wins the block. The miner sends it to the Sumo Frog
program, which checks it and mints the reward to the reward address.

The reward address is the miner's own wallet, or the payout address you set. A payout address is
a PUBLIC address only. Never type a seed phrase or private key into this miner (or anything else).
"""
import argparse
import atexit
import base64
import hashlib
import json
import multiprocessing as mp
import os
import queue
import re
import secrets
import shutil
import signal
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "v0.6.4"
DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"
MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
MINE_DISC = bytes([59, 22, 178, 213, 139, 197, 160, 196])        # mine(challenge, guess)
MINE_TO_DISC = bytes([190, 115, 82, 206, 226, 21, 147, 187])     # mine_to(challenge, guess), pays `payout`
CONFIG_DISC = bytes([155, 12, 170, 224, 30, 250, 204, 130])
ERRORS = {6000: "BadParams", 6001: "NotUpgradeAuthority", 6002: "StaleChallenge",
          6003: "InsufficientWork", 6004: "SupplyExhausted", 6005: "MathOverflow"}
UNIT = 10 ** 9
PAYOUT_FILE = os.path.join(HERE, "payout-address.txt")

for _stream in (sys.stdout, sys.stderr):
    try:  # never crash on a console that can't print a character: replace it instead
        _stream.reconfigure(errors="replace")
    except Exception:
        pass


# ======================= look (v4: 8-bit synthwave Japan) =======================
# Nothing in this section changes mining, hashing, RPC or the network guard.

def enable_colour(force_plain=False):
    """True if the console can show ANSI colours and half-block pixels. Windows 10+ needs
    'virtual terminal' mode switched on first (no extra packages: plain ctypes)."""
    if force_plain or os.environ.get("NO_COLOR") or os.environ.get("SUMO_PLAIN"):
        return False
    if not sys.stdout.isatty() and not os.environ.get("SUMO_FORCE_COLOUR"):
        return False
    try:
        "\u2580\u2588".encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if not k32.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            if not k32.SetConsoleMode(h, mode.value | 0x0004):  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                return False
        except Exception:
            return False
    elif os.environ.get("TERM") == "dumb":
        return False
    return True


# ======================= console input guard (Windows) =======================
# Why: a Windows console starts in "QuickEdit" mode with echo, line input and mouse input on.
# Clicking or typing in the mining window can then freeze the console (output blocks until you
# press a key or Enter), and the miner's draw loop sits inside that blocked write, so it stops
# collecting a found block and stops watching for a new challenge. Typed keys also pile up in the
# console's input buffer and get replayed into the .bat file's "pause" afterwards.
# Fix: while mining, switch QuickEdit, mouse, echo and line input OFF, and keep throwing away any
# keys pressed. The old console mode is put back on exit. Plain ctypes, no extras.
# Processed input is off too, so Ctrl+C arrives as an ordinary key (\x03) instead of a signal. The
# miner asks "Stop mining? (y/n)" itself, and cmd.exe never sees a Ctrl+C, so its own "Terminate
# batch job (Y/N)?" question (which only appears after the miner has already stopped) never shows.
_ENABLE_EXTENDED_FLAGS = 0x0080    # needed so that leaving QuickEdit (0x0040) out really turns it off
_STD_INPUT_HANDLE = -10
_input_guard = {"k32": None, "handle": None}


def _kernel32():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetStdHandle.argtypes = [wintypes.DWORD]
    k32.GetStdHandle.restype = wintypes.HANDLE
    k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetConsoleMode.restype = wintypes.BOOL
    k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.SetConsoleMode.restype = wintypes.BOOL
    k32.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]
    k32.FlushConsoleInputBuffer.restype = wintypes.BOOL
    return k32


def flush_console_input():
    """Throw away any keys or mouse clicks waiting in the console's input buffer. Does nothing
    unless quiet_console_input() is active (so never on other systems or when stdin isn't a console)."""
    k32, handle = _input_guard["k32"], _input_guard["handle"]
    if k32 is None:
        return
    try:
        k32.FlushConsoleInputBuffer(handle)
    except Exception:
        pass


def read_key():
    """One key press (waits for it). Arrow and function keys arrive in two parts and give "".
    Off Windows it reads stdin, and the end of stdin counts as Ctrl+C."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()
            return ""
        return ch
    return sys.stdin.read(1) or "\x03"


def pending_keys():
    """All keys typed since the last call, or "" when quiet_console_input() isn't active."""
    if _input_guard["k32"] is None or os.name != "nt":
        return ""
    import msvcrt
    keys = ""
    while msvcrt.kbhit():
        keys += read_key()
    return keys


def stop_requested(scr, hud):
    """Called every tick while mining. If Ctrl+C was pressed, ask "Stop mining?" and wait for y or n
    (mining carries on in the background meanwhile). True = stop."""
    if "\x03" not in pending_keys():
        return False
    scr.event("Stop mining?  Press Y to stop, N to keep mining.")
    scr.draw(hud)
    while True:
        key = read_key().lower()
        if key in ("y", "\x03"):
            return True
        if key in ("n", "\r", "\x1b"):
            scr.event("OK, still mining.")
            scr.draw(hud)
            return False


class quiet_console_input:
    """Context manager: stdin is a real Windows console -> QuickEdit, mouse, echo, line input and
    Ctrl+C-as-a-signal off (Ctrl+C is read as the key \\x03, see stop_requested), keys discarded; the old
    mode is restored on exit, and also at interpreter exit and on Ctrl+Break / window close, so a killed
    miner can't leave the window without Ctrl+C or echo. Anywhere else it does nothing. `k32` lets the
    offline checks pass in a fake kernel32."""

    def __init__(self, k32=None):
        self._k32 = k32
        self._old = self._cb = None

    def __enter__(self):
        import ctypes
        try:
            k32 = self._k32 or (_kernel32() if os.name == "nt" else None)
            if k32 is None:
                return self
            handle = k32.GetStdHandle(_STD_INPUT_HANDLE)
            mode = ctypes.c_uint32()
            if not handle or not k32.GetConsoleMode(handle, ctypes.byref(mode)):
                return self  # stdin is a pipe or file, not a console
            if not k32.SetConsoleMode(handle, _ENABLE_EXTENDED_FLAGS):
                return self
            self._old = mode.value
            _input_guard.update(k32=k32, handle=handle)
            flush_console_input()
            atexit.register(self._restore)
            try:  # Ctrl+Break, closing the window, logoff, shutdown: put the mode back, then let Windows go on
                from ctypes import wintypes
                self._cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)(self._on_console_event)
                k32.SetConsoleCtrlHandler(self._cb, True)
            except Exception:
                self._cb = None
        except Exception:
            self._old = None
            _input_guard.update(k32=None, handle=None)
        return self

    def _restore(self):
        try:
            k32, handle = _input_guard["k32"], _input_guard["handle"]
            if self._old is not None and k32 is not None:
                k32.SetConsoleMode(handle, self._old)
        except Exception:
            pass

    def _on_console_event(self, event):
        self._restore()
        return False

    def __exit__(self, *exc):
        if self._old is not None:
            flush_console_input()  # so keys pressed while mining don't leak into "pause"
            self._restore()
            atexit.unregister(self._restore)
            if self._cb is not None:
                try:
                    _input_guard["k32"].SetConsoleCtrlHandler(self._cb, False)
                except Exception:
                    pass
        _input_guard.update(k32=None, handle=None)
        return False


try:
    import sumo_art
except Exception:  # art file missing: the plain look still works
    sumo_art = None

# v4 palette (same 16 colours as the mockups)
NAVY, NAVY2, PURPLE, PINK, WHITE, YELLOW, GREY, BLACK, NEON, ORANGE = (
    (14, 16, 48), (30, 38, 96), (88, 28, 112), (255, 120, 190), (255, 250, 240),
    (255, 228, 64), (160, 160, 184), (0, 0, 0), (120, 255, 96), (255, 146, 56))
MAGENTA = (255, 36, 140)


def fg(c):
    return f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m"


def bg(c):
    return f"\x1b[48;2;{c[0]};{c[1]};{c[2]}m"


RESET = "\x1b[0m"


def pixels(rows, palette):
    """Pixel rows (palette index per character) -> console lines, two pixel rows per line using
    the upper-half block: top pixel = text colour, bottom pixel = background colour."""
    out = []
    for y in range(0, len(rows) - 1, 2):
        top, bot = rows[y], rows[y + 1]
        line, last = [], None
        for a, b in zip(top, bot):
            ca, cb = palette[int(a, 16)], palette[int(b, 16)]
            key = (ca, cb)
            if key != last:
                line.append(bg(cb) + (fg(ca) if ca != cb else ""))
                last = key
            line.append(" " if ca == cb else "\u2580")
        out.append("".join(line) + RESET)
    return out


def fmt_int(n):
    return f"{n:,}"


def fmt_sumo(base_units):
    v = base_units / UNIT
    return f"{v:,.0f}" if v == int(v) else f"{v:,.4f}".rstrip("0").rstrip(".")


def short(pk):
    s = str(pk)
    return s[:4] + "..." + s[-4:]


class Screen:
    """Draws the miner. Colour mode: a full-screen pixel dashboard redrawn in place.
    Plain mode: ordinary lines of text (for old consoles, logs, or --plain)."""

    WIDE = 94   # columns the full scene + HUD needs; narrower windows get the HUD without the scene

    def __init__(self, colour):
        self.colour = colour and sumo_art is not None
        self.events = []
        self.frame = 0
        self.started = False
        self.last_plain = 0.0
        self.footer_note = ""  # pinned under the events on the colour screen (never scrolls away)

    # ---- shared ----
    def event(self, text):
        self.events = (self.events + [time.strftime("%H:%M ") + text])[-3:]
        if not self.colour:
            print("\n  " + text, flush=True)

    def start(self, info):
        self.info = info
        if self.colour:
            sys.stdout.write("\x1b[?25l\x1b[2J")  # hide cursor, clear
            self.started = True
        else:
            plain_banner(info)

    def stop(self):
        if self.colour and self.started:
            sys.stdout.write(RESET + "\x1b[?25h\n")
            sys.stdout.flush()

    # ---- the dashboard ----
    def draw(self, hud, found=False):
        """hud: dict with block, rate, guesses, diff, reward, mined, balance, halving."""
        if not self.colour:
            return self.draw_plain(hud, found)
        self.frame += 1
        cols = shutil.get_terminal_size((120, 30)).columns
        art = sumo_art.FRAMES["found" if found else "mine"]
        scene = pixels(art[self.frame % len(art)], sumo_art.PALETTE) if cols >= self.WIDE else []
        right = self.panel(hud, found)
        n = max(len(scene), len(right))
        W = 30
        lines = []
        for i in range(n):
            left = (scene[i] + " ") if i < len(scene) else ""
            r = right[i] if i < len(right) else bg(NAVY) + " " * W + RESET
            lines.append(left + r)
        width = max((61 if scene else 0) + W, min(cols - 1, 100))
        lines.append("")
        for e in self.events:
            lines.append(fg(WHITE) + "  " + e[:width - 2] + RESET)
        for _ in range(3 - len(self.events)):
            lines.append("")
        if self.footer_note:
            lines.append(fg(YELLOW) + "  " + self.footer_note[:width - 2] + RESET)
        lines.append(fg(GREY) + "  Ctrl+C or close the window to stop. Test coins only: no real money." + RESET)
        out = "\x1b[H" + "".join(l + "\x1b[K\n" for l in lines) + "\x1b[J"
        sys.stdout.write(out)
        sys.stdout.flush()

    def panel(self, h, found):
        """The right-hand column: logo, title, status box, HUD. 30 columns, navy background."""
        W = 30
        N = bg(NAVY)

        def row(text="", colour=WHITE, raw=None):
            if raw is not None:
                return raw
            return N + fg(colour) + " " + text[:W - 2].ljust(W - 1) + RESET

        def kv(label, value, vcol=WHITE):
            value = value[:W - 2 - len(label) - 1]
            return N + fg(GREY) + " " + label + fg(vcol) + value.rjust(W - 2 - len(label)) + " " + RESET

        logo = pixels(sumo_art.LOGO, sumo_art.PALETTE)
        title = [N + "  " + l + N + " " * (W - 27) + RESET for l in logo]
        title.append(N + fg(WHITE) + "\x1b[1m" + "  FROG MINER" + RESET + N + fg(GREY)
                     + (VERSION + " ").rjust(W - 12) + RESET)
        if found:
            s = f"*** BLOCK FOUND! +{h['reward_won']} ***"
            box = [bg(YELLOW) + fg(BLACK) + "\x1b[1m" + " " * W + RESET,
                   bg(YELLOW) + fg(BLACK) + "\x1b[1m" + s.center(W) + RESET,
                   bg(YELLOW) + fg(BLACK) + "\x1b[1m" + " " * W + RESET]
        else:
            dots = "." * (1 + self.frame % 3)
            s = f">> MINING{dots}".ljust(13)
            box = [N + fg(WHITE) + "+" + "-" * (W - 2) + "+" + RESET,
                   N + fg(WHITE) + "| " + bg(BLACK) + fg(WHITE) + s.ljust(W - 4) + N + " |" + RESET,
                   N + fg(WHITE) + "+" + "-" * (W - 2) + "+" + RESET]
        lines = title + [row("TEST COINS / TEST CHAIN", PINK)] + box
        lines += [kv("BLOCK", "#" + fmt_int(h["block"])),
                  kv("HASH/S", h["rate"]),
                  kv("GUESS #", fmt_int(h["guesses"])),
                  kv("DIFF", h["diff"]),
                  kv("REWARD", h["reward"] + "/BLK", YELLOW),
                  kv("MINED", f"{h['mined']} BLOCK" + ("" if h["mined"] == 1 else "S")),
                  kv("BALANCE", h["balance"] + " SUMO", YELLOW),
                  kv("HALVING IN", fmt_int(h["halving"]) + " BLK"),
                  row(),
                  row("PAYS TO " + h["pays_to"], NEON)]
        lines.append(row())
        while len(lines) < 21:
            lines.append(row())
        return lines

    def draw_plain(self, h, found):
        if found:
            print(f"\n  *** BLOCK FOUND! +{h['reward_won']} ***  block #{fmt_int(h['block'])}, "
                  f"balance {h['balance']} SUMO", flush=True)
            return
        now = time.time()
        if now - self.last_plain < 1:
            return
        self.last_plain = now
        print(f"\r  >> MINING...  block #{fmt_int(h['block'])}  guess #{fmt_int(h['guesses'])}  "
              f"{h['rate']}  diff {h['diff']}   ", end="", flush=True)


def plain_banner(info):
    lines = ["SUMO FROG MINER " + VERSION + "  ($SUMO)",
             "TEST COINS / TEST CHAIN on " + info["cluster"],
             "worthless, no real money"]
    w = max(len(l) for l in lines) + 4
    print("  +" + "=" * w + "+")
    for l in lines:
        print("  |  " + l.ljust(w - 2) + "|")
    print("  +" + "=" * w + "+")
    print(f"  fee wallet {info['fee_wallet']} | rewards go to {info['pays_to']} | {info['workers']} workers")


# ======================= network =======================

def apply_network(settings):
    """Pick the RPC from a single "network" setting. Default is the private test chain.
    "devnet" uses devnet_rpc (public Solana devnet). Does not deploy anything.
    Refuses a network or devnet_rpc value that is not text, or is empty."""
    settings["_shipped_rpc"] = settings.get("rpc")  # the private network link this zip shipped with
    if "network" not in settings:
        raw = "private"
    else:
        net = settings["network"]
        if not isinstance(net, str) or not net.strip():
            sys.exit('The "network" setting in sumo_config.json must be the word "private" or "devnet". Stopping.')
        raw = net.strip().lower().replace("_", "-")
    if "devnet_rpc" in settings:
        devnet_rpc = settings["devnet_rpc"]
        if not isinstance(devnet_rpc, str) or not devnet_rpc.strip():
            sys.exit('The "devnet_rpc" setting in sumo_config.json must be a web address '
                     '(for example https://api.devnet.solana.com). Stopping.')
    if raw in ("devnet", "public-devnet"):
        rpc = settings.get("devnet_rpc") or "https://api.devnet.solana.com"
        settings["rpc"] = rpc
        settings["network"] = "devnet"
    elif raw in ("private", "private-test"):
        settings["network"] = "private"
    else:
        sys.exit('Unknown network in sumo_config.json. Use "private" or "devnet". Stopping.')
    return settings


def warn_network_mismatch(settings, cluster):
    """Warn (do not stop) when the chain we found does not match the chosen network."""
    wanted = settings.get("network") or "private"
    if wanted == "devnet" and cluster != "devnet":
        print(f'Warning: network is set to "devnet" in sumo_config.json, but this chain is {cluster}.', flush=True)
    elif wanted == "private" and cluster != "private Sumo test network":
        print(f'Warning: network is set to "private" in sumo_config.json, but this chain is {cluster}.', flush=True)


def load_settings():
    with open(os.path.join(HERE, "sumo_config.json")) as f:
        settings = json.load(f)
    return apply_network(settings)


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
# Josh's choice (2 Nov 2026): the private test link stays plain http until launch, with this warning.
HTTP_NOTE = ("Note: the private test link isn't encrypted. Fine for test coins with no value. "
             "Always check the payout address you type.")
# The colour mining screen's pinned footer version (fits an 80-column window; the full note is
# printed at startup, in plain mode and before any withdraw).
HTTP_NOTE_SHORT = "Note: test link isn't encrypted. Check your payout address."


def secs_text(el):
    """How long a block took: tenths under 10 s (a fast PC can find one in under a second,
    which "0s" made look like a bug), whole seconds after that."""
    return f"{el:.1f}s" if el < 10 else f"{el:.0f}s"


def has_odd_authority(url):
    """True for a link with a backslash anywhere or a user name part (name@host): Python's link reader and
    the network code can read such links differently, so the miner refuses them. Anything that isn't text
    (a missing or hand-edited link) is refused too."""
    if not isinstance(url, str):
        return True
    try:
        return "\\" in url or "@" in urllib.parse.urlsplit(url).netloc
    except ValueError:
        return True


def is_local_url(url):
    """True only when the link's host is exactly this computer (not just containing 'localhost')."""
    try:
        if has_odd_authority(url):          # also True for anything that is not text
            return False
        return (urllib.parse.urlsplit(url).hostname or "").lower() in LOCAL_HOSTS
    except ValueError:
        return False


def url_scheme(url):
    if not isinstance(url, str):
        return ""
    try:
        return urllib.parse.urlsplit(url).scheme.lower()
    except ValueError:
        return ""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A server that answers "go to another address" is treated as a failure, never followed."""
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(NoRedirect)


def open_url(req, timeout):
    """The one way every network request in the miner is opened (redirects are refused)."""
    return _OPENER.open(req, timeout=timeout)


send_started = threading.Event()   # set the moment a transaction is handed to the network (see Rpc.call)
_cancel = threading.local()   # grind's watch thread sets .event; its retry waits then end early


def retry_wait(secs):
    ev = getattr(_cancel, "event", None)
    if ev is None:
        time.sleep(secs)
    elif ev.wait(secs):
        raise RuntimeError("stopped")


class Rpc:
    def __init__(self, url):
        self.url = url

    def call(self, method, *params):
        if method == "sendTransaction":
            send_started.set()
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}).encode()
        for attempt in range(5):
            try:
                req = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
                with open_url(req, 30) as r:
                    out = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if 300 <= e.code < 400:
                    raise      # a redirect is final: no retries and no waiting
                if attempt == 4:
                    raise
                retry_wait(2 * (attempt + 1))
            except Exception:  # network blips / 429s on the public RPC
                if attempt == 4:
                    raise
                retry_wait(2 * (attempt + 1))
        if "error" in out:
            raise RpcError(out["error"])
        return out["result"]


class RpcError(Exception):
    def __init__(self, err):
        super().__init__(err.get("message", str(err)))
        self.err = err

    def custom_code(self):
        try:
            ie = self.err["data"]["err"]["InstructionError"][1]
            return ie.get("Custom") if isinstance(ie, dict) else None
        except Exception:
            return None


def link_problem(url, settings):
    """None when the network link passes the first check (before any request is sent), or the plain
    sentence to stop with. https only, except this computer (localhost) and the private network's own
    shipped link when "private_genesis" is set. check_devnet and the picture menu both use this."""
    scheme, local = url_scheme(url), is_local_url(url)
    if scheme not in ("http", "https"):
        return "The network link must start with https:// . Stopping."
    if has_odd_authority(url):
        return "That network link has a backslash or a user name part (name@) in it. Use a plain https:// link. Stopping."
    plain_http_ok = local or (url == settings.get("_shipped_rpc") and settings.get("private_genesis"))
    if scheme == "http" and not plain_http_ok:
        return "That network link isn't encrypted (http). Use an https:// link. Stopping."
    return None


def check_devnet(rpc, url, settings):
    """Refuse to run anywhere except devnet, a local test validator, or the one private
    Sumo Frog test network named in sumo_config.json ("private_genesis").
    Links must be https, except on this computer (localhost) and the private network's own
    link from sumo_config.json, which is plain http for now (see the note printed below)."""
    scheme, local = url_scheme(url), is_local_url(url)
    problem = link_problem(url, settings)
    if problem:
        sys.exit(problem)
    genesis = rpc.call("getGenesisHash")
    if genesis == MAINNET_GENESIS:
        sys.exit("This RPC is Solana MAINNET. Sumo Frog never runs there. Stopping.")
    if settings.get("private_genesis") and genesis == settings["private_genesis"]:
        cluster = "private Sumo test network"
        warn_network_mismatch(settings, cluster)
        return cluster
    if scheme == "http" and not local:
        sys.exit("That network link isn't encrypted (http) and isn't the private Sumo test network. Stopping.")
    if genesis == DEVNET_GENESIS:
        cluster = "devnet"
        warn_network_mismatch(settings, cluster)
        return cluster
    if local:
        cluster = "local test validator"
        warn_network_mismatch(settings, cluster)
        return cluster
    sys.exit("This RPC is not Solana devnet or the private Sumo Frog test network. Stopping.")


class Chain:
    def __init__(self, settings):
        self.url = settings["rpc"]
        self.rpc = Rpc(self.url)
        self.cluster = check_devnet(self.rpc, self.url, settings)
        # The only plain-http link check_devnet lets through off this computer is the private one.
        self.unencrypted = url_scheme(self.url) == "http" and not is_local_url(self.url)
        if self.unencrypted:
            print(HTTP_NOTE)
        self.program = Pubkey.from_string(settings["program_id"])
        self.config, _ = Pubkey.find_program_address([b"config"], self.program)
        self.mint, _ = Pubkey.find_program_address([b"mint"], self.program)

    def ata(self, owner):
        return Pubkey.find_program_address([bytes(owner), bytes(TOKEN_PROGRAM), bytes(self.mint)], ATA_PROGRAM)[0]

    def state(self):
        info = self.rpc.call("getAccountInfo", str(self.config), {"encoding": "base64", "commitment": "confirmed"})
        if not info["value"]:
            sys.exit("Sumo Frog isn't set up on this network yet (config account missing).")
        d = base64.b64decode(info["value"]["data"][0])
        assert d[:8] == CONFIG_DISC, "unexpected config account"
        o = 8
        authority = Pubkey.from_bytes(d[o:o + 32]); o += 32
        mint = Pubkey.from_bytes(d[o:o + 32]); o += 32
        o += 2  # bumps
        challenge = d[o:o + 32]; o += 32
        (target, initial_reward, halving, retarget, block_time, max_supply, blocks, minted,
         epoch_start, last_solve) = struct.unpack_from("<QQQQqQQQqq", d, o); o += 80
        last_miner = Pubkey.from_bytes(d[o:o + 32]); o += 32
        (last_reward,) = struct.unpack_from("<Q", d, o)
        era = blocks // halving
        reward = 0 if era >= 64 else initial_reward >> era
        return dict(authority=authority, mint=mint, challenge=challenge, target=target,
                    initial_reward=initial_reward, halving_interval=halving, retarget_interval=retarget,
                    target_block_time=block_time, max_supply=max_supply, blocks_mined=blocks,
                    total_minted=minted, epoch_start_ts=epoch_start, last_solve_ts=last_solve,
                    last_miner=last_miner, last_reward=last_reward,
                    next_reward=min(reward, max_supply - minted),
                    blocks_to_halving=(era + 1) * halving - blocks)

    def sol_balance(self, owner):
        return self.rpc.call("getBalance", str(owner), {"commitment": "confirmed"})["value"] / UNIT

    def sumo_units(self, owner):
        try:
            v = self.rpc.call("getTokenAccountBalance", str(self.ata(owner)), {"commitment": "confirmed"})
            return int(v["value"]["amount"])
        except RpcError:
            return 0

    def submit(self, kp, challenge, guess, payout=None):
        """Send a winning guess. payout=None: reward to the fee wallet itself (`mine`).
        payout=<address>: reward to that wallet (`mine_to`), the fee wallet only pays fees."""
        if payout is None or payout == kp.pubkey():
            data = MINE_DISC + challenge + struct.pack("<Q", guess)
            accounts = [AccountMeta(kp.pubkey(), True, True), AccountMeta(self.config, False, True),
                        AccountMeta(self.mint, False, True), AccountMeta(self.ata(kp.pubkey()), False, True)]
        else:
            data = MINE_TO_DISC + challenge + struct.pack("<Q", guess)
            accounts = [AccountMeta(kp.pubkey(), True, True), AccountMeta(payout, False, False),
                        AccountMeta(self.config, False, True), AccountMeta(self.mint, False, True),
                        AccountMeta(self.ata(payout), False, True)]
        accounts += [AccountMeta(TOKEN_PROGRAM, False, False), AccountMeta(ATA_PROGRAM, False, False),
                     AccountMeta(SYSTEM_PROGRAM, False, False)]
        ix = Instruction(self.program, data, accounts)
        bh = self.rpc.call("getLatestBlockhash", {"commitment": "confirmed"})["value"]["blockhash"]
        tx = Transaction([kp], Message([ix], kp.pubkey()), Hash.from_string(bh))
        sig = self.rpc.call("sendTransaction", base64.b64encode(bytes(tx)).decode(),
                            {"encoding": "base64", "preflightCommitment": "confirmed"})
        for _ in range(60):
            st = self.rpc.call("getSignatureStatuses", [sig])["value"][0]
            if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
                if st.get("err"):
                    raise RpcError({"message": str(st["err"]), "data": {"err": st["err"]}})
                return sig
            time.sleep(1)
        raise TimeoutError(f"not confirmed in 60s: {sig}")


def difficulty_bits(target):
    import math
    return 64 - math.log2(target + 1)


def expected_hashes(target):
    return (2 ** 64) / (target + 1)


# ======================= payout address =======================

BAD_PAYOUTS = {str(SYSTEM_PROGRAM), str(TOKEN_PROGRAM), str(ATA_PROGRAM)}


def sumo_addresses(settings):
    """The Sumo Frog program, its config and its mint: never a wallet."""
    program = Pubkey.from_string(settings["program_id"])
    out = {program, Pubkey.find_program_address([b"config"], program)[0],
           Pubkey.find_program_address([b"mint"], program)[0]}
    for k in ("config", "mint"):
        try:
            out.add(Pubkey.from_string(settings[k]))
        except Exception:
            pass
    return out


def parse_payout(text, settings, nothing="Nothing was saved."):
    """A wallet's PUBLIC address, or exit with a plain explanation. Never accepts anything that
    looks like a seed phrase, a private key or a key file, and never an address nobody can spend
    from: system programs, the Sumo Frog program, config or mint, or a program-controlled
    (off-curve) address such as a token account. Used for every payout and withdraw path."""
    t = (text or "").strip().strip('"').strip("'")
    if not t:
        sys.exit("No address given. Paste your wallet's PUBLIC address (the one you'd share to receive coins).")
    if len(t.split()) > 1:
        sys.exit("That looks like a list of words (a seed phrase?). NEVER type a seed phrase into anything,\n"
                 "including this miner. Paste only your wallet's PUBLIC address. " + nothing)
    if t.startswith("[") or "," in t:
        sys.exit("That looks like the contents of a key file. Never share or paste key files.\n"
                 "Paste only your wallet's PUBLIC address. " + nothing)
    if len(t) > 44:
        sys.exit("That's too long to be a wallet address. It might be a PRIVATE key: never paste one anywhere.\n"
                 "Paste only your wallet's PUBLIC address (32 to 44 letters and numbers). " + nothing)
    try:
        pk = Pubkey.from_string(t)
    except Exception:
        sys.exit("That isn't a valid Solana address. Check you copied all of it. " + nothing)
    if str(pk) in BAD_PAYOUTS or pk == Pubkey.default():
        sys.exit("That's a Solana system address, not a wallet. " + nothing)
    if pk in sumo_addresses(settings):
        sys.exit("That's a Sumo Frog program address, not a wallet. " + nothing)
    if not pk.is_on_curve():
        sys.exit("That's a program-controlled address (like a token account), not a normal wallet. "
                 "Coins sent there could be stuck for good. Use your wallet's main PUBLIC address. " + nothing)
    return pk


def check_wallet_account(chain, pk, nothing):
    """With a network to ask: refuse an address that already exists as a program or token
    account rather than a plain wallet. A brand-new wallet (no account yet) is fine.
    Returns the account info (or None)."""
    acct = _account(chain, pk)
    if acct and (acct.get("executable") or acct.get("owner") != str(SYSTEM_PROGRAM)):
        sys.exit("That address belongs to a program or token account, not a wallet. "
                 "Use your wallet's main PUBLIC address. " + nothing)
    return acct


def flush_typed_ahead(k32=None):
    k32 = k32 or _kernel32()
    k32.FlushConsoleInputBuffer(k32.GetStdHandle(_STD_INPUT_HANDLE))


def ask_line(prompt):
    """input(), after throwing away any key already waiting in the console, so a stray Enter that was
    typed earlier can't answer this question before the person has seen it."""
    if os.name == "nt" and sys.stdin.isatty():
        try:
            flush_typed_ahead()
        except Exception:
            pass
    return input(prompt)


def ask_address(prompt, check):
    """Keep asking until check(text) accepts the answer. check refuses with sys.exit("reason"): the
    reason is shown and the question comes back. 'back' or 'cancel' gives None; an empty answer asks again."""
    while True:
        try:
            text = ask_line(prompt).strip()
        except EOFError:
            sys.exit("No address given.")
        if text.lower() in ("back", "cancel"):
            return None
        if not text:
            print("Paste an address, or type  back  to cancel.\n")
            continue
        try:
            return check(text)
        except SystemExit as e:
            if not isinstance(e.code, str):
                raise
            print(f"\n{e.code}\nTry again, or type  back  to cancel.\n")


FIX_SAVED = "Fix it by running Set payout address (or: py sumo_miner.py set-payout <address>)."


def saved_payout(settings):
    """The payout address from payout-address.txt, else from sumo_config.json ("payout"), else None."""
    text = None
    if os.path.exists(PAYOUT_FILE):
        with open(PAYOUT_FILE) as f:
            text = f.read().strip()
    elif settings.get("payout"):
        text = settings["payout"]
    if not text or text.lower() == "none":
        return None
    return parse_payout(text, settings, "Your saved payout address can't be used. " + FIX_SAVED)


def cmd_set_payout(args, settings):
    print("Checking the network...", flush=True)
    chain = None
    try:  # a refusal of the network itself (mainnet, bad link) stops here, before any question
        chain = Chain(settings)
    except Exception:  # offline: SystemExit (a refusal) still stops
        pass

    def check(text):
        if text.strip().lower() in ("none", "off", "self"):
            return "none"
        pk = parse_payout(text, settings)
        try:  # double-check it's a plain wallet, not a token or program account, if we can reach the network
            if chain is None:
                raise OSError("offline")
            check_wallet_account(chain, pk, "Nothing was saved.")
        except Exception:  # offline or a network hiccup; SystemExit (a refusal) still stops here
            print("(Couldn't reach the test network to double-check the address; the miner checks again when it starts.)")
        return pk

    if args.address is not None:
        pk = check(args.address)
    else:
        pk = ask_address("Paste your wallet's PUBLIC address ('none' = keep rewards in the miner's wallet, "
                         "'back' = cancel): ", check)
        if pk is None:
            sys.exit("Cancelled. Nothing was saved.")
    if isinstance(pk, str):  # "none"
        if os.path.exists(PAYOUT_FILE):
            os.remove(PAYOUT_FILE)
        print("Payout address removed. Rewards will stay in the miner's own test wallet.")
        return
    print(f"\nRewards will be sent to this PUBLIC address:\n\n    {pk}\n")
    print("Check it matches your wallet exactly. Coins sent to a wrong address are lost.\n"
          "Never use an exchange deposit address.")
    if sys.stdin.isatty() and not args.yes:
        if input("Type YES to save it: ").strip().upper() != "YES":
            sys.exit("Not saved.")
    with open(PAYOUT_FILE, "w") as f:
        f.write(str(pk) + "\n")
    print(f"Saved to {os.path.basename(PAYOUT_FILE)}. The miner will pay this address from the next block.")


# ======================= withdraw (leftover test SOL back to your wallet) =======================

SYSVAR_RENT = "SysvarRent111111111111111111111111111111111"
TOKEN_ACCOUNT_SIZE = 165


STOPPED_SENDING = "\nStopped while sending. It may still go through. Check balance (menu 2) before trying again."
STOPPED_BEFORE = "\nStopped before anything was sent."


def _system_transfer(src, dst, lamports):
    return Instruction(SYSTEM_PROGRAM, struct.pack("<IQ", 2, lamports),
                       [AccountMeta(src, True, True), AccountMeta(dst, False, True)])


def _account(chain, pk):
    return chain.rpc.call("getAccountInfo", str(pk), {"encoding": "base64", "commitment": "confirmed"})["value"]


def _send(chain, kp, ixs):
    bh = chain.rpc.call("getLatestBlockhash", {"commitment": "confirmed"})["value"]["blockhash"]
    tx = Transaction([kp], Message(ixs, kp.pubkey()), Hash.from_string(bh))
    sig = chain.rpc.call("sendTransaction", base64.b64encode(bytes(tx)).decode(),
                         {"encoding": "base64", "preflightCommitment": "confirmed"})
    for _ in range(60):
        st = chain.rpc.call("getSignatureStatuses", [sig])["value"][0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            if st.get("err"):
                raise RpcError({"message": str(st["err"]), "data": {"err": st["err"]}})
            return sig
        time.sleep(1)
    raise TimeoutError(f"not confirmed in 60s: {sig}")


def _fee(chain, kp, ixs):
    """What the network charges for this transaction (falls back to the standard 5,000 lamports)."""
    try:
        bh = chain.rpc.call("getLatestBlockhash", {"commitment": "confirmed"})["value"]["blockhash"]
        msg = Message.new_with_blockhash(ixs, kp.pubkey(), Hash.from_string(bh))
        v = chain.rpc.call("getFeeForMessage", base64.b64encode(bytes(msg)).decode(), {"commitment": "confirmed"})["value"]
        return int(v) if v is not None else 5000
    except Exception:
        return 5000


def withdraw_destination(args, settings, kp, chain):
    """The PUBLIC address to send to: the one typed on the command line, else the saved payout address
    (confirmed on screen), else ask until it's a plain wallet address (or 'back'). Returns (address, its account)."""
    nothing = "Nothing was sent."

    def check(text):
        dest = parse_payout(text, settings, nothing)
        if dest == kp.pubkey():
            sys.exit("That's the miner's own wallet. Withdraw sends coins to a DIFFERENT wallet you control. " + nothing)
        if dest in (chain.program, chain.config, chain.mint):
            sys.exit("That's a Sumo Frog program address, not a wallet. " + nothing)
        return dest, check_wallet_account(chain, dest, nothing)

    if args.address:
        return check(args.address)
    saved = saved_payout(settings)
    if saved is not None:
        print(f"Your saved payout address is:\n\n    {saved}\n")
        if not (sys.stdin.isatty() and not args.yes):
            return check(str(saved))
        if input("Send to this address? [y/N] ").strip().lower() in ("y", "yes"):
            return check(str(saved))
    else:
        print("No payout address saved yet, so please paste one.\n")
    if not sys.stdin.isatty():
        sys.exit("No address given. Run: py sumo_miner.py withdraw <your wallet's PUBLIC address>")
    got = ask_address("Paste your wallet's PUBLIC address to send to ('back' = cancel): ", check)
    if got is None:
        sys.exit("Cancelled. Nothing was sent.")
    return got


def cmd_withdraw(args, settings):
    """Send the miner wallet's leftover test SOL (and optionally its SUMO) to a wallet you control.
    Sweeps everything minus the fee, so the miner's wallet ends at 0 and closes cleanly."""
    chain = Chain(settings)
    kp = load_key(args.keypair)
    me = kp.pubkey()
    c = enable_colour(args.plain)
    hi = (lambda t: fg(YELLOW) + t + RESET) if c else (lambda t: t)
    head = (lambda t: bg(NAVY) + fg(PINK) + " " + t + " " + RESET) if c else (lambda t: "== " + t + " ==")
    print(head("WITHDRAW TEST SOL") + f"   {chain.cluster}\n")
    print(f"Miner's test wallet  {me}")
    dest, dest_acct = withdraw_destination(args, settings, kp, chain)

    balance = chain.rpc.call("getBalance", str(me), {"commitment": "confirmed"})["value"]
    my_ata = chain.ata(me)
    ata_acct = _account(chain, my_ata)
    sumo = chain.sumo_units(me) if ata_acct else 0
    ixs, extra_in, extra_out, notes = [], 0, 0, []

    send_sumo = False
    if sumo > 0:
        if args.sumo:
            send_sumo = True
        elif sys.stdin.isatty() and not args.yes:
            send_sumo = input(f"The miner's wallet also holds {fmt_sumo(sumo)} SUMO. Send that too? [y/N] "
                              ).strip().lower() in ("y", "yes")
    if send_sumo:
        dest_ata = chain.ata(dest)
        if not _account(chain, dest_ata):  # create the SUMO account at the destination (idempotent)
            extra_out = chain.rpc.call("getMinimumBalanceForRentExemption", TOKEN_ACCOUNT_SIZE)
            ixs.append(Instruction(ATA_PROGRAM, bytes([1]), [
                AccountMeta(me, True, True), AccountMeta(dest_ata, False, True), AccountMeta(dest, False, False),
                AccountMeta(chain.mint, False, False), AccountMeta(SYSTEM_PROGRAM, False, False),
                AccountMeta(TOKEN_PROGRAM, False, False)]))
            notes.append(f"opens a SUMO account for the destination (-{extra_out / UNIT:.6f} SOL, kept by it)")
        ixs.append(Instruction(TOKEN_PROGRAM, bytes([12]) + struct.pack("<QB", sumo, 9), [
            AccountMeta(my_ata, False, True), AccountMeta(chain.mint, False, False),
            AccountMeta(dest_ata, False, True), AccountMeta(me, True, False)]))
    if ata_acct and (send_sumo or sumo == 0):  # empty SUMO account: close it and get its rent back
        extra_in = ata_acct["lamports"]
        ixs.append(Instruction(TOKEN_PROGRAM, bytes([9]), [
            AccountMeta(my_ata, False, True), AccountMeta(me, False, True), AccountMeta(me, True, False)]))
        notes.append(f"closes the miner's SUMO account once empty (+{extra_in / UNIT:.6f} SOL back)")
    elif sumo > 0:
        notes.append(f"{fmt_sumo(sumo)} SUMO stays in the miner's wallet (use --sumo to send it too)")

    fee = _fee(chain, kp, ixs + [_system_transfer(me, dest, 1)])
    amount = balance + extra_in - extra_out - fee
    if amount <= 0:
        sys.exit(f"Nothing to withdraw: the wallet has {balance / UNIT:.6f} test SOL, less than the fee.")
    if not dest_acct:
        floor = chain.rpc.call("getMinimumBalanceForRentExemption", 0)
        if amount < floor:
            sys.exit(f"Too little to send to a brand-new wallet ({amount / UNIT:.6f} SOL; the network needs at least "
                     f"{floor / UNIT:.6f} to open one). Nothing was sent.")
    ixs.append(_system_transfer(me, dest, amount))

    print(f"\n  >> SEND     {hi(f'{amount / UNIT:.6f} test SOL')}" + (f" + {hi(fmt_sumo(sumo) + ' SUMO')}" if send_sumo else ""))
    print(f"  >> TO       {hi(str(dest))}")
    print(f"  >> FEE      {fee / UNIT:.6f} SOL   (the miner's wallet ends at 0 SOL and closes)")
    for n in notes:
        print(f"  ..          {n}")
    print("\nCheck the address matches your wallet exactly. Coins sent to a wrong address are lost.")
    if chain.unencrypted:
        print(HTTP_NOTE)
    if not args.yes:
        if not sys.stdin.isatty():
            sys.exit("Not sent (add --yes to send without asking).")
        if input("Send now? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("Not sent.")
    send_started.clear()
    try:
        sig = _send(chain, kp, ixs)
    except KeyboardInterrupt:
        sys.exit(STOPPED_SENDING if send_started.is_set() else STOPPED_BEFORE)
    except RpcError as e:
        sys.exit(f"!! The network refused it: {e}. Nothing was sent.")
    try:
        print(f"\n*** SENT. Transaction {sig}")
        print(f"Destination now has {chain.sol_balance(dest):.6f} test SOL.")
        print("To mine again on this PC, get some test SOL for fees first.")
    except KeyboardInterrupt:
        sys.exit(f"\nDone, the coins were sent. Transaction {sig}")


# ======================= hashing workers =======================
CHUNK = 50_000


def _worker(prefix, target, start, wid, nworkers, found, counter, stop):
    # Ctrl+C reaches every process on the console. Workers ignore it (the parent sets `stop` and
    # shuts them down), so they never print their own KeyboardInterrupt traceback over the screen.
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    parent = mp.parent_process()
    tb = target.to_bytes(8, "big")
    base = hashlib.sha256(prefix)  # challenge || reward address = exactly one 64-byte block, hashed once
    copy = base.copy
    chunk_id = wid
    while not stop.is_set():
        # If the miner itself was killed (Task Manager, crash), nobody is left to set `stop`
        # and this worker ignores Ctrl+C: quit on our own so it can't burn CPU forever.
        if parent is not None and not parent.is_alive():
            return
        lo = start + chunk_id * CHUNK
        for n in range(lo, lo + CHUNK):
            h = copy()
            h.update(n.to_bytes(8, "little"))
            if h.digest()[:8] <= tb:
                found.put(n & 0xFFFFFFFFFFFFFFFF)
                stop.set()
                return
        with counter.get_lock():
            counter.value += CHUNK
        chunk_id += nworkers


def grind(chain, earner, st, workers, on_tick, poll_secs=5):
    """Search for a winning guess for `earner` (the reward address).
    Returns (guess or None if the challenge moved on, hashes tried, seconds)."""
    prefix = st["challenge"] + bytes(earner)
    start = secrets.randbits(62)
    found, counter, stop = mp.Queue(), mp.Value("Q", 0), mp.Event()
    procs = [mp.Process(target=_worker, args=(prefix, st["target"], start, i, workers, found, counter, stop), daemon=True)
             for i in range(workers)]
    result = None
    moved, done = threading.Event(), threading.Event()

    def watch():  # in its own thread, so a slow or dead RPC can't make Ctrl+C wait
        _cancel.event = done
        while not done.wait(poll_secs):
            try:
                if chain.state()["challenge"] != st["challenge"]:
                    moved.set()
                    return
            except (Exception, SystemExit):
                pass
    # quiet input from before the workers start, only while hashing: start-up and network waits keep a normal Ctrl+C
    t0 = time.time()
    with quiet_console_input():
        try:
            for p in procs:
                p.start()
            threading.Thread(target=watch, daemon=True).start()
            while not moved.is_set():
                try:
                    result = found.get(timeout=0.4)
                    break
                except queue.Empty:
                    pass
                el = time.time() - t0
                on_tick(counter.value, counter.value / el if el else 0)
            else:
                result = "moved"
        finally:
            done.set()
            stop.set()
            for p in procs:
                if p.pid is None:  # never started (a worker failed to start)
                    continue
                p.join(timeout=2)
                if p.is_alive():
                    p.terminate()
    el = time.time() - t0
    return result, counter.value, el


def rate_text(r):
    return f"{r / 1e6:.2f} MH/S" if r >= 1e5 else f"{r / 1e3:.1f} KH/S"


def cmd_mine(args, settings):
    chain = Chain(settings)
    kp = load_key(args.keypair)
    payout = parse_payout(args.payout, settings, "Not mining.") if args.payout and args.payout.lower() not in ("none", "self") else (
        None if args.payout else saved_payout(settings))
    if payout == kp.pubkey():
        payout = None
    if payout is not None:
        if payout in (chain.program, chain.config, chain.mint):
            sys.exit("Your payout address is a Sumo Frog program address, not a wallet. " + FIX_SAVED)
        check_wallet_account(chain, payout, "Not mining. " + FIX_SAVED)
    earner = payout or kp.pubkey()
    if chain.sol_balance(kp.pubkey()) < 0.003:
        how = ("Get free devnet SOL at https://faucet.solana.com (pick Devnet, paste your wallet address), "
               "then start mining again." if chain.cluster == "devnet" else
               "Run:  py sumo_miner.py faucet   (or run Get test SOL)")
        sys.exit(f"Your test wallet {kp.pubkey()} needs a little test SOL for fees (about 0.003).\n{how}")
    workers = args.workers or os.cpu_count() or 1
    scr = Screen(enable_colour(args.plain))
    scr.start(dict(cluster=chain.cluster, fee_wallet=str(kp.pubkey()), workers=workers,
                   pays_to=str(earner) + ("" if payout else " (this miner's own test wallet)")))
    if payout:
        scr.event(f"Rewards go to your payout address {payout}")
    if chain.unencrypted:
        if scr.colour:
            scr.footer_note = HTTP_NOTE_SHORT  # pinned: an event line would be cut off and scroll away
        else:
            scr.event(HTTP_NOTE)
    scr.event(f"Mining on the {chain.cluster} with {workers} CPU workers")
    mined, rates, sending = 0, [], False
    hud = {}
    try:
        while args.blocks == 0 or mined < args.blocks:
            st = chain.state()
            if st["next_reward"] <= 0:
                scr.event("Max supply reached. Nothing left to mine.")
                break
            balance = fmt_sumo(chain.sumo_units(earner))
            hud = dict(block=st["blocks_mined"] + 1, rate="--", guesses=0,
                       diff=f"{difficulty_bits(st['target']):.1f} BITS", reward=fmt_sumo(st["next_reward"]) + " SUMO",
                       mined=mined, balance=balance, halving=st["blocks_to_halving"], pays_to=short(earner),
                       reward_won="")

            def tick(hashes, rate):
                if stop_requested(scr, hud):
                    raise KeyboardInterrupt
                hud.update(guesses=hashes, rate=rate_text(rate))
                scr.draw(hud)

            scr.draw(hud)
            guess, hashes, el = grind(chain, earner, st, workers, tick)
            if el > 1 and hashes:
                rates.append(hashes / el)
            if guess == "moved" or guess is None:
                scr.event(f"Block #{fmt_int(st['blocks_mined'] + 1)} went to another frog. On to the next one.")
                continue
            send_started.clear()
            try:
                chain.submit(kp, st["challenge"], guess, payout)
            except KeyboardInterrupt:
                sending = send_started.is_set()
                raise
            except RpcError as e:
                code = e.custom_code()
                if code == 6002:
                    scr.event("Another miner got there first. On to the next block.")
                else:
                    scr.event(f"Block refused: {ERRORS.get(code, e)}")
                continue
            mined += 1
            won = fmt_sumo(st["next_reward"]) + " SUMO"
            hud.update(mined=mined, balance=fmt_sumo(chain.sumo_units(earner)), reward_won=won)
            scr.event(f"*** BLOCK FOUND! #{fmt_int(st['blocks_mined'] + 1)}  +{won} "
                      f"after {fmt_int(hashes)} guesses ({secs_text(el)})")
            for _ in range(8 if scr.colour else 1):
                scr.draw(hud, found=True)
                time.sleep(0.4 if scr.colour else 0)
    except KeyboardInterrupt:
        pass
    finally:
        scr.stop()
    if sending:
        print(STOPPED_SENDING + " (The last block was being sent.)")
    if rates:
        print(f"\n  Stopped. Mined {mined} block(s) this session. Average {sum(rates)/len(rates)/1e6:.2f} MH/s.")


def cmd_status(args, settings):
    chain = Chain(settings)
    st = chain.state()
    print(f"Network           {chain.cluster}")
    print(f"Program           {chain.program}\nMint              {chain.mint}")
    print(f"Blocks mined      {st['blocks_mined']:,}")
    print(f"Difficulty        {difficulty_bits(st['target']):.2f} bits (~{expected_hashes(st['target'])/1e6:.1f}M guesses per block)")
    print(f"Next reward       {fmt_sumo(st['next_reward'])} SUMO (halves every {st['halving_interval']:,} blocks; "
          f"next halving in {st['blocks_to_halving']:,} blocks)")
    print(f"Supply            {fmt_sumo(st['total_minted'])} / {fmt_sumo(st['max_supply'])} SUMO")
    print(f"Target block time {st['target_block_time']}s, retarget every {st['retarget_interval']} blocks")
    print(f"Last block        {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st['last_solve_ts']))} by {st['last_miner']}")


# ======================= picture menu (Pixy's design) =======================
# The launcher calls `sumo_miner.py menu` before it asks for a key. It draws an 80 x 30 colour screen, or
# exits 1 having printed nothing, and then the launcher shows its plain menu. It parses the wallet file, uses
# only the public half, and makes at most a short chain check and one balance request, so it can't print a secret or hang.
MENU_RPC_TIMEOUT = 2.5      # seconds for the one balance request; the whole wait is capped a little above


def read_public_key(path):
    """("none", None) no wallet file, ("bad", None) unreadable or damaged, ("ok", Pubkey). The menu parses the
    wallet file and checks that its two halves belong together (the same check the miner makes when it loads
    the wallet), then uses only the public half: the secret half is never shown, logged or kept."""
    if not os.path.isfile(path):
        return "none", None
    try:
        with open(path) as f:
            data = json.load(f)
        if not (isinstance(data, list) and len(data) == 64
                and all(type(x) is int and 0 <= x < 256 for x in data)):
            return "bad", None
        pub = Keypair.from_bytes(bytes(data)).pubkey()      # raises if the public half doesn't match
        return "ok", pub
    except Exception:
        return "bad", None


MENU_DEVNET_RPC = "https://api.devnet.solana.com"


def menu_rpc_allowed(settings):
    """The same first rules as check_devnet (https only, except this computer and the shipped private link when
    private_genesis is set), and then only a link that is exactly public devnet, this computer or the shipped
    private link. Any other link (including a mainnet one) gets no request at all."""
    url = settings.get("rpc") or ""
    if not isinstance(url, str) or link_problem(url, settings):
        return False
    if is_local_url(url) or url == MENU_DEVNET_RPC:
        return True
    return bool(settings.get("private_genesis")) and url == settings.get("_shipped_rpc")


def menu_post(url, method, params, timeout):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with open_url(req, timeout) as r:
        return json.loads(r.read(65536))


def menu_chain_ok(settings, timeout):
    """Never ask about the wallet on mainnet. Public devnet is known by its exact link; this computer and the
    private link are asked for their genesis hash first (no wallet details in that request); off this computer
    only the private network's own genesis hash is accepted, as in check_devnet."""
    url = settings["rpc"]
    if url == MENU_DEVNET_RPC:
        return True
    genesis = menu_post(url, "getGenesisHash", [], timeout).get("result")
    if not isinstance(genesis, str) or genesis == MAINNET_GENESIS:
        return False
    if is_local_url(url):
        return True
    # Off this computer only the private network is allowed (check_devnet refuses plain http to anything else).
    return bool(settings.get("private_genesis")) and genesis == settings["private_genesis"]


def menu_balance(settings, owner, timeout=MENU_RPC_TIMEOUT):
    """The wallet's SUMO in base units, or None when the network can't answer in time or the link isn't allowed.
    One balance request, no retries, and a hard time limit (the request runs in a helper thread that is simply
    left behind)."""
    result = {}

    def work():
        try:
            if not menu_rpc_allowed(settings) or not menu_chain_ok(settings, timeout):
                return
            program = Pubkey.from_string(settings["program_id"])
            mint = Pubkey.find_program_address([b"mint"], program)[0]
            ata = Pubkey.find_program_address([bytes(owner), bytes(TOKEN_PROGRAM), bytes(mint)], ATA_PROGRAM)[0]
            out = menu_post(settings["rpc"], "getTokenAccountBalance", [str(ata), {"commitment": "confirmed"}], timeout)
            if "result" in out:
                result["units"] = int(out["result"]["value"]["amount"])
            elif "could not find account" in str((out.get("error") or {}).get("message", "")).lower():
                result["units"] = 0      # no token account yet = nothing mined yet
        except Exception:
            pass

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout + 1.0)
    return result.get("units")


def menu_balance_text(units):
    s = fmt_sumo(units)
    if "." not in s:
        s += ".00"
    elif len(s.split(".")[1]) < 2:
        s += "0"
    return s + " SUMO"


def menu_text(settings, keypair_path, cols, rows):
    """The finished picture menu as text, or None when the plain menu should be used instead. Never raises."""
    try:
        if cols < 80 or rows < 30:
            return None
        import sumo_menu
        status, pub = read_public_key(keypair_path)
        if status == "none":
            parts = ("no wallet yet", False, "-", False)
        elif status == "bad":
            parts = ("wallet file unreadable", False, "-", False)
        else:
            units = menu_balance(settings, pub)
            balance = ("offline", False) if units is None else (menu_balance_text(units), True)
            parts = (short(pub), True) + balance
        return sumo_menu.render(VERSION, *parts, selected=1, skip_last_cell=(rows == sumo_menu.ROWS and cols == sumo_menu.COLS))
    except Exception:
        return None


def cmd_menu(args, settings):
    """Draw the picture menu. Exit 0 = drawn; exit 1 (nothing printed) = use the plain menu."""
    text = None
    try:
        if enable_colour(args.plain):
            size = shutil.get_terminal_size(fallback=(0, 0))
            text = menu_text(settings, args.keypair, size.columns, size.lines)
            if text is not None:
                text.encode(sys.stdout.encoding or "ascii")   # a console that can't show it: plain menu
    except KeyboardInterrupt:
        sys.exit(1)             # Ctrl+C while it loads: say nothing, the launcher shows its plain menu
    except Exception:
        text = None
    if text is None:
        sys.exit(1)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception:
        sys.exit(1)


def cmd_pick(args, settings):
    """Wait for a key 1-5 and exit with 10 + that number (11 to 15), for the launcher's menu. Any other
    key is ignored without a sound (the batch file's `choice` beeps). Ctrl+C or any trouble exits 15
    (Exit); the launcher treats every code below 11 (a crash) as Exit too, never as Mine."""
    try:
        while True:
            key = read_key()
            if key and key in "12345":
                sys.exit(10 + int(key))
            if key == "\x03":
                sys.exit(15)
    except (KeyboardInterrupt, Exception):
        sys.exit(15)


def cmd_balance(args, settings):
    chain = Chain(settings)
    kp = load_key(args.keypair)
    print(f"Miner's test wallet {kp.pubkey()}\n  {fmt_sumo(chain.sumo_units(kp.pubkey()))} SUMO\n"
          f"  {chain.sol_balance(kp.pubkey()):.4f} test SOL (for fees)")
    payout = saved_payout(settings)
    if payout and payout != kp.pubkey():
        print(f"Payout address {payout}\n  {fmt_sumo(chain.sumo_units(payout))} SUMO")


def cmd_faucet(args, settings):
    """Ask the test network's faucet for free (worthless) test SOL for fees."""
    chain = Chain(settings)
    kp = load_key(args.keypair)
    if chain.cluster == "devnet" and not is_local_url(chain.url):
        print("On public devnet, use https://faucet.solana.com (choose Devnet). Trying requestAirdrop anyway...")
    amount = int(min(args.sol, 1.0) * UNIT)
    try:
        sig = chain.rpc.call("requestAirdrop", str(kp.pubkey()), amount, {"commitment": "confirmed"})
    except RpcError as e:
        sys.exit(f"Faucet said no: {e}")
    for _ in range(30):
        st = chain.rpc.call("getSignatureStatuses", [sig])["value"][0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            break
        time.sleep(1)
    print(f"Got {amount/UNIT:g} test SOL (worthless). Balance: {chain.sol_balance(kp.pubkey()):.4f} test SOL")


def cmd_new_key(args, settings):
    if os.path.exists(args.keypair):
        sys.exit(f"{os.path.basename(args.keypair)} already exists in this folder, not overwriting it.")
    kp = Keypair()
    # Owner-only (600) from the start, so other accounts on a shared Mac or Linux machine can't
    # read it. On Windows this just makes a normal file.
    fd = os.open(args.keypair, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(list(bytes(kp)), f)
    try:
        os.chmod(args.keypair, 0o600)
    except OSError:
        pass
    print(f"New TEST-NETWORK-ONLY wallet saved to {os.path.basename(args.keypair)}\nAddress: {kp.pubkey()}\n"
          "It only pays the test fees. Never put real money in it. Next: py sumo_miner.py faucet")


def load_key(path):
    if not os.path.exists(path):
        sys.exit(f"No wallet file ({os.path.basename(path)}) in this folder yet. Run: py sumo_miner.py new-key")
    with open(path) as f:
        return Keypair.from_bytes(bytes(json.load(f)))


def set_window_icon():
    """On Windows, use Pixy's frog as the console window / taskbar icon. No-op elsewhere.
    Does not change the miner's console art."""
    if sys.platform != "win32":
        return
    ico = os.path.join(HERE, "sumo.ico")
    if not os.path.isfile(ico):
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        handle = user32.GetConsoleWindow()
        if not handle:
            return
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        LoadImageW = user32.LoadImageW
        LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
        LoadImageW.restype = wintypes.HANDLE
        small = LoadImageW(None, ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        big = LoadImageW(None, ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if big:
            user32.SendMessageW(handle, WM_SETICON, ICON_BIG, big)
        if small:
            user32.SendMessageW(handle, WM_SETICON, ICON_SMALL, small)
    except Exception:
        pass


# Windows drive paths, however they are written: C:\Users\Me\x, C:\\Users\\Me\\x, C:/Users/Me/x, any
# capitals, 8.3 short names (JOSHSM~1). Every folder part is dropped and only the last name is kept.
_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+(?:[^\\/'\"\r\n]+[\\/]+)*")
_UNC_PATH = re.compile(r"(?<![\w:])\\\\+[^\\/'\"\r\n]+[\\/]+(?:[^\\/'\"\r\n]+[\\/]+)*")
_USERS_PATH = re.compile(r"(?i)(?:[\\/]+)(?:users|home)[\\/]+[^\\/'\"\r\n]+[\\/]+(?:[^\\/'\"\r\n]+[\\/]+)*")
_POSIX_PATH = re.compile(r"(?<![\w:/.])(?:/[^/'\"\r\n\s]+)+/")


def scrub_paths(text):
    """Hide this computer's folder names (and the user name inside them) from anything printed.
    The miner's own folder and the user's home folder are matched first, ignoring capitals and
    single/double backslashes or forward slashes; then any other drive, network or home-style
    path is cut down to just its last name."""
    text = str(text)
    for real, label in ((HERE, "<this folder>"), (os.path.expanduser("~"), "~")):
        if real and len(real) > 3:
            pattern = r"[\\/]+".join(re.escape(part) for part in re.split(r"[\\/]+", real) if part)
            if real[:1] in "\\/":
                pattern = r"[\\/]+" + pattern
            text = re.sub(pattern, label, text, flags=re.I)
    for rx in (_DRIVE_PATH, _UNC_PATH, _USERS_PATH, _POSIX_PATH):
        text = rx.sub("", text)
    return text


_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
_IPV6 = re.compile(r"\[[0-9A-Fa-f:.]{2,}\](?::\d+)?")
_IPV6_BARE = re.compile(r"(?<![0-9A-Fa-f:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|"
                        r"(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4})?(?::[0-9A-Fa-f]{1,4}){0,6})(?![0-9A-Fa-f:])")
_HOST = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?::\d+)?\b")


def scrub_network(text, hostnames=False):
    """Hide server addresses (IP:port, [IPv6]:port and, if asked, host names) from a message."""
    text = _IPV4.sub("<server>", _IPV6_BARE.sub("<server>", _IPV6.sub("<server>", str(text))))
    return _HOST.sub("<server>", text) if hostnames else text


def friendly_error(e):
    """One short line for an unexpected error, with no folder names, user name or server address.
    Web errors: the code and reason only. Real file errors: only the file's own name and the reason.
    Anything else is path- and address-scrubbed."""
    if isinstance(e, urllib.error.HTTPError):  # its .filename is the URL: never show it
        return f"HTTP {e.code} {scrub_network(scrub_paths(e.reason or ''), True)}".strip()
    if isinstance(e, urllib.error.URLError):
        return f"{type(e).__name__}: {scrub_network(scrub_paths(e.reason), True)}"
    if isinstance(e, OSError) and (e.filename or e.filename2):
        names = [os.path.basename(str(n).replace("\\", "/").rstrip("/")) or "?" for n in (e.filename, e.filename2) if n]
        reason = scrub_paths(e.strerror or type(e).__name__)
        return f"{type(e).__name__}: {reason} ({' -> '.join(names)})"
    return f"{type(e).__name__}: {scrub_network(scrub_paths(e))}"


def main():
    try:
        _main()
    except KeyboardInterrupt:
        if sys.argv[1:2] == ["menu"]:
            sys.exit(1)      # the picture menu says nothing: the launcher then shows its plain menu
        # Ctrl+C anywhere (also during start-up or a network call): a friendly stop, not a traceback.
        print("\n  Stopped (Ctrl+C). Nothing is lost. You can start mining again whenever you like.", flush=True)
    except SystemExit:
        raise
    except Exception as e:
        # No Python traceback on screen: it would show full file paths (and the Windows user name).
        # Set SUMO_DEBUG=1 to see the full traceback when reporting a bug.
        if os.environ.get("SUMO_DEBUG"):
            raise
        print(f"\n  Something went wrong: {friendly_error(e)}\n"
              "  If it keeps happening, tell the person who sent you the miner what this message says.",
              file=sys.stderr, flush=True)
        sys.exit(1)


def _main():
    set_window_icon()
    # allow_abbrev=False: "--ye" or "--y" must NOT quietly mean "--yes" (which skips the y/N questions).
    ap = argparse.ArgumentParser(description="Sumo Frog miner (test networks only, worthless test coins)",
                                 allow_abbrev=False)
    ap.add_argument("command", choices=["mine", "status", "balance", "new-key", "faucet", "set-payout", "withdraw", "menu", "pick"])
    ap.add_argument("address", nargs="?", help="for set-payout or withdraw: your wallet's PUBLIC address (set-payout also takes 'none')")
    ap.add_argument("--keypair", default=os.path.join(HERE, "sumo-devnet-key.json"),
                    help="the miner's own test wallet file (pays the test fees)")
    ap.add_argument("--payout", help="send rewards to this PUBLIC wallet address ('self' = the miner's own wallet)")
    ap.add_argument("--workers", type=int, default=0, help="CPU processes (default: all cores)")
    ap.add_argument("--blocks", type=int, default=0, help="stop after N blocks (default: keep going)")
    ap.add_argument("--plain", action="store_true", help="plain text, no colours or pixel art")
    ap.add_argument("--yes", action="store_true", help="for set-payout and withdraw: don't ask to confirm")
    ap.add_argument("--sumo", action="store_true", help="for withdraw: also send the miner wallet's SUMO")
    ap.add_argument("--rpc", help="override RPC URL (devnet, localhost or the private Sumo network only)")
    ap.add_argument("--sol", type=float, default=1.0, help="faucet amount in test SOL (max 1)")
    args = ap.parse_args()
    if args.command == "pick":  # the launcher's menu key: needs no settings, so a missing or broken config can't close the window
        with quiet_console_input():
            cmd_pick(args, None)
    settings = load_settings()
    if args.rpc:
        settings["rpc"] = args.rpc
    run = {"mine": cmd_mine, "status": cmd_status, "balance": cmd_balance, "new-key": cmd_new_key,
           "faucet": cmd_faucet, "set-payout": cmd_set_payout, "withdraw": cmd_withdraw,
           "menu": cmd_menu}[args.command]
    run(args, settings)


if __name__ == "__main__":
    mp.freeze_support()
    main()
