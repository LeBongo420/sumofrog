# -*- mode: python ; coding: utf-8 -*-
# Windowed Sumo Frog miner for Windows (devnet only). Build on windows-latest:
#   python -m PyInstaller miner/sumo_gui.spec --noconfirm --clean
# Never bundle wallets, keys, .env or the private sumo_config.json.

import os
from PyInstaller.utils.hooks import collect_dynamic_libs

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))

datas = []
for name, dest in (
    (os.path.join(SPEC_DIR, "devnet", "sumo_config.devnet.json"), "."),
    (os.path.join(SPEC_DIR, "sumo_config.example.json"), "."),
    (os.path.join(SPEC_DIR, "sumo.ico"), "."),
    (os.path.join(SPEC_DIR, "sumo_coin.ico"), "."),
):
    if os.path.isfile(name):
        datas.append((name, dest))
branding = os.path.join(SPEC_DIR, "branding")
if os.path.isdir(branding):
    datas.append((branding, "branding"))

hiddenimports = [
    "solders",
    "solders.hash",
    "solders.instruction",
    "solders.keypair",
    "solders.message",
    "solders.pubkey",
    "solders.transaction",
    "multiprocessing",
    "tkinter",
    "tkinter.font",
    "tkinter.messagebox",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageSequence",
    "PIL.ImageGrab",
]

a = Analysis(
    [os.path.join(SPEC_DIR, "sumo_gui.py")],
    pathex=[SPEC_DIR],
    binaries=collect_dynamic_libs("solders"),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["sumo_config.json"],
    noarchive=False,
)

# Do not ship any wallet or key file if one somehow appeared in the tree.
a.datas = [d for d in a.datas if "sumo-devnet-key" not in str(d[0]).lower()
           and not str(d[0]).lower().endswith("keypair.json")
           and os.path.basename(str(d[0])) != "sumo_config.json"]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SumoFrog",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(SPEC_DIR, "sumo.ico") if os.path.isfile(os.path.join(SPEC_DIR, "sumo.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SumoFrog",
)
