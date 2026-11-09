#!/usr/bin/env python3
"""Offline checks for scripts/deploy-devnet.sh SUMO_RPC refuse rule (Ribbit, 5 Nov 2026).

Proves a SUMO_RPC with a backslash or @ is refused by the real deploy script before the
host check (and before `solana` is called). Normal local/devnet URLs without \\ or @ pass
this new guard. No deploy, no Oracle validator, no network needed for the refuse cases.
Run: python3 tests/deploy_devnet_guard.py
"""
import os
import subprocess
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "deploy-devnet.sh")
passed = 0


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


def run_deploy(rpc, env_extra=None, timeout=15):
    env = os.environ.copy()
    env["SUMO_RPC"] = rpc
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", SCRIPT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def guard_allows(rpc):
    """Same case pattern as deploy-devnet.sh: True if the new guard lets the URL through."""
    r = subprocess.run(
        [
            "bash",
            "-c",
            'case "$1" in *\\\\*|*@*) exit 1 ;; esac; exit 0',
            "_",
            rpc,
        ]
    )
    return r.returncode == 0


# ---- refuse case is in the script, before genesis-hash and before the host check ----
src = open(SCRIPT).read()
refuse_at = src.find("*\\\\*|*@*")
gh_at = src.find('GH="$(solana genesis-hash')
host_at = src.find('HOST="$(python3')
ok("refuse case present in deploy-devnet.sh", refuse_at > 0)
ok("refuse case is before solana genesis-hash", 0 < refuse_at < gh_at)
ok("refuse case is before the host check", 0 < refuse_at < host_at)
ok("refuse message is plain", "SUMO_RPC has a backslash or @" in src)

# ---- Ribbit's example: Python host parse would treat it as local; we must refuse ----
ribbit = r"http://some-other-host\@127.0.0.1:8999"
ok(
    "Ribbit example: Python host parse sees 127.0.0.1 (the bug)",
    (urllib.parse.urlsplit(ribbit).hostname or "").lower() == "127.0.0.1",
)

# ---- crafted URLs: real script refuses quickly (no solana / no deploy) ----
crafted = [
    ribbit,
    "http://user@evil.io",
    r"http://127.0.0.1\evil",
    "http://evil.io/@127.0.0.1",
]
for rpc in crafted:
    r = run_deploy(rpc)
    out = (r.stdout or "") + (r.stderr or "")
    ok(f"script refuses {rpc!r}", r.returncode == 1 and "backslash or @" in out)
    ok(
        f"script does not reach deploy/setup for {rpc!r}",
        "Deployer" not in out and "Program already" not in out and "stub" not in out.lower(),
    )
    ok(f"guard case refuses {rpc!r}", not guard_allows(rpc))

# ---- normal URLs: this new guard accepts them (existing host/genesis checks still apply) ----
for rpc in (
    "http://127.0.0.1:8899",
    "http://localhost:8899",
    "http://[::1]:8899",
    "https://api.devnet.solana.com",
):
    ok(f"guard allows {rpc!r}", guard_allows(rpc))

print(f"deploy-devnet guard: {passed} passed")
