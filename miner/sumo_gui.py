#!/usr/bin/env python3
"""Sumo Frog windowed miner for Windows (Solana devnet only, worthless test coins).

A simple Start/Stop window over the existing miner logic. The local test wallet
stays on this PC and is never sent anywhere. There is no tip or developer fee:
all mined SUMO goes to the local test wallet, or to an optional public payout
address you paste.

Never paste a seed phrase or private key into this app.
"""
import json
import multiprocessing as mp
import os
import queue
import sys
import threading
import webbrowser

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

import sumo_miner as m

VERSION = "v0.7.0"
PUBLIC_DEVNET_RPC = "https://api.devnet.solana.com"
FAUCET_URL = "https://faucet.solana.com"
WALLET_NAME = "sumo-devnet-key.json"
PAYOUT_NAME = "payout-address.txt"
MIN_TEST_SOL = 0.003

# High-contrast dark palette (game-launcher). Status is always written in words, not colour alone.
BG = "#0B0720"
BG_RAISED = "#14102C"
BG_CARD = "#1A1638"
BG_STAGE = "#090616"
FG = "#F5F2FF"
SUB = "#DCD6F5"
MUTED = "#C8C0E6"
BORDER = "#3E3860"
ACCENT = "#FF3EA5"
GOLD = "#FFC247"
ENTRY_BG = "#0F0C22"
HERO_START_BG = "#F5F2FF"
HERO_START_FG = "#0B0720"
HERO_STOP_BG = "#1A1638"
HERO_STOP_FG = "#F5F2FF"


def bundled_dir():
    """Files shipped with the app (settings, icons). Inside the PyInstaller folder when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir():
    """Where the local wallet and payout file live: next to the .exe, or the miner folder.
    Override with SUMO_GUI_HOME for tests. Never a remote path."""
    override = os.environ.get("SUMO_GUI_HOME")
    if override:
        return os.path.abspath(override)
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def wallet_path():
    return os.path.join(user_data_dir(), WALLET_NAME)


def payout_path():
    return os.path.join(user_data_dir(), PAYOUT_NAME)


def load_gui_settings():
    """Public Solana devnet only. Never reads the private test-network config."""
    names = (
        "sumo_config.devnet.json",
        os.path.join("devnet", "sumo_config.devnet.json"),
        "sumo_config.example.json",
    )
    data = None
    for name in names:
        path = os.path.join(bundled_dir(), name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            break
    if not isinstance(data, dict):
        raise SystemExit("The miner is missing its devnet settings file. Re-download the miner.")
    data["network"] = "devnet"
    data["devnet_rpc"] = PUBLIC_DEVNET_RPC
    data.pop("rpc", None)
    data.pop("private_genesis", None)
    data.pop("payout", None)
    settings = m.apply_network(data)
    if settings.get("network") != "devnet" or settings.get("rpc") != PUBLIC_DEVNET_RPC:
        raise SystemExit("The windowed miner only runs on public Solana devnet. Stopping.")
    if settings.get("private_genesis"):
        raise SystemExit("The windowed miner only runs on public Solana devnet. Stopping.")
    return settings


def create_or_load_wallet(path):
    """Load the local test wallet, or create one once. Never overwrites an existing file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        return m.load_key(path), False
    m.cmd_new_key(type("Args", (), {"keypair": path})(), None)
    return m.load_key(path), True


def read_saved_payout(settings):
    path = payout_path()
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text or text.lower() == "none":
        return None
    return m.parse_payout(text, settings, "Your saved payout address can't be used. Clear it and paste a PUBLIC address.")


def write_saved_payout(pk):
    path = payout_path()
    if pk is None:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(pk) + "\n")


def payout_confirm_text(pk):
    """Yes/Cancel dialog body. Always includes the full public address."""
    return (
        "Rewards will go to this PUBLIC address from the next block:\n\n"
        f"{pk}\n\n"
        "Check every character. The local test wallet still pays the fees.\n"
        "There is no tip or developer fee.\n\n"
        "Save this address?"
    )


def try_parse_payout(text, settings):
    """Return (pubkey, None) or (None, reason). Never accepts a seed phrase or private key."""
    try:
        return m.parse_payout(text, settings, "Nothing was saved."), None
    except SystemExit as e:
        return None, e.code if isinstance(e.code, str) else "That address could not be used."


