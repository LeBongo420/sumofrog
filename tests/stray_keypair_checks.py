#!/usr/bin/env python3
"""Offline checks for scripts/remove_stray_keypair.sh.

Uses throwaway keys in a temp folder only. Never touches the live .keys/.
No network. Run: python3 tests/stray_keypair_checks.py
"""
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "remove_stray_keypair.sh")
passed = 0


def ok(name, cond):
    global passed
    assert cond, name
    passed += 1


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def make_key(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
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


def run_remove(root):
    return subprocess.run(
        ["bash", SCRIPT, root],
        capture_output=True,
        text=True,
    )


def setup_repo(tmp, name):
    root = os.path.join(tmp, name)
    os.makedirs(os.path.join(root, "target", "deploy"))
    os.makedirs(os.path.join(root, ".keys"))
    real = make_key(os.path.join(root, ".keys", "program.json"))
    return root, real, sha(real)


def main():
    tmp = tempfile.mkdtemp(prefix="sumo-stray-key-")
    try:
        # A plain unique file in target/deploy is removed; the real key is left.
        root, real, real_sha = setup_repo(tmp, "plain")
        stray = make_key(os.path.join(root, "target", "deploy", "sumofrog-keypair.json"))
        stray_was = os.path.isfile(stray)
        r = run_remove(root)
        ok("plain stray: exit 0", r.returncode == 0)
        ok("plain stray: the target/deploy copy was removed",
           stray_was and not os.path.lexists(stray))
        ok("plain stray: the real key survives",
           os.path.isfile(real) and sha(real) == real_sha)

        # A symlink to the real key is left, and the real key is not wiped.
        root, real, real_sha = setup_repo(tmp, "symlink")
        link = os.path.join(root, "target", "deploy", "sumofrog-keypair.json")
        os.symlink(real, link)
        r = run_remove(root)
        ok("symlink: exit 0", r.returncode == 0)
        ok("symlink: warned and left the link",
           "symlink" in (r.stderr or "").lower() and os.path.islink(link))
        ok("symlink: the real key survives",
           os.path.isfile(real) and sha(real) == real_sha)

        # A hard link to the real key is left, and the real key is not wiped.
        root, real, real_sha = setup_repo(tmp, "hardlink")
        hard = os.path.join(root, "target", "deploy", "sumofrog-keypair.json")
        os.link(real, hard)
        r = run_remove(root)
        ok("hard link: exit 0", r.returncode == 0)
        ok("hard link: warned and left both names",
           "link count" in (r.stderr or "").lower()
           and os.path.isfile(hard) and os.path.isfile(real)
           and os.stat(hard).st_ino == os.stat(real).st_ino)
        ok("hard link: the real key survives",
           os.path.isfile(real) and sha(real) == real_sha
           and os.stat(real).st_size > 0
           and stat.S_ISREG(os.stat(real).st_mode))

        # A symlinked target/deploy folder is left, and the file in it survives.
        root, real, real_sha = setup_repo(tmp, "linkdir")
        other = os.path.join(tmp, "linkdir-other-deploy")
        os.makedirs(other)
        # Put the real key under the other folder, then point target/deploy at it.
        named = os.path.join(other, "sumofrog-keypair.json")
        os.rename(real, named)
        os.rmdir(os.path.join(root, "target", "deploy"))
        os.symlink(other, os.path.join(root, "target", "deploy"))
        r = run_remove(root)
        ok("symlinked dir: exit 0", r.returncode == 0)
        ok("symlinked dir: warned and left the folder link",
           "symlink" in (r.stderr or "").lower()
           and os.path.islink(os.path.join(root, "target", "deploy")))
        ok("symlinked dir: the real key survives",
           os.path.isfile(named) and sha(named) == real_sha)

        # Missing file is a no-op.
        root, real, real_sha = setup_repo(tmp, "missing")
        r = run_remove(root)
        ok("missing file: exit 0 and no warning",
           r.returncode == 0 and "warning" not in (r.stderr or "").lower())
        ok("missing file: the real key survives",
           os.path.isfile(real) and sha(real) == real_sha)

        # No repo-root argument: refuse and do not touch a same-named file
        # in the current folder.
        decoy = os.path.join(tmp, "decoy")
        os.makedirs(os.path.join(decoy, "target", "deploy"))
        decoy_key = make_key(os.path.join(decoy, "target", "deploy", "sumofrog-keypair.json"))
        decoy_sha = sha(decoy_key)
        r = subprocess.run(
            ["bash", SCRIPT],
            cwd=decoy,
            capture_output=True,
            text=True,
        )
        err = (r.stderr or "").lower()
        ok("missing argument: exit non-zero", r.returncode != 0)
        ok("missing argument: message says the root is required",
           "required" in err or "usage" in err)
        ok("missing argument: did not delete the decoy file",
           os.path.isfile(decoy_key) and sha(decoy_key) == decoy_sha)

        # No .keys/program.json: leave the stray (this is the clean-checkout case).
        nokeys = os.path.join(tmp, "nokeys")
        os.makedirs(os.path.join(nokeys, "target", "deploy"))
        leftover = make_key(os.path.join(nokeys, "target", "deploy", "sumofrog-keypair.json"))
        leftover_sha = sha(leftover)
        r = run_remove(nokeys)
        ok("missing .keys/program.json: exit 0 and warned",
           r.returncode == 0 and "program.json" in (r.stderr or "").lower())
        ok("missing .keys/program.json: left the stray",
           os.path.isfile(leftover) and sha(leftover) == leftover_sha)

        # .keys/program.json is a symlink: leave the stray and the real key.
        root, real, real_sha = setup_repo(tmp, "key-symlink")
        outside = make_key(os.path.join(tmp, "key-symlink-outside.json"))
        os.remove(real)
        os.symlink(outside, real)
        stray = make_key(os.path.join(root, "target", "deploy", "sumofrog-keypair.json"))
        stray_sha = sha(stray)
        outside_sha = sha(outside)
        r = run_remove(root)
        ok("symlinked .keys/program.json: exit 0 and warned",
           r.returncode == 0 and "symlink" in (r.stderr or "").lower())
        ok("symlinked .keys/program.json: left the stray",
           os.path.isfile(stray) and sha(stray) == stray_sha)
        ok("symlinked .keys/program.json: the real key survives",
           os.path.isfile(outside) and sha(outside) == outside_sha
           and os.path.islink(real))

        # A separate byte-identical copy of the live key is a duplicate, so
        # removing it is safe. The live key is left alone.
        root, real, real_sha = setup_repo(tmp, "duplicate")
        dup = os.path.join(root, "target", "deploy", "sumofrog-keypair.json")
        shutil.copy2(real, dup)
        os.chmod(dup, 0o600)
        ok("duplicate: two separate files with the same hash",
           os.stat(dup).st_ino != os.stat(real).st_ino
           and sha(dup) == real_sha
           and os.stat(dup).st_nlink == 1)
        r = run_remove(root)
        ok("duplicate: exit 0 and the copy was removed",
           r.returncode == 0 and not os.path.lexists(dup))
        ok("duplicate: the live key survives",
           os.path.isfile(real) and sha(real) == real_sha)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"stray keypair checks: {passed} passed")


if __name__ == "__main__":
    main()
