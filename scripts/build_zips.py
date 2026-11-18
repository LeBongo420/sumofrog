#!/usr/bin/env python3
"""Build docs/downloads/sumo-miner-v<version>.zip from the miner folder.

Flat zip (no folders). Packed from git (committed tracked files only),
never the working tree, so ignored sumo_config.json, keys and keypairs
cannot be included. The example config is packed; the real config is not.
Usage: python3 scripts/build_zips.py            (private-chain zip)
       python3 scripts/build_zips.py --devnet   (sumo-miner-v<version>-devnet.zip: ships a
       ready sumo_config.json set to public devnet, plus devnet START HERE / HOW TO MINE text)
       python3 scripts/build_zips.py --devnet --candidate   (same, named ...-devnet-candidate.zip,
       so a test build never overwrites a zip people already have)
The devnet zip is tidy: only START HERE.txt and the one launcher (SUMO Frog.bat, a numbered menu) on
top, everything else in files/.
The private-chain zip stays flat (no folders).
"""
import hashlib
import json
import os
import re
import subprocess
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
    "sumo.ico",
    "sumo_coin.ico",
    "requirements.txt",
]
# Devnet zip layout: (name inside the zip, source under miner/). Top level = the launcher and START HERE;
# everything else sits in one folder, files/ (the miner finds its own files next to sumo_miner.py).
DEVNET_TOP = [
    ("START HERE.txt", "devnet/START HERE.txt"),
    ("SUMO Frog.bat", "devnet/SUMO Frog.bat"),
]
DEVNET_FILES_DIR = "files"
DEVNET_INNER = [
    ("HOW TO MINE.txt", "devnet/HOW TO MINE.txt"),
    ("_start.bat", "devnet/_start.bat"),
    ("_setup.bat", "_setup.bat"),
    ("sumo_miner.py", "sumo_miner.py"),
    ("sumo_art.py", "sumo_art.py"),
    ("sumo_config.json", "devnet/sumo_config.devnet.json"),
    ("sumo.ico", "sumo.ico"),
    ("sumo_coin.ico", "sumo_coin.ico"),
    ("requirements.txt", "requirements.txt"),
]
DEVNET_LAYOUT = DEVNET_TOP + [(f"{DEVNET_FILES_DIR}/{a}", src) for a, src in DEVNET_INNER]
FORBIDDEN_NAMES = ("sumo_config.json", "payout-address", ".venv", "keypair",
                   "id.json", "sumo-devnet-key", ".keys", "target/")
# Hosts allowed in the example: placeholder only.
HOST_OK = re.compile(r"YOUR_SERVER")
IPV4 = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
KEYPAIR = re.compile(rb"\[\s*(?:\d{1,3}\s*,\s*){31,}\d{1,3}\s*\]")
PEM = re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?" + rb"PRIVATE KEY-----")