def run_mining(settings, key_path, payout, workers, stop_event, on_status, on_event):
    """Mine on public devnet until Stop is pressed. Rewards go to payout or the local wallet.
    The local wallet pays the test-network fees. There is no tip or developer fee."""
    chain = m.Chain(settings)
    if chain.cluster != "devnet":
        raise SystemExit("The windowed miner only runs on Solana devnet. Stopping.")
    kp = m.load_key(key_path)
    if payout is not None and payout == kp.pubkey():
        payout = None
    if payout is not None:
        if payout in (chain.program, chain.config, chain.mint):
            raise SystemExit("Your payout address is a Sumo Frog program address, not a wallet.")
        m.check_wallet_account(chain, payout, "Not mining.")
    earner = payout or kp.pubkey()
    if chain.sol_balance(kp.pubkey()) < MIN_TEST_SOL:
        raise SystemExit(
            f"Your test wallet {kp.pubkey()} needs a little test SOL for fees (about 0.003).\n"
            "Click Open devnet faucet, pick Devnet, paste your wallet address, "
            "then click Start mining again."
        )
    workers = workers or os.cpu_count() or 1
    mined, rates, sending = 0, [], False
    on_event(f"Mining on devnet with {workers} CPU workers. All mined SUMO goes to the reward wallet. No tip or developer fee.")

    def publish(hud):
        on_status(dict(hud))

    try:
        while not stop_event.is_set():
            st = chain.state()
            if st["next_reward"] <= 0:
                on_event("Max supply reached. Nothing left to mine.")
                break
            hud = dict(
                state="MINING",
                block=st["blocks_mined"] + 1,
                rate="--",
                guesses=0,
                diff=f"{m.difficulty_bits(st['target']):.1f} BITS",
                reward=m.fmt_sumo(st["next_reward"]) + " SUMO",
                mined=mined,
                balance=m.fmt_sumo(chain.sumo_units(earner)),
                sol=chain.sol_balance(kp.pubkey()),
                halving=st["blocks_to_halving"],
                pays_to=str(earner),
                workers=workers,
                reward_won="",
            )
            publish(hud)

            def tick(hashes, rate, _hud=hud):
                if stop_event.is_set():
                    raise KeyboardInterrupt
                _hud.update(guesses=hashes, rate=m.rate_text(rate), state="MINING")
                publish(_hud)

            guess, hashes, el = m.grind(chain, earner, st, workers, tick)
            if stop_event.is_set():
                break
            if el > 1 and hashes:
                rates.append(hashes / el)
            if guess == "moved" or guess is None:
                on_event(f"Block #{m.fmt_int(st['blocks_mined'] + 1)} went to another frog. On to the next one.")
                continue
            m.send_started.clear()
            try:
                # payout=None uses mine (credit the local wallet). A public payout uses mine_to.
                # The fee payer is always the local wallet. No other address receives a cut.
                chain.submit(kp, st["challenge"], guess, payout)
            except KeyboardInterrupt:
                sending = m.send_started.is_set()
                raise
            except m.RpcError as e:
                code = e.custom_code()
                if code == 6002:
                    on_event("Another miner got there first. On to the next block.")
                else:
                    on_event(f"Block refused: {m.ERRORS.get(code, e)}")
                continue
            mined += 1
            won = m.fmt_sumo(st["next_reward"]) + " SUMO"
            hud.update(
                mined=mined,
                balance=m.fmt_sumo(chain.sumo_units(earner)),
                sol=chain.sol_balance(kp.pubkey()),
                reward_won=won,
                state="BLOCK FOUND",
            )
            publish(hud)
            on_event(
                f"BLOCK FOUND! #{m.fmt_int(st['blocks_mined'] + 1)}  +{won} after "
                f"{m.fmt_int(hashes)} guesses ({m.secs_text(el)}). "
                "All of that SUMO went to the reward wallet. No tip or developer fee."
            )
    except KeyboardInterrupt:
        pass
    if sending:
        on_event("Stopped while sending. It may still go through. Check the SUMO balance before trying again. (The last block was being sent.)")
    elif rates:
        on_event(f"Stopped. Mined {mined} block(s) this session. Average {sum(rates)/len(rates)/1e6:.2f} MH/s.")
    else:
        on_event("Stopped.")
    on_status({"state": "STOPPED", "rate": "--"})


# ======================= look: dark game-launcher =======================
# Nothing below changes mining, the wallet, the payout rules or the network guard.

def branding_dir():
    return os.path.join(bundled_dir(), "branding")


# Caps on drop-in animation so a huge pack cannot freeze the window.
MAX_SPRITE_FRAMES = 48
MAX_SPRITE_FILE_BYTES = 2 * 1024 * 1024
MAX_SPRITE_EDGE = 1024
MAX_SPRITE_PIXELS = 1024 * 1024


def sprite_frames_dir():
    """Pixy's animated frog drops in here only (frog.gif, or frame_001.png, ...)."""
    return os.path.join(branding_dir(), "sprites")


def sprite_file_ok(path):
    """True when the file exists and is within the size cap."""
    try:
        return os.path.isfile(path) and 0 < os.path.getsize(path) <= MAX_SPRITE_FILE_BYTES
    except OSError:
        return False


