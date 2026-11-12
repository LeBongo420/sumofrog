#!/usr/bin/env python3
"""Fail if the declared program addresses disagree.

Compares every sumofrog address in Anchor.toml, declare_id! in
programs/sumofrog/src/lib.rs, and when present the public address of
.keys/program.json. Prints public addresses only, never key bytes.

Usage: python3 scripts/check_program_id.py
On success, prints the agreed public address and exits 0.
"""
import json
import os
import re
import sys

from solders.keypair import Keypair
from solders.pubkey import Pubkey

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBKEY = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
DECLARE = re.compile(
    r'declare_id!\(\s*"([1-9A-HJ-NP-Za-km-z]{32,44})"\s*\)'
)
TOML_ID = re.compile(r'^\s*sumofrog\s*=\s*"([1-9A-HJ-NP-Za-km-z]{32,44})"')
SECTION = re.compile(r"^\[([^\]]+)\]")


def _pubkey(label, value):
    if not value or not PUBKEY.fullmatch(value):
        raise SystemExit(f"program id in {label} is not a valid address")
    try:
        return str(Pubkey.from_string(value))
    except Exception:
        raise SystemExit(f"program id in {label} is not a valid address")


def _ids_from_anchor(root):
    path = os.path.join(root, "Anchor.toml")
    if not os.path.isfile(path):
        raise SystemExit("program id check failed: Anchor.toml is missing")
    text = open(path, encoding="utf-8").read()
    found = {}
    section = None
    for line in text.splitlines():
        m = SECTION.match(line.strip())
        if m:
            section = m.group(1)
            continue
        m = TOML_ID.match(line)
        if m:
            label = f"Anchor.toml [{section}]" if section else "Anchor.toml"
            found[label] = _pubkey(label, m.group(1))
    if not found:
        raise SystemExit("program id check failed: no sumofrog address in Anchor.toml")
    return found


def _id_from_declare(root):
    rel = os.path.join("programs", "sumofrog", "src", "lib.rs")
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        raise SystemExit(f"program id check failed: {rel} is missing")
    text = open(path, encoding="utf-8").read()
    hits = DECLARE.findall(text)
    if len(hits) != 1:
        raise SystemExit(
            f"program id check failed: {rel} must contain exactly one declare_id!"
        )
    label = f"{rel} declare_id"
    return {label: _pubkey(label, hits[0])}


def _id_from_key(root):
    rel = os.path.join(".keys", "program.json")
    path = os.path.join(root, rel)
    if not os.path.lexists(path):
        return {}
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        if not isinstance(data, list) or not all(isinstance(n, int) for n in data):
            raise ValueError("not a keypair list")
        pubkey = str(Keypair.from_bytes(bytes(data)).pubkey())
    except SystemExit:
        raise
    except Exception:
        # Do not include the exception text; it might hold key material.
        raise SystemExit("program id check failed: .keys/program.json is not a valid keypair")
    return {rel: pubkey}


def collect_program_ids(root=None):
    """Return an ordered map of source label -> public address.

    .keys/program.json is included only when that file is present.
    """
    root = os.path.abspath(root or ROOT)
    ids = {}
    ids.update(_ids_from_anchor(root))
    ids.update(_id_from_declare(root))
    ids.update(_id_from_key(root))
    return ids


def require_matching_program_id(root=None):
    """Return the agreed program Pubkey, or exit if the sources disagree."""
    ids = collect_program_ids(root)
    values = set(ids.values())
    if len(values) != 1:
        lines = ["program id mismatch:"]
        for label, value in ids.items():
            lines.append(f"  {label}: {value}")
        raise SystemExit("\n".join(lines))
    return Pubkey.from_string(next(iter(values)))


def main(argv=None):
    del argv
    program = require_matching_program_id()
    print(str(program))
    return 0


if __name__ == "__main__":
    sys.exit(main())
