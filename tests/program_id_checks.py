#!/usr/bin/env python3
"""Offline checks for scripts/check_program_id.py.

Uses throwaway keys and temp source files only. Never touches the live .keys/.
No network. Run: python3 tests/program_id_checks.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import check_program_id as c  # noqa: E402

passed = 0


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except SystemExit as e:
        return str(e.code)
    raise AssertionError(f"not refused: {fn.__name__}")


def make_key(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(
        [
            "solana-keygen", "new", "--no-bip39-passphrase", "--silent",
            "--outfile", path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.chmod(path, 0o600)
    return path


def pubkey_of(path):
    r = subprocess.run(
        ["solana-keygen", "pubkey", path],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def write_tree(root, address, key_path=None, extra_toml_address=None, declare=None):
    os.makedirs(os.path.join(root, "programs", "sumofrog", "src"), exist_ok=True)
    os.makedirs(os.path.join(root, ".keys"), exist_ok=True)
    local_addr = address
    devnet_addr = extra_toml_address or address
    open(os.path.join(root, "Anchor.toml"), "w", encoding="utf-8").write(
        "[programs.localnet]\n"
        f'sumofrog = "{local_addr}"\n\n'
        "[programs.devnet]\n"
        f'sumofrog = "{devnet_addr}"\n'
    )
    open(
        os.path.join(root, "programs", "sumofrog", "src", "lib.rs"),
        "w",
        encoding="utf-8",
    ).write(f'declare_id!("{declare or address}");\n')
    if key_path is not None:
        dest = os.path.join(root, ".keys", "program.json")
        shutil.copy2(key_path, dest)
        os.chmod(dest, 0o600)


def key_bytes_leak(output, key_path):
    raw = open(key_path, encoding="utf-8").read().strip()
    return raw in output or json.dumps(json.loads(raw)) in output


def main():
    tmp = tempfile.mkdtemp(prefix="sumo-progid-")
    try:
        key_a = make_key(os.path.join(tmp, "keys", "a.json"))
        key_b = make_key(os.path.join(tmp, "keys", "b.json"))
        addr_a = pubkey_of(key_a)
        addr_b = pubkey_of(key_b)
        ok("throwaway keys have different public addresses", addr_a != addr_b)

        # All three sources agree.
        agree = os.path.join(tmp, "agree")
        write_tree(agree, addr_a, key_a)
        got = str(c.require_matching_program_id(agree))
        ok("agreed sources return the public address", got == addr_a)

        # Missing key file is fine when the two source files agree.
        no_key = os.path.join(tmp, "no-key")
        write_tree(no_key, addr_a, key_path=None)
        got = str(c.require_matching_program_id(no_key))
        ok("missing .keys/program.json is ok when the sources agree", got == addr_a)

        # Mismatch in Anchor.toml (both sections, so declare_id and the key agree).
        bad_toml = os.path.join(tmp, "bad-toml")
        write_tree(bad_toml, addr_b, key_a, declare=addr_a)
        msg = refused(c.require_matching_program_id, bad_toml)
        ok("mismatch in Anchor.toml is refused", "mismatch" in msg.lower())
        ok("mismatch in Anchor.toml reports both public addresses",
           addr_a in msg and addr_b in msg)
        ok("mismatch in Anchor.toml does not print key bytes",
           not key_bytes_leak(msg, key_a) and not key_bytes_leak(msg, key_b))

        # Mismatch in declare_id!.
        bad_decl = os.path.join(tmp, "bad-declare")
        write_tree(bad_decl, addr_a, key_a, declare=addr_b)
        msg = refused(c.require_matching_program_id, bad_decl)
        ok("mismatch in declare_id is refused", "mismatch" in msg.lower())
        ok("mismatch in declare_id reports both public addresses",
           addr_a in msg and addr_b in msg and "declare_id" in msg)
        ok("mismatch in declare_id does not print key bytes",
           not key_bytes_leak(msg, key_a) and not key_bytes_leak(msg, key_b))

        # Mismatch in .keys/program.json.
        bad_key = os.path.join(tmp, "bad-key")
        write_tree(bad_key, addr_a, key_b)
        msg = refused(c.require_matching_program_id, bad_key)
        ok("mismatch in .keys/program.json is refused", "mismatch" in msg.lower())
        ok("mismatch in .keys/program.json reports both public addresses",
           addr_a in msg and addr_b in msg and ".keys/program.json" in msg)
        ok("mismatch in .keys/program.json does not print key bytes",
           not key_bytes_leak(msg, key_a) and not key_bytes_leak(msg, key_b))

        # The two Anchor.toml sections disagree with each other.
        split_toml = os.path.join(tmp, "split-toml")
        write_tree(split_toml, addr_a, key_a, extra_toml_address=addr_b)
        msg = refused(c.require_matching_program_id, split_toml)
        ok("disagreement between Anchor.toml sections is refused",
           "mismatch" in msg.lower() and addr_a in msg and addr_b in msg)

        # Missing key file, but the two source files disagree.
        no_key_bad = os.path.join(tmp, "no-key-bad")
        write_tree(no_key_bad, addr_a, key_path=None, declare=addr_b)
        msg = refused(c.require_matching_program_id, no_key_bad)
        ok("missing key still refuses a source-file mismatch",
           "mismatch" in msg.lower() and addr_a in msg and addr_b in msg)

        # The live repo (this checkout) agrees with itself. Do not print the address here.
        live = str(c.require_matching_program_id(c.ROOT))
        ok("live repo sources agree",
           live and c.PUBKEY.fullmatch(live) is not None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"program id checks: {passed} passed")


if __name__ == "__main__":
    main()
