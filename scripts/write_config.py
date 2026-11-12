#!/usr/bin/env python3
"""Usage: write_config.py RPC_URL [PRIVATE_GENESIS_HASH]
Write the program ID and derived addresses into the miner and stats page configs."""
import json, os, re, sys
from solders.pubkey import Pubkey

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rpc = sys.argv[1] if len(sys.argv) > 1 else "https://api.devnet.solana.com"
private_genesis = sys.argv[2] if len(sys.argv) > 2 else None  # genesis hash of the private Sumo network


def program_id():
    """Public program address from Anchor.toml — no key file needed."""
    text = open(os.path.join(ROOT, "Anchor.toml"), encoding="utf-8").read()
    m = re.search(r'^\s*sumofrog\s*=\s*"([1-9A-HJ-NP-Za-km-z]{32,44})"', text, re.M)
    if not m:
        raise SystemExit("program id not found in Anchor.toml")
    return Pubkey.from_string(m.group(1))


program = program_id()
config = Pubkey.find_program_address([b"config"], program)[0]
mint = Pubkey.find_program_address([b"mint"], program)[0]
cfg = {"program_id": str(program), "config": str(config), "mint": str(mint), "rpc": rpc}
if private_genesis:
    cfg["private_genesis"] = private_genesis
cfg["devnet_rpc"] = "https://api.devnet.solana.com"
with open(os.path.join(ROOT, "miner/sumo_config.json"), "w") as f:
    json.dump(cfg, f, indent=2)
with open(os.path.join(ROOT, "stats/sumo_config.js"), "w") as f:
    f.write("const SUMO = " + json.dumps(cfg, indent=2) + ";\n")
print(json.dumps(cfg, indent=2))