def sprite_image_ok(size):
    """True when a frame's pixel size is within the cap."""
    try:
        w, h = size
    except (TypeError, ValueError):
        return False
    return w > 0 and h > 0 and w <= MAX_SPRITE_EDGE and h <= MAX_SPRITE_EDGE and (w * h) <= MAX_SPRITE_PIXELS


def find_sprite_source(folder):
    """('gif', path), ('frames', [paths]) or (None, None).
    Only files in this folder that pass the size cap; at most MAX_SPRITE_FRAMES frames."""
    if not os.path.isdir(folder):
        return None, None
    names = sorted(os.listdir(folder))

    def ok(name):
        return sprite_file_ok(os.path.join(folder, name))

    if "frog.gif" in names and ok("frog.gif"):
        return "gif", os.path.join(folder, "frog.gif")
    gifs = [n for n in names if n.lower().endswith(".gif") and ok(n)]
    if gifs:
        return "gif", os.path.join(folder, gifs[0])
    frames = [n for n in names if n.lower().endswith(".png")
              and (n.lower().startswith("frame_") or n.lower().startswith("frog_"))
              and ok(n)]
    frames = frames[:MAX_SPRITE_FRAMES]
    if frames:
        return "frames", [os.path.join(folder, n) for n in frames]
    return None, None


def _load_private_fonts():
    """Use the bundled fonts on Windows without installing them for the whole PC."""
    fonts = os.path.join(branding_dir(), "fonts")
    if sys.platform != "win32" or not os.path.isdir(fonts):
        return
    try:
        import ctypes
        FR_PRIVATE = 0x10
        for name in os.listdir(fonts):
            if name.lower().endswith(".ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(fonts, name), FR_PRIVATE, 0)
    except Exception:
        pass


def _pick_family(root, wanted, fallback):
    try:
        families = {f.lower(): f for f in tkfont.families(root)}
    except Exception:
        families = {}
    for name in wanted:
        if name.lower() in families:
            return families[name.lower()]
    return fallback


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, splinesteps=24, **kw)



def _punch_dark_background(im):
    """Make the navy ground around the pixel frog transparent, keeping black eye pixels."""
    im = im.convert("RGBA")
    pix = im.load()
    w, h = im.size
    bg = pix[0, 0]
    def near(p):
        return all(abs(p[i] - bg[i]) < 22 for i in range(3)) and p[3] > 0
    from collections import deque
    seen, q = set(), deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        if near(pix[x, y]):
            pix[x, y] = (0, 0, 0, 0)
            q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return im