def git_show(relpath):
    """Return the committed bytes of a tracked file (never working-tree or ignored copies)."""
    r = subprocess.run(
        ["git", "-C", ROOT, "show", f"HEAD:{relpath}"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"refusing to pack untracked or uncommitted file: {relpath}")
    return r.stdout


def version():
    text = git_show("miner/sumo_miner.py").decode("utf-8")
    m = re.search(r'^VERSION\s*=\s*"v?([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("VERSION not found in sumo_miner.py")
    return m.group(1)


# Address sources for the zip payload check. The first two are the local
# gitignored configs; the last is the off-repo note that also holds the
# server address. The check must never be skipped silently.
DEFAULT_ADDRESS_SOURCES = (
    os.path.join(ROOT, "miner", "sumo_config.json"),
    os.path.join(ROOT, "stats", "sumo_config.js"),
    "/workspace/copytrader/ORACLE.md",
)


def usable_ipv4s(text):
    """Return every unique non-loopback IPv4 as bytes, in the order found."""
    data = text.encode("utf-8") if isinstance(text, str) else text
    out = []
    seen = set()
    for hit in IPV4.findall(data):
        s = hit.decode("ascii")
        if s.startswith(("127.", "0.", "255.")):
            continue
        if hit not in seen:
            seen.add(hit)
            out.append(hit)
    return tuple(out)


def usable_ipv4(text):
    """Return the first non-loopback IPv4 as bytes, or b''."""
    found = usable_ipv4s(text)
    return found[0] if found else b""


def oracle_ip(sources=None):
    """Return every private server IPv4 found in the address sources, as a tuple of bytes.

    Reads the local gitignored miner config, the stats config, and ORACLE.md
    (or the paths in sources). Collects every usable address from every
    source that exists. Exits non-zero if every source is missing or none
    contains a usable address. Never prints an address.
    """
    paths = tuple(sources) if sources is not None else DEFAULT_ADDRESS_SOURCES
    found_file = False
    ips = []
    seen = set()
    for path in paths:
        if not os.path.isfile(path):
            continue
        found_file = True
        for ip in usable_ipv4s(open(path, encoding="utf-8").read()):
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
    if not found_file:
        raise SystemExit("server-address check failed: no address source file was found")
    if not ips:
        raise SystemExit("server-address check failed: no usable address in the source files")
    return tuple(ips)


def check_payload(name, data, ips):
    lower = name.lower()
    if any(n in lower or n in name for n in FORBIDDEN_NAMES):
        raise SystemExit(f"refusing to pack forbidden name: {name}")
    if name == "sumo_config.json" or name.endswith("/sumo_config.json"):
        raise SystemExit("refusing to pack real sumo_config.json")
    for ip in ips:
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


def check_devnet_config(data):
    """The shipped devnet config must say devnet, name no private server and no private genesis."""
    cfg = json.loads(data)
    if cfg.get("network") != "devnet":
        raise SystemExit("devnet config must set network to devnet")
    if set(cfg) - {"network", "program_id", "config", "mint", "devnet_rpc"}:
        raise SystemExit("devnet config has unexpected keys (no rpc/private_genesis/payout allowed)")
    if cfg.get("devnet_rpc") != "https://api.devnet.solana.com":
        raise SystemExit("devnet config must use the public devnet RPC")
    if b"YOUR_SERVER" in data:
        raise SystemExit("devnet config still has the server placeholder")


def build_devnet(candidate=False):
    """The tidy devnet zip: START HERE.txt + SUMO Frog.bat on top, everything else in files/."""
    ver = version()
    name = f"sumo-miner-v{ver}-devnet{'-candidate' if candidate else ''}.zip"
    dest_dir = os.path.join(ROOT, "docs", "downloads")
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, name)
    ips = oracle_ip()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in DEVNET_LAYOUT:
            parts = arc.split("/")
            if "\\" in arc or ".." in parts or len(parts) > 2 or (len(parts) == 2 and parts[0] != DEVNET_FILES_DIR):
                raise SystemExit(f"refusing unexpected path in devnet zip: {arc}")
            data = git_show(f"miner/{src}")
            if arc == f"{DEVNET_FILES_DIR}/sumo_config.json":
                check_devnet_config(data)
                check_payload("sumo_config.devnet.json", data, ips)
            else:
                check_payload(arc, data, ips)
            info = zipfile.ZipInfo(arc, date_time=(2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
        names = z.namelist()
        top = [n for n in names if "/" not in n]
        if sorted(top) != sorted(a for a, _ in DEVNET_TOP):
            raise SystemExit(f"devnet zip top level is not just START HERE.txt and SUMO Frog.bat: {top}")
        if any(n.count("/") > 1 or not n.startswith(DEVNET_FILES_DIR + "/") for n in names if "/" in n):
            raise SystemExit("devnet zip has a folder other than files/")
        if f"{DEVNET_FILES_DIR}/sumo_config.json" not in names or any("example" in n for n in names):
            raise SystemExit("devnet zip must ship files/sumo_config.json and no example config")
    raw = open(out, "rb").read()
    if any(ip in raw for ip in ips):
        os.remove(out)
        raise SystemExit("server address found in zip bytes")
    sha = hashlib.sha256(raw).hexdigest()
    print("wrote", os.path.relpath(out, ROOT), len(raw), "bytes")
    print("sha256", sha)
    print("files", ", ".join(names))
    return name, sha, len(raw)


def build(devnet=False, candidate=False):
    if devnet:
        return build_devnet(candidate)
    ver = version()
    name = f"sumo-miner-v{ver}.zip"
    dest_dir = os.path.join(ROOT, "docs", "downloads")
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, name)
    ips = oracle_ip()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            data = git_show(f"miner/{f}")
            check_payload(f, data, ips)
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
    if any(ip in raw for ip in ips):
        os.remove(out)
        raise SystemExit("server address found in zip bytes")
    sha = hashlib.sha256(raw).hexdigest()
    print("wrote", os.path.relpath(out, ROOT), len(raw), "bytes")
    print("sha256", sha)
    print("files", ", ".join(FILES))
    return name, sha, len(raw)


if __name__ == "__main__":
    import sys
    build(devnet="--devnet" in sys.argv[1:], candidate="--candidate" in sys.argv[1:])
