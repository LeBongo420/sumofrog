#!/usr/bin/env python3
"""Build the Windows miner zips: dist/sumo_miner_win.zip and dist/sumo_miner_friends.zip.
Flat (no folders, no usernames in paths). Never includes wallet files, payout-address.txt or .venv.
Usage: python3 scripts/build_zips.py"""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINER = os.path.join(ROOT, "miner")
FILES = ["Mine SUMO.bat", "Check balance.bat", "Get test SOL.bat", "Set payout address.bat", "Withdraw SOL.bat", "_setup.bat",
         "HOW TO MINE.txt", "sumo_miner.py", "sumo_art.py", "sumo_config.json", "requirements.txt"]
NEVER = ("key", "payout-address", ".venv", "keypair")


def build(name):
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            assert not any(n in f.lower() for n in NEVER), f
            info = zipfile.ZipInfo(f, date_time=(2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, open(os.path.join(MINER, f), "rb").read())
    print("wrote", os.path.relpath(out, ROOT), os.path.getsize(out), "bytes")


if __name__ == "__main__":
    for n in ("sumo_miner_win.zip", "sumo_miner_friends.zip"):
        build(n)