class RoundButton(tk.Canvas):
    """A rounded, high-contrast button. The label text always says what it does."""

    def __init__(self, parent, text, command, font, bg, fg, outline, width=200, height=44,
                 radius=14, parent_bg=BG):
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._cmd, self._font = command, font
        self._bw, self._bh, self._rad = width, height, radius
        self._enabled = True
        self._hover = False
        self.set_style(text, bg, fg, outline)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Configure>", self._resize)

    def set_style(self, text, bg, fg, outline):
        self._text, self._bg, self._fg, self._outline = text, bg, fg, outline
        self._draw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.config(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def _resize(self, e):
        if e.width > 4 and e.height > 4:
            self._bw, self._bh = e.width, e.height
            self._draw()

    def _click(self, _e):
        if self._enabled and self._cmd:
            self._cmd()

    def _draw(self):
        self.delete("all")
        w, h, r = self._bw, self._bh, self._rad
        outline_w = 3 if (self._hover and self._enabled) else 2
        fill = self._bg if self._enabled else BG_CARD
        text_fg = self._fg if self._enabled else MUTED
        line = self._outline if self._enabled else BORDER
        _round_rect(self, 2, 2, w - 2, h - 2, r, fill=fill, outline=line, width=outline_w)
        self.create_text(w // 2, h // 2, text=self._text, fill=text_fg, font=self._font)

    def cget_text(self):
        return self._text


class MinerApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_gui_settings()
        self.bus = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.kp = None
        self.payout = None
        self.created_wallet = False
        self._copy_reset = None
        self._images = {}
        self._sprite = []
        self._sprite_i = 0
        self._sprite_job = None
        self._details_open = False

        _load_private_fonts()
        root.title(f"SUMO Frog miner {VERSION}")
        root.configure(bg=BG)
        self._set_icon()
        self._fonts()
        self._build()
        root.update_idletasks()
        req_w = max(root.winfo_reqwidth(), 840)
        req_h = root.winfo_reqheight() + 8
        root.geometry(f"{req_w}x{req_h}")
        root.minsize(780, min(req_h, 640))
        self._load_wallet()
        self._load_payout()
        self._set_state("STOPPED", "Ready. Test coins only on Solana devnet.")
        self._start_sprite()
        root.after(100, self._drain)
        self._maybe_screenshot()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- look ----------
    def _set_icon(self):
        for name in ("sumo_coin.ico", "sumo.ico"):
            path = os.path.join(bundled_dir(), name)
            if os.path.isfile(path):
                try:
                    self.root.iconbitmap(path)
                    return
                except Exception:
                    continue
        logo = self._photo("sumo_logo.png", 64)
        if logo is not None:
            try:
                self.root.iconphoto(True, logo)
            except Exception:
                pass

    def _fonts(self):
        body = _pick_family(self.root, ("Outfit", "Segoe UI Variable Text", "Segoe UI", "Inter", "DejaVu Sans"), "TkDefaultFont")
        pixel = _pick_family(self.root, ("Press Start 2P",), body)
        mono = _pick_family(self.root, ("Cascadia Mono", "Consolas", "IBM Plex Mono", "DejaVu Sans Mono"), "TkFixedFont")
        self.f = {
            "brand": tkfont.Font(family=pixel, size=16),
            "pixel_sm": tkfont.Font(family=pixel, size=8),
            "status": tkfont.Font(family=body, size=22, weight="bold"),
            "status_sub": tkfont.Font(family=body, size=12),
            "hero": tkfont.Font(family=body, size=19, weight="bold"),
            "card_label": tkfont.Font(family=body, size=11, weight="bold"),
            "card_value": tkfont.Font(family=body, size=21, weight="bold"),
            "body": tkfont.Font(family=body, size=12),
            "body_b": tkfont.Font(family=body, size=12, weight="bold"),
            "small": tkfont.Font(family=body, size=11),
            "btn": tkfont.Font(family=body, size=12, weight="bold"),
            "mono": tkfont.Font(family=mono, size=11),
        }

    def _photo(self, name, size, punch_bg=False):
        key = (name, size, punch_bg)
        if key in self._images:
            return self._images[key]
        path = os.path.join(branding_dir(), name)
        if not os.path.isfile(path):
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(path).convert("RGBA")
            if punch_bg:
                im = _punch_dark_background(im)
            im = im.resize((size, size), Image.NEAREST)
            photo = ImageTk.PhotoImage(im)
        except Exception:
            try:
                photo = tk.PhotoImage(file=path)
                factor = max(1, photo.width() // size)
                photo = photo.subsample(factor, factor)
            except Exception:
                return None
        self._images[key] = photo
        return photo

    def _label(self, parent, text="", font="body", fg=FG, bg=BG, **kw):
        return tk.Label(parent, text=text, font=self.f[font], fg=fg, bg=bg, **kw)

    # ---------- layout ----------
    def _build(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=24, pady=18)

        # Header: coin logo, pixel title, short promise
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        logo = self._photo("sumo_logo.png", 56)
        if logo is not None:
            tk.Label(head, image=logo, bg=BG).pack(side="left", padx=(0, 14))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", fill="x", expand=True)
        self._label(titles, "SUMO FROG", "brand", fg=FG).pack(anchor="w", pady=(4, 6))
        self._label(titles, "Miner  ·  Solana devnet  ·  test coins only", "small", fg=SUB).pack(anchor="w")
        badge = tk.Frame(head, bg=BG_RAISED, highlightbackground=BORDER, highlightthickness=1)
        badge.pack(side="right", anchor="n")
        self._label(badge, f"{VERSION}  ·  NO FEES", "pixel_sm", fg=FG, bg=BG_RAISED, padx=10, pady=8).pack()

        # Stage: frog sprite on the left, big status and hero button on the right
        stage = tk.Frame(outer, bg=BG_STAGE, highlightbackground=BORDER, highlightthickness=1)
        stage.pack(fill="x", pady=(18, 14))
        inner = tk.Frame(stage, bg=BG_STAGE)
        inner.pack(fill="x", padx=22, pady=20)

        sprite_col = tk.Frame(inner, bg=BG_STAGE)
        sprite_col.pack(side="left", padx=(4, 28))
        self.sprite_label = tk.Label(sprite_col, bg=BG_STAGE, bd=0)
        self.sprite_label.pack()
        self._label(sprite_col, "A little frog animation will live here soon",
                    "small", fg=MUTED, bg=BG_STAGE).pack(pady=(8, 0))

        right = tk.Frame(inner, bg=BG_STAGE)
        right.pack(side="left", fill="both", expand=True, pady=8)
        self.status_var = tk.StringVar(value="STATUS: STOPPED")
        self.status_label = tk.Label(right, textvariable=self.status_var, font=self.f["status"],
                                     fg=FG, bg=BG_STAGE, anchor="w")
        self.status_label.pack(anchor="w")
        self.status_sub_var = tk.StringVar(value="Press Start to mine $SUMO. All of it is yours.")
        tk.Label(right, textvariable=self.status_sub_var, font=self.f["status_sub"], fg=SUB,
                 bg=BG_STAGE, anchor="w", justify="left", wraplength=470).pack(anchor="w", pady=(4, 16))
        self.hero = RoundButton(right, "▶  START MINING", self._toggle, self.f["hero"],
                                HERO_START_BG, HERO_START_FG, FG, width=330, height=66,
                                radius=30, parent_bg=BG_STAGE)
        self.hero.pack(anchor="w", fill="x", pady=(4, 0))
        # Kept for tests and keyboard users: the same actions as the hero button.
        self.start_btn = self.hero
        self.stop_btn = self.hero
        self.root.bind("<space>", lambda e: self._toggle_from_key(e))

        # Stat cards
        cards = tk.Frame(outer, bg=BG)
        cards.pack(fill="x")
        self.stat_vars = {
            "hash": tk.StringVar(value="--"),
            "blocks": tk.StringVar(value="0"),
            "balance": tk.StringVar(value="--"),
            "sol": tk.StringVar(value="--"),
        }
        for i, (key, label, hint) in enumerate((
            ("hash", "HASH RATE", "guesses per second"),
            ("blocks", "BLOCKS FOUND", "this session"),
            ("balance", "SUMO BALANCE", "reward wallet"),
            ("sol", "TEST SOL", "pays the fees"),
        )):
            card = tk.Frame(cards, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            self._label(card, label, "card_label", fg=SUB, bg=BG_CARD).pack(anchor="w", padx=14, pady=(12, 2))
            tk.Label(card, textvariable=self.stat_vars[key], font=self.f["card_value"], fg=FG,
                     bg=BG_CARD, anchor="w").pack(anchor="w", padx=14)
            self._label(card, hint, "small", fg=MUTED, bg=BG_CARD).pack(anchor="w", padx=14, pady=(0, 12))
            cards.columnconfigure(i, weight=1, uniform="cards")

        # Secondary line: guess # and network details, in plain words
        self.detail_var = tk.StringVar(value="Guess #: 0   ·   Block: --   ·   Difficulty: --   ·   Reward: --")
        self.guess_var = tk.StringVar(value="Guess #: 0")
        tk.Label(outer, textvariable=self.detail_var, font=self.f["small"], fg=SUB, bg=BG,
                 anchor="w").pack(fill="x", pady=(10, 0))

        # Collapsible "Wallet & payout"
        self.details_btn = RoundButton(outer, "+  Wallet & payout", self._toggle_details, self.f["btn"],
                                       BG_RAISED, FG, BORDER, width=230, height=40, radius=12, parent_bg=BG)
        self.details_btn.pack(anchor="w", pady=(14, 0))
        self.details = tk.Frame(outer, bg=BG_RAISED, highlightbackground=BORDER, highlightthickness=1)
        self._build_details(self.details)

        # Activity log
        self.log_title = self._label(outer, "ACTIVITY", "card_label", fg=SUB)
        self.log_title.pack(anchor="w", pady=(14, 6))
        logf = tk.Frame(outer, bg=BG_RAISED, highlightbackground=BORDER, highlightthickness=1, height=118)
        logf.pack(fill="x", expand=False, pady=(0, 4))
        logf.pack_propagate(False)
        self.message = tk.Text(logf, height=3, font=self.f["small"], bg=BG_RAISED, fg=FG,
                               relief="flat", bd=0, highlightthickness=0,
                               wrap="word", state="disabled", padx=12, pady=8, insertbackground=FG)
        self.message.pack(fill="both", expand=True)

    def _build_details(self, box):
        pad = tk.Frame(box, bg=BG_RAISED)
        pad.pack(fill="x", padx=16, pady=14)

        self._label(pad, "YOUR TEST WALLET", "card_label", fg=SUB, bg=BG_RAISED).pack(anchor="w")
        self._label(pad, "Saved only on this PC. Never uploaded. It pays the tiny devnet fees.",
                    "small", fg=MUTED, bg=BG_RAISED).pack(anchor="w", pady=(2, 6))
        row = tk.Frame(pad, bg=BG_RAISED)
        row.pack(fill="x")
        self.address_var = tk.StringVar(value="(no wallet yet)")
        self.address_entry = tk.Entry(row, textvariable=self.address_var, font=self.f["mono"],
                                      fg=FG, bg=ENTRY_BG, readonlybackground=ENTRY_BG, relief="flat",
                                      highlightthickness=1, highlightbackground=BORDER, highlightcolor=FG)
        self.address_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.address_entry.config(state="readonly")
        self.copy_btn = RoundButton(row, "Copy address", self._copy_address, self.f["btn"],
                                    FG, BG, FG, width=150, height=38, radius=12, parent_bg=BG_RAISED)
        self.copy_btn.pack(side="left", padx=(10, 0))
        frow = tk.Frame(pad, bg=BG_RAISED)
        frow.pack(fill="x", pady=(10, 0))
        RoundButton(frow, "Get test SOL  ↗", self._open_faucet, self.f["btn"],
                    BG_CARD, FG, FG, width=170, height=38, radius=12, parent_bg=BG_RAISED).pack(side="left")
        self._label(frow, "Opens the devnet faucet and copies your address.", "small",
                    fg=MUTED, bg=BG_RAISED).pack(side="left", padx=(12, 0))

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=14)

        self._label(pad, "PAYOUT ADDRESS  (OPTIONAL)", "card_label", fg=SUB, bg=BG_RAISED).pack(anchor="w")
        self._label(pad, "Paste your own wallet's PUBLIC address to get your SUMO there.\n"
                         "NEVER paste a seed phrase or private key.",
                    "small", fg=MUTED, bg=BG_RAISED, justify="left").pack(anchor="w", pady=(2, 6))
        self.payout_entry = tk.Entry(pad, font=self.f["mono"], fg=FG, bg=ENTRY_BG, insertbackground=FG,
                                     relief="flat", highlightthickness=1, highlightbackground=BORDER,
                                     highlightcolor=FG)
        self.payout_entry.pack(fill="x", ipady=7)
        brow = tk.Frame(pad, bg=BG_RAISED)
        brow.pack(fill="x", pady=(10, 0))
        RoundButton(brow, "Save payout", self._save_payout, self.f["btn"], FG, BG, FG,
                    width=150, height=38, radius=12, parent_bg=BG_RAISED).pack(side="left")
        RoundButton(brow, "Use test wallet", self._clear_payout, self.f["btn"], BG_CARD, FG, FG,
                    width=170, height=38, radius=12, parent_bg=BG_RAISED).pack(side="left", padx=(10, 0))
        self.reward_var = tk.StringVar(value="Rewards go to: your test wallet. No tip or developer fee.")
        tk.Label(pad, textvariable=self.reward_var, font=self.f["small"], fg=FG, bg=BG_RAISED,
                 anchor="w", justify="left", wraplength=700).pack(fill="x", pady=(10, 0))

    def _toggle_details(self, force=None):
        self._details_open = (not self._details_open) if force is None else bool(force)
        if self._details_open:
            self.details.pack(fill="x", pady=(8, 0), after=self.details_btn)
            self.details_btn.set_style("–  Wallet & payout", BG_RAISED, FG, FG)
            self.root.geometry("")
        else:
            self.details.pack_forget()
            self.details_btn.set_style("+  Wallet & payout", BG_RAISED, FG, BORDER)

    # ---------- frog sprite (placeholder until Pixy's frames arrive) ----------
    def _start_sprite(self, size=188):
        kind, src = find_sprite_source(sprite_frames_dir())
        frames = []
        try:
            from PIL import Image, ImageSequence, ImageTk
            if kind == "gif":
                gif = Image.open(src)
                if sprite_image_ok(gif.size):
                    for i, fr in enumerate(ImageSequence.Iterator(gif)):
                        if i >= MAX_SPRITE_FRAMES:
                            break
                        if sprite_image_ok(fr.size):
                            frames.append(ImageTk.PhotoImage(fr.convert("RGBA").resize((size, size), Image.NEAREST)))
            elif kind == "frames":
                for pth in src[:MAX_SPRITE_FRAMES]:
                    im = Image.open(pth)
                    if sprite_image_ok(im.size):
                        frames.append(ImageTk.PhotoImage(im.convert("RGBA").resize((size, size), Image.NEAREST)))
        except Exception:
            frames = []
        if not frames:
            still = self._photo("sumo_frog.png", size, punch_bg=True)
            frames = [still] if still is not None else []
        self._sprite = frames
        if frames:
            self.sprite_label.config(image=frames[0])
        if len(frames) > 1:
            self._animate_sprite()

    def _animate_sprite(self):
        if not self._sprite:
            return
        self._sprite_i = (self._sprite_i + 1) % len(self._sprite)
        self.sprite_label.config(image=self._sprite[self._sprite_i])
        delay = 110 if self._busy() else 260
        self._sprite_job = self.root.after(delay, self._animate_sprite)

    # ---------- messages ----------
    def _log(self, text):
        self.message.config(state="normal")
        self.message.insert("end", "›  " + text.rstrip() + "\n")
        self.message.see("end")
        self.message.config(state="disabled")

    def _set_state(self, state, note=None):
        self.status_var.set("STATUS: " + state)
        subs = {
            "STOPPED": "Press Start to mine $SUMO. All of it is yours.",
            "STARTING": "Connecting to Solana devnet…",
            "MINING": "Your PC is making guesses. Leave this window open.",
            "STOPPING": "Finishing this batch of guesses…",
        }
        if state in subs:
            self.status_sub_var.set(subs[state])
        if note:
            self._log(note)

    # ---------- wallet & payout (same rules as before) ----------
    def _load_wallet(self):
        try:
            self.kp, self.created_wallet = create_or_load_wallet(wallet_path())
        except SystemExit as e:
            self.address_var.set("(wallet could not be opened)")
            self._log(e.code if isinstance(e.code, str) else "The wallet file could not be opened.")
            return
        except Exception as e:
            self.address_var.set("(wallet could not be opened)")
            self._log("The wallet file could not be opened: " + m.friendly_error(e))
            return
        self.address_var.set(str(self.kp.pubkey()))
        if self.created_wallet:
            self._log("Made a new test wallet on this PC. Keep " + WALLET_NAME + " private.")
        self._update_reward_line()

    def _load_payout(self):
        if self.kp is None:
            return
        try:
            self.payout = read_saved_payout(self.settings)
        except SystemExit as e:
            self.payout = None
            self._log(e.code if isinstance(e.code, str) else "The saved payout address could not be used.")
            return
        if self.payout:
            self.payout_entry.delete(0, "end")
            self.payout_entry.insert(0, str(self.payout))
        self._update_reward_line()

    def _short(self, pk):
        s = str(pk)
        return s[:6] + "…" + s[-6:]

    def _update_reward_line(self):
        if self.payout is not None:
            self.reward_var.set("Rewards go to: your payout address " + self._short(self.payout)
                                + ". The test wallet pays fees. No tip or developer fee.")
        elif self.kp is not None:
            self.reward_var.set("Rewards go to: your test wallet " + self._short(self.kp.pubkey())
                                + ". No tip or developer fee.")
        else:
            self.reward_var.set("Rewards go to: your test wallet. No tip or developer fee.")

    def _copy_address(self, also_log=True):
        addr = self.address_var.get()
        if not addr or addr.startswith("("):
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(addr)
        self.root.update_idletasks()
        self.copy_btn.set_style("Copied ✓", FG, BG, FG)
        if self._copy_reset:
            self.root.after_cancel(self._copy_reset)
        self._copy_reset = self.root.after(2000, lambda: self.copy_btn.set_style("Copy address", FG, BG, FG))
        if also_log:
            self._log("Address copied.")
        return True

    def _open_faucet(self):
        self._copy_address(also_log=False)
        webbrowser.open(FAUCET_URL)
        self._log("Opened the faucet and copied your address. Pick Devnet, paste it, request SOL.")

    def _save_payout(self):
        text = self.payout_entry.get().strip()
        if not text:
            self._log("Paste a PUBLIC address first, or click Use test wallet.")
            return
        pk, err = try_parse_payout(text, self.settings)
        if err:
            messagebox.showerror("Payout address not saved", err, parent=self.root)
            self._log(err)
            return
        if self.kp is not None and pk == self.kp.pubkey():
            self._clear_payout()
            return
        if not messagebox.askyescancel(
            "Save payout address?",
            payout_confirm_text(pk),
            parent=self.root,
        ):
            self._log("Payout not saved.")
            return
        write_saved_payout(pk)
        self.payout = pk
        self.payout_entry.delete(0, "end")
        self.payout_entry.insert(0, str(pk))
        self._update_reward_line()
        self._log("Payout saved. From the next block your SUMO goes there.")

    def _clear_payout(self):
        write_saved_payout(None)
        self.payout = None
        self.payout_entry.delete(0, "end")
        self._update_reward_line()
        self._log("Payout cleared. Rewards stay in your test wallet.")

    # ---------- mining ----------
    def _busy(self):
        return self.worker is not None and self.worker.is_alive()

    def _toggle_from_key(self, e):
        if isinstance(e.widget, tk.Entry):
            return
        self._toggle()

    def _toggle(self):
        if self._busy():
            self._stop()
        else:
            self._start()

    def _hero_mining(self, mining):
        if mining:
            self.hero.set_style("■  STOP MINING", HERO_STOP_BG, HERO_STOP_FG, FG)
        else:
            self.hero.set_style("▶  START MINING", HERO_START_BG, HERO_START_FG, FG)

    def _start(self):
        if self._busy():
            return
        if self.kp is None:
            self._log("There is no test wallet yet, so mining can't start.")
            return
        self.stop_event.clear()
        self._hero_mining(True)
        self._set_state("STARTING", "Starting the miner…")
        payout = self.payout
        key = wallet_path()
        settings = self.settings

        def work():
            try:
                run_mining(
                    settings, key, payout, 0, self.stop_event,
                    on_status=lambda hud: self.bus.put(("status", hud)),
                    on_event=lambda msg: self.bus.put(("event", msg)),
                )
            except SystemExit as e:
                msg = e.code if isinstance(e.code, str) else "Mining could not start."
                self.bus.put(("error", msg))
            except Exception as e:
                self.bus.put(("error", "Something went wrong: " + m.friendly_error(e)))
            finally:
                self.bus.put(("done", None))

        self.worker = threading.Thread(target=work, name="sumo-mine", daemon=True)
        self.worker.start()
        if self._sprite_job is None and len(self._sprite) > 1:
            self._animate_sprite()

    def _stop(self):
        if not self._busy():
            return
        self.stop_event.set()
        self.hero.set_enabled(False)
        self._set_state("STOPPING", "Stopping…")

    def _apply_status(self, hud):
        state = hud.get("state") or "MINING"
        if hud.get("reward_won") and state == "BLOCK FOUND":
            self.status_var.set("STATUS: BLOCK FOUND  +" + hud["reward_won"])
            self.status_sub_var.set("Nice! That SUMO is yours. Still mining…")
        else:
            self._set_state(state)
        if "rate" in hud:
            self.stat_vars["hash"].set(str(hud["rate"]))
        if "guesses" in hud:
            self.guess_var.set("Guess #: " + m.fmt_int(hud["guesses"]))
        if "mined" in hud:
            self.stat_vars["blocks"].set(m.fmt_int(hud["mined"]))
        if "balance" in hud:
            self.stat_vars["balance"].set(str(hud["balance"]))
        if "sol" in hud:
            self.stat_vars["sol"].set(f"{hud['sol']:.4f}")
        parts = [self.guess_var.get()]
        if "block" in hud:
            self._last_block = "Block: " + m.fmt_int(hud["block"])
        if "diff" in hud:
            self._last_diff = "Difficulty: " + str(hud["diff"])
        if "reward" in hud:
            self._last_reward = "Reward: " + str(hud["reward"])
        parts += [getattr(self, "_last_block", "Block: --"), getattr(self, "_last_diff", "Difficulty: --"),
                  getattr(self, "_last_reward", "Reward: --")]
        self.detail_var.set("   ·   ".join(parts))

    def _drain(self):
        try:
            while True:
                kind, payload = self.bus.get_nowait()
                if kind == "status":
                    self._apply_status(payload)
                elif kind == "event":
                    self._log(payload)
                    if str(payload).startswith("Stopped"):
                        self._set_state("STOPPED")
                elif kind == "error":
                    if "needs a little test SOL" in str(payload):
                        self.status_var.set("STATUS: NEEDS TEST SOL")
                        self.status_sub_var.set("Open Wallet & payout, then click Get test SOL.")
                        self._toggle_details(True)
                    else:
                        self.status_var.set("STATUS: NEEDS ATTENTION")
                        self.status_sub_var.set("See the activity below.")
                    self._log(payload)
                    messagebox.showinfo("SUMO Frog miner", payload, parent=self.root)
                elif kind == "done":
                    self.hero.set_enabled(True)
                    self._hero_mining(False)
                    if not self.status_var.get().startswith("STATUS: NEEDS"):
                        if "BLOCK FOUND" not in self.status_var.get():
                            self._set_state("STOPPED")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _on_close(self):
        if self._busy():
            self.stop_event.set()
            self.worker.join(timeout=3)
        self.root.destroy()

    # ---------- screenshots for review (never used in normal runs) ----------
    def _maybe_screenshot(self):
        path = os.environ.get("SUMO_GUI_SCREENSHOT")
        if not path:
            return
        demo = os.environ.get("SUMO_GUI_DEMO") == "1"
        open_details = os.environ.get("SUMO_GUI_OPEN_DETAILS") == "1"

        def shoot():
            if demo:
                self._hero_mining(True)
                self._apply_status(dict(state="MINING", rate="4.82 MH/S", guesses=12_847_301, mined=3,
                                        balance="60", sol=0.9871, block=1_243, diff="24.0 BITS",
                                        reward="20 SUMO"))
                self._log("Mining on devnet with 8 CPU workers. No tip or developer fee.")
                self._log("BLOCK FOUND! #1,241  +20 SUMO after 9,812,004 guesses (6.1s).")
            if open_details:
                self._toggle_details(True)
            self.root.update_idletasks()
            self.root.lift()
            self.root.focus_force()
            self.root.after(500, lambda: _take_screenshot(path, self.root))

        self.root.after(700, shoot)


def _take_screenshot(path, root):
    """Save just this window (review only)."""
    import shutil
    import subprocess
    import tempfile
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = max(root.winfo_width(), 1), max(root.winfo_height(), 1)
    saved = False
    try:
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
        saved = True
    except Exception:
        saved = False
    if not saved and shutil.which("scrot"):
        tmp = tempfile.mktemp(suffix=".png")
        subprocess.run(["scrot", "-o", tmp], check=False)
        try:
            from PIL import Image
            im = Image.open(tmp)
            im.crop((max(x, 0), max(y, 0), min(x + w, im.width), min(y + h, im.height))).save(path)
        except Exception:
            if os.path.isfile(tmp):
                shutil.copy(tmp, path)
        try:
            os.remove(tmp)
        except OSError:
            pass
    root.after(200, root.destroy)


def main():
    root = tk.Tk()
    MinerApp(root)
    root.mainloop()


if __name__ == "__main__":
    mp.freeze_support()
    main()
