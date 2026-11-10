#!/usr/bin/env python3
"""Build docs/downloads/sumo-miner-v<version>.zip from the miner folder.

Flat zip (no folders). Includes the example config only — never the real
sumo_config.json, keys, keypairs, or a server address.
Usage: python3 scripts/build_zips.py
"""
import hashlib
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINER = os.path.join(ROOT, "miner")
FILES = [
    "START HERE.txt",
    "HOW TO MINE.txt",
    "Mine SUMO.bat",
    "Check balance.bat",
    "Get test SOL.bat",
    "Set payout address.bat",
    "Withdraw SOL.bat",
    "_setup.bat",
    "sumo_miner.py",
    "sumo_art.py",
    "sumo_config.example.json",
    "requirements.txt",
]
FORBIDDEN_NAMES = ("sumo_config.json", "payout-address", ".venv", "keypair",
                   "id.json", "sumo-devnet-key", ".keys", "target/")
# Hosts allowed in the example: placeholder only.
HOST_OK = re.compile(r"YOUR_SERVER")
IPV4 = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
KEYPAIR = re.compile(rb"\[\s*(?:\d{1,3}\s*,\s*){31,}\d{1,3}\s*\]")
PEM = re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?" + rb"PRIVATE KEY-----")


def version():
    text = open(os.path.join(MINER, "sumo_miner.py"), encoding="utf-8").read()
    m = re.search(r'^VERSION\s*=\s*"v?([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("VERSION not found in sumo_miner.py")
    return m.group(1)


def oracle_ip():
    path = "/workspace/copytrader/ORACLE.md"
    if not os.path.isfile(path):
        return b""
    m = re.search(r"`(\d+\.\d+\.\d+\.\d+)`", open(path, encoding="utf-8").read())
    return m.group(1).encode() if m else b""


def check_payload(name, data, ip):
    lower = name.lower()
    if any(n in lower or n in name for n in FORBIDDEN_NAMES):
        raise SystemExit(f"refusing to pack forbidden name: {name}")
    if name == "sumo_config.json" or name.endswith("/sumo_config.json"):
        raise SystemExit("refusing to pack real sumo_config.json")
    if ip and ip in data:
        raise SystemExit(f"server address found in {name}")
    if PEM.search(data) or KEYPAIR.search(data):
        raise SystemExit(f"key material found in {name}")
    if name.endswith(".json") or name.endswith(".js") or name.endswith(".py") or name.endswith(".txt"):
        for hit in IPV4.findall(data):
            s = hit.decode()
            if s.startswith("127.") or s.startswith("0.") or s.startswith("255."):
                continue
            # allow nothing else — example must use YOUR_SERVER
            raise SystemExit(f"unexpected address in {name}")


def build():
    ver = version()
    name = f"sumo-miner-v{ver}.zip"
    dest_dir = os.path.join(ROOT, "docs", "downloads")
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, name)
    ip = oracle_ip()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            path = os.path.join(MINER, f)
            if not os.path.isfile(path):
                raise SystemExit(f"missing {f}")
            data = open(path, "rb").read()
            check_payload(f, data, ip)
            # flat name only — no directories, no usernames
            if os.path.basename(f) != f or "/" in f or "\\" in f:
                raise SystemExit(f"refusing nested path: {f}")
            info = zipfile.ZipInfo(f, date_time=(2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
        names = z.namelist()
        if any("/" in n or "\\" in n for n in names):
            raise SystemExit("zip contains a folder path")
        if "sumo_config.json" in names:
            raise SystemExit("zip contains real config")
        if "sumo_config.example.json" not in names:
            raise SystemExit("zip missing example config")
    raw = open(out, "rb").read()
    if ip and ip in raw:
        os.remove(out)
        raise SystemExit("server address found in zip bytes")
    sha = hashlib.sha256(raw).hexdigest()
    print("wrote", os.path.relpath(out, ROOT), len(raw), "bytes")
    print("sha256", sha)
    print("files", ", ".join(FILES))
    return name, sha, len(raw)


if __name__ == "__main__":
    build()
