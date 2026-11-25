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

# High-contrast palette. Status is always written in words, not colour alone.
BG = "#FFFFFF"
FG = "#111111"
SUB = "#1A1A1A"
PANEL = "#F3F3F3"
BORDER = "#111111"
BTN_BG = "#111111"
BTN_FG = "#FFFFFF"
BTN_OFF_BG = "#E8E8E8"
BTN_OFF_FG = "#111111"
ENTRY_BG = "#FFFFFF"
DANGER_BG = "#111111"
DANGER_FG = "#FFFFFF"


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

        root.title(f"SUMO Frog miner {VERSION}  (test coins only)")
        root.configure(bg=BG)
        root.minsize(720, 700)
        self._set_icon()
        self._build()
        root.update_idletasks()
        req_w = max(root.winfo_reqwidth(), 760)
        req_h = root.winfo_reqheight()
        root.geometry(f"{req_w}x{req_h}")
        root.minsize(720, min(req_h, 760))
        self._load_wallet()
        self._load_payout()
        self._set_state("STOPPED", "Ready. This is Solana devnet: test coins only, no real money.")
        root.after(100, self._drain)
        self._maybe_screenshot()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_icon(self):
        for name in ("sumo_coin.ico", "sumo.ico"):
            path = os.path.join(bundled_dir(), name)
            if os.path.isfile(path):
                try:
                    root = self.root
                    root.iconbitmap(path)
                    return
                except Exception:
                    continue

    def _font(self, size=11, bold=False, mono=False):
        if mono:
            base = tkfont.nametofont("TkFixedFont")
            return tkfont.Font(family=base.actual("family"), size=size, weight="bold" if bold else "normal")
        family = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
        return tkfont.Font(family=family, size=size, weight="bold" if bold else "normal")

    def _build(self):
        pad = {"padx": 14, "pady": 4}
        f_title = self._font(16, True)
        f_body = self._font(11)
        f_small = self._font(10)
        f_mono = self._font(11, mono=True)

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", **pad)
        tk.Label(header, text="SUMO Frog miner", font=f_title, bg=BG, fg=FG, anchor="w").pack(anchor="w")
        tk.Label(
            header,
            text=f"{VERSION}  ·  Solana devnet  ·  test coins only, no real money",
            font=f_small, bg=BG, fg=SUB, anchor="w",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="No tip or developer fee. All mined SUMO goes to your reward wallet.",
            font=f_body, bg=BG, fg=FG, anchor="w",
        ).pack(anchor="w")

        self.status_box = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=2)
        self.status_box.pack(fill="x", padx=14, pady=6)
        self.status_var = tk.StringVar(value="STATUS: STOPPED")
        tk.Label(
            self.status_box, textvariable=self.status_var, font=self._font(15, True),
            bg=PANEL, fg=FG, anchor="w", padx=10, pady=8,
        ).pack(fill="x")

        wallet = tk.LabelFrame(
            self.root, text="  Your local test wallet  ", font=self._font(11, True),
            bg=BG, fg=FG, bd=2, relief="solid", padx=8, pady=6,
        )
        wallet.pack(fill="x", padx=14, pady=4)
        tk.Label(
            wallet,
            text="Saved only on this PC as " + WALLET_NAME + ". It is never uploaded. It pays the tiny test-network fees.",
            font=f_small, bg=BG, fg=SUB, wraplength=720, justify="left", anchor="w",
        ).pack(fill="x")
        row = tk.Frame(wallet, bg=BG)
        row.pack(fill="x", pady=(6, 2))
        self.address_var = tk.StringVar(value="(no wallet yet)")
        self.address_entry = tk.Entry(
            row, textvariable=self.address_var, font=f_mono, bg=PANEL, fg=FG,
            relief="solid", bd=1, readonlybackground=PANEL,
        )
        self.address_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.address_entry.config(state="readonly")
        self.copy_btn = self._button(row, "Copy address", self._copy_address)
        self.copy_btn.pack(side="left", padx=(8, 0))
        faucet_row = tk.Frame(wallet, bg=BG)
        faucet_row.pack(fill="x", pady=(6, 0))
        self._button(faucet_row, "Open devnet faucet", self._open_faucet).pack(side="left")
        tk.Label(
            faucet_row,
            text="Opens faucet.solana.com and copies your address. Pick Devnet, paste it, request test SOL.",
            font=f_small, bg=BG, fg=SUB, wraplength=480, justify="left", anchor="w",
        ).pack(side="left", padx=(10, 0))

        payout = tk.LabelFrame(
            self.root, text="  Payout address (optional)  ", font=self._font(11, True),
            bg=BG, fg=FG, bd=2, relief="solid", padx=8, pady=6,
        )
        payout.pack(fill="x", padx=14, pady=4)
        tk.Label(
            payout,
            text="Paste your own wallet's PUBLIC address to have mined SUMO credited there. "
                 "The local test wallet still pays the fees. Leave this empty to keep rewards "
                 "in the local test wallet. NEVER paste a seed phrase or private key.",
            font=f_small, bg=BG, fg=SUB, wraplength=720, justify="left", anchor="w",
        ).pack(fill="x")
        prow = tk.Frame(payout, bg=BG)
        prow.pack(fill="x", pady=(6, 2))
        self.payout_entry = tk.Entry(prow, font=f_mono, bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="solid", bd=2)
        self.payout_entry.pack(side="left", fill="x", expand=True, ipady=4)
        brow = tk.Frame(payout, bg=BG)
        brow.pack(fill="x", pady=(6, 0))
        self._button(brow, "Save payout address", self._save_payout).pack(side="left")
        self._button(brow, "Use miner wallet", self._clear_payout, invert=True).pack(side="left", padx=(8, 0))
        self.reward_var = tk.StringVar(value="Rewards go to: this miner's test wallet. No tip or developer fee.")
        tk.Label(payout, textvariable=self.reward_var, font=f_body, bg=BG, fg=FG, anchor="w", wraplength=720, justify="left").pack(fill="x", pady=(4, 0))

        stats = tk.LabelFrame(
            self.root, text="  Live status  ", font=self._font(11, True),
            bg=BG, fg=FG, bd=2, relief="solid", padx=8, pady=6,
        )
        stats.pack(fill="x", padx=14, pady=4)
        self.stat_vars = {
            "hash": tk.StringVar(value="Hash rate: --"),
            "guess": tk.StringVar(value="Guess #: 0"),
            "blocks": tk.StringVar(value="Blocks found this session: 0"),
            "balance": tk.StringVar(value="SUMO balance: --"),
            "sol": tk.StringVar(value="Test SOL (for fees): --"),
            "block": tk.StringVar(value="Network block: --"),
            "diff": tk.StringVar(value="Difficulty: --"),
            "reward": tk.StringVar(value="Block reward: --"),
        }
        grid = tk.Frame(stats, bg=BG)
        grid.pack(fill="x")
        items = [
            ("hash", 0, 0), ("guess", 0, 1),
            ("blocks", 1, 0), ("balance", 1, 1),
            ("sol", 2, 0), ("block", 2, 1),
            ("diff", 3, 0), ("reward", 3, 1),
        ]
        for key, r, c in items:
            tk.Label(
                grid, textvariable=self.stat_vars[key], font=f_body, bg=PANEL, fg=FG,
                anchor="w", padx=8, pady=5, relief="solid", bd=1,
            ).grid(row=r, column=c, sticky="ew", padx=3, pady=2)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        controls = tk.Frame(self.root, bg=BG)
        controls.pack(fill="x", padx=14, pady=8)
        self.start_btn = self._button(controls, "Start mining", self._start, big=True)
        self.start_btn.pack(side="left")
        self.stop_btn = self._button(controls, "Stop mining", self._stop, big=True, invert=True)
        self.stop_btn.pack(side="left", padx=(10, 0))
        self.stop_btn.config(state="disabled")

        self.message = tk.Text(
            self.root, height=5, font=f_small, bg=PANEL, fg=FG, relief="solid", bd=2,
            wrap="word", state="disabled", padx=8, pady=6,
            highlightthickness=0,
        )
        self.message.pack(fill="x", expand=False, padx=14, pady=(0, 12))

    def _button(self, parent, text, command, invert=False, big=False):
        bg, fg = (BTN_OFF_BG, BTN_OFF_FG) if invert else (BTN_BG, BTN_FG)
        return tk.Button(
            parent, text=text, command=command, font=self._font(12 if not big else 14, True),
            bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
            relief="solid", bd=2, padx=14, pady=6, highlightthickness=0, cursor="hand2",
        )

    def _log(self, text):
        self.message.config(state="normal")
        self.message.insert("end", text.rstrip() + "\n")
        self.message.see("end")
        self.message.config(state="disabled")

    def _set_state(self, state, note=None):
        self.status_var.set("STATUS: " + state)
        if note:
            self._log(note)

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
            self._log(
                "A new test-only wallet was saved as " + WALLET_NAME + " in this folder. "
                "Keep that file private and never share it. Never put real money in it."
            )
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

    def _update_reward_line(self):
        if self.payout is not None:
            self.reward_var.set(
                "Rewards go to: " + str(self.payout) + " (your payout address). "
                "The local test wallet pays fees. No tip or developer fee."
            )
        elif self.kp is not None:
            self.reward_var.set(
                "Rewards go to: this miner's test wallet (" + str(self.kp.pubkey()) + "). "
                "No tip or developer fee."
            )
        else:
            self.reward_var.set("Rewards go to: this miner's test wallet. No tip or developer fee.")

    def _copy_address(self, also_log=True):
        addr = self.address_var.get()
        if not addr or addr.startswith("("):
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(addr)
        self.root.update_idletasks()
        self.copy_btn.config(text="Copied")
        if self._copy_reset:
            self.root.after_cancel(self._copy_reset)
        self._copy_reset = self.root.after(2000, lambda: self.copy_btn.config(text="Copy address"))
        if also_log:
            self._log("Address copied. You can paste it at the devnet faucet.")
        return True

    def _open_faucet(self):
        self._copy_address(also_log=False)
        webbrowser.open(FAUCET_URL)
        self._log(
            "Opened the devnet faucet in your browser and copied your address. "
            "Pick Devnet, paste the address, and request the most it allows."
        )

    def _save_payout(self):
        text = self.payout_entry.get().strip()
        if not text:
            self._log("Paste a PUBLIC address first, or click Use miner wallet to keep rewards here.")
            return
        pk, err = try_parse_payout(text, self.settings)
        if err:
            messagebox.showerror("Payout address not saved", err, parent=self.root)
            self._log(err)
            return
        if self.kp is not None and pk == self.kp.pubkey():
            self._clear_payout()
            return
        write_saved_payout(pk)
        self.payout = pk
        self.payout_entry.delete(0, "end")
        self.payout_entry.insert(0, str(pk))
        self._update_reward_line()
        self._log("Saved payout address. From the next block, mined SUMO is credited to that wallet. No tip or developer fee.")

    def _clear_payout(self):
        write_saved_payout(None)
        self.payout = None
        self.payout_entry.delete(0, "end")
        self._update_reward_line()
        self._log("Payout address cleared. Rewards will stay in this miner's test wallet.")

    def _busy(self):
        return self.worker is not None and self.worker.is_alive()

    def _start(self):
        if self._busy():
            return
        if self.kp is None:
            self._log("There is no local test wallet yet, so mining can't start.")
            return
        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
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

    def _stop(self):
        if not self._busy():
            return
        self.stop_event.set()
        self._set_state("STOPPING", "Stop requested. Waiting for this guess batch to finish…")

    def _apply_status(self, hud):
        state = hud.get("state") or "MINING"
        if hud.get("reward_won") and state == "BLOCK FOUND":
            self.status_var.set("STATUS: BLOCK FOUND  +" + hud["reward_won"])
        else:
            self.status_var.set("STATUS: " + state)
        if "rate" in hud:
            self.stat_vars["hash"].set("Hash rate: " + str(hud["rate"]))
        if "guesses" in hud:
            self.stat_vars["guess"].set("Guess #: " + m.fmt_int(hud["guesses"]))
        if "mined" in hud:
            self.stat_vars["blocks"].set("Blocks found this session: " + m.fmt_int(hud["mined"]))
        if "balance" in hud:
            self.stat_vars["balance"].set("SUMO balance: " + str(hud["balance"]))
        if "sol" in hud:
            self.stat_vars["sol"].set("Test SOL (for fees): " + f"{hud['sol']:.4f}")
        if "block" in hud:
            self.stat_vars["block"].set("Network block: " + m.fmt_int(hud["block"]))
        if "diff" in hud:
            self.stat_vars["diff"].set("Difficulty: " + str(hud["diff"]))
        if "reward" in hud:
            self.stat_vars["reward"].set("Block reward: " + str(hud["reward"]))

    def _drain(self):
        try:
            while True:
                kind, payload = self.bus.get_nowait()
                if kind == "status":
                    self._apply_status(payload)
                elif kind == "event":
                    self._log(payload)
                    if str(payload).startswith("Stopped"):
                        self.status_var.set("STATUS: STOPPED")
                elif kind == "error":
                    self.status_var.set("STATUS: NEEDS ATTENTION")
                    if "needs a little test SOL" in str(payload):
                        self.status_var.set("STATUS: NEEDS TEST SOL")
                    self._log(payload)
                    messagebox.showinfo("SUMO Frog miner", payload, parent=self.root)
                elif kind == "done":
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    if not self.status_var.get().startswith("STATUS: NEEDS"):
                        if "BLOCK FOUND" not in self.status_var.get():
                            self.status_var.set("STATUS: STOPPED")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _on_close(self):
        if self._busy():
            self.stop_event.set()
            self.worker.join(timeout=3)
        self.root.destroy()

    def _maybe_screenshot(self):
        path = os.environ.get("SUMO_GUI_SCREENSHOT")
        if not path:
            return

        def shoot():
            self.root.update_idletasks()
            self.root.lift()
            self.root.focus_force()
            self.root.after(400, lambda: _take_screenshot(path, self.root))

        self.root.after(600, shoot)


def _take_screenshot(path, root):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    # Prefer a window capture when scrot is present; fall back to a Tk postscript crop is not needed.
    import shutil
    import subprocess
    if shutil.which("scrot"):
        subprocess.run(["scrot", "-z", path], check=False)
    root.after(200, root.destroy)


def main():
    root = tk.Tk()
    MinerApp(root)
    root.mainloop()


if __name__ == "__main__":
    mp.freeze_support()
    main()
