#!/usr/bin/env python3
"""Offline checks for the public-site publish dest guard and the miner zip path.
No network. Run: python3 tests/site_publish_checks.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import build_site as b  # noqa: E402
import build_zips as z  # noqa: E402

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


def write_site(path, marker):
    os.makedirs(path, exist_ok=True)
    open(os.path.join(path, "marker.txt"), "w", encoding="utf-8").write(marker)


def swap_public_site(base):
    """Run the documented repeat-safe swap in a stand-in of /home/ubuntu/sumo."""
    subprocess.run(["rm", "-rf", os.path.join(base, "site.old")], check=True)
    subprocess.run(
        ["mv", "-T", os.path.join(base, "site"), os.path.join(base, "site.old")],
        check=True,
    )
    subprocess.run(
        ["mv", "-T", os.path.join(base, "site.new"), os.path.join(base, "site")],
        check=True,
    )


def main():
    stats = os.path.realpath(os.path.join(b.ROOT, "stats"))
    docs = os.path.realpath(os.path.join(b.ROOT, "docs"))

    msg = refused(b.stage_public_site, stats).lower()
    ok("stage refuses the live stats/ folder", "stats" in msg or "docs" in msg)
    msg = refused(b.stage_public_site, docs).lower()
    ok("stage refuses the live docs/ folder", "stats" in msg or "docs" in msg)
    msg = refused(b.stage_public_site, b.ROOT).lower()
    ok("stage refuses the repo root", "stats" in msg or "docs" in msg or "live" in msg)
    inside = os.path.join(stats, "published-by-mistake")
    msg = refused(b.stage_public_site, inside).lower()
    ok("stage refuses a folder inside stats/", "stats" in msg or "docs" in msg)
    inside_docs = os.path.join(docs, "published-by-mistake")
    msg = refused(b.stage_public_site, inside_docs).lower()
    ok("stage refuses a folder inside docs/", "stats" in msg or "docs" in msg)

    tmp = tempfile.mkdtemp()
    link_stats = os.path.join(tmp, "link-to-stats")
    os.symlink(stats, link_stats)
    msg = refused(b.stage_public_site, link_stats).lower()
    ok("stage refuses a symlink to stats/", "stats" in msg or "docs" in msg)
    # The live stats page must be unchanged after the refused symlink dest.
    ok("symlink dest did not overwrite stats/index.html", os.path.isfile(os.path.join(stats, "index.html")))

    link_docs = os.path.join(tmp, "link-to-docs")
    os.symlink(docs, link_docs)
    msg = refused(b.stage_public_site, link_docs).lower()
    ok("stage refuses a symlink to docs/", "stats" in msg or "docs" in msg)

    msg = refused(b.write_publishable_stats_config, stats).lower()
    ok("write config refuses the live stats/ folder", "stats" in msg or "docs" in msg)
    link_cfg = os.path.join(tmp, "link-cfg-stats")
    os.symlink(stats, link_cfg)
    msg = refused(b.write_publishable_stats_config, link_cfg).lower()
    ok("write config refuses a symlink to stats/", "stats" in msg or "docs" in msg)
    msg = refused(b.write_publishable_stats_config, docs).lower()
    ok("write config refuses the live docs/ folder", "stats" in msg or "docs" in msg)

    dest = os.path.join(tmp, "public")
    b.stage_public_site(dest, "example")
    published = open(os.path.join(dest, "stats", "sumo_config.js"), encoding="utf-8").read()
    ok("staged example config is publishable", b.stats_config_is_publishable(published))
    ok("staged example uses YOUR_SERVER", "YOUR_SERVER" in published)
    ok("staged example has no raw IPv4", b.IPV4.search(published) is None)
    ok("home page was staged", os.path.isfile(os.path.join(dest, "index.html")))
    ok("stats page was staged under dest/stats", os.path.isfile(os.path.join(dest, "stats", "index.html")))
    # dest/stats is not the live tree
    ok("staged stats dir is not the live stats/ tree",
       os.path.realpath(os.path.join(dest, "stats")) != stats)
    ok("staged stats config is a regular file",
       os.path.isfile(os.path.join(dest, "stats", "sumo_config.js"))
       and not os.path.islink(os.path.join(dest, "stats", "sumo_config.js")))
    cfg_path = os.path.join(dest, "stats", "sumo_config.js")
    ok("published stats/sumo_config.js is mode 644",
       (os.stat(cfg_path).st_mode & 0o777) == 0o644)
    published_modes = []
    for dirpath, _dirnames, filenames in os.walk(dest):
        for name in filenames:
            published_modes.append(os.stat(os.path.join(dirpath, name)).st_mode & 0o777)
    ok("all published files are mode 644",
       published_modes and all(mode == 0o644 for mode in published_modes))

    msg = refused(b.stage_public_site, dest, "example").lower()
    ok("stage refuses a non-empty publish folder", "non-empty" in msg)

    empty = os.path.join(tmp, "empty-real")
    os.mkdir(empty)
    link_empty = os.path.join(tmp, "link-empty")
    os.symlink(empty, link_empty)
    msg = refused(b.stage_public_site, link_empty).lower()
    ok("stage refuses a symlink publish folder", "symlink" in msg)

    with_link = os.path.join(tmp, "has-symlink")
    os.mkdir(with_link)
    os.symlink(os.path.join(dest, "index.html"), os.path.join(with_link, "sneaky"))
    msg = refused(b.stage_public_site, with_link).lower()
    ok("stage refuses a publish folder that contains a symlink", "symlink" in msg)

    # A symlink already sitting at the dest config must be replaced, not followed.
    canary_dir = os.path.join(tmp, "canary-dir")
    os.mkdir(canary_dir)
    canary = os.path.join(tmp, "live-canary.js")
    open(canary, "w", encoding="utf-8").write("LIVE_SECRET_SHOULD_STAY")
    planted = os.path.join(canary_dir, "sumo_config.js")
    os.symlink(canary, planted)
    b.write_publishable_stats_config(canary_dir, "example")
    ok("atomic write replaces a planted symlink",
       not os.path.islink(planted) and os.path.isfile(planted))
    ok("atomic write did not follow the planted symlink",
       open(canary, encoding="utf-8").read() == "LIVE_SECRET_SHOULD_STAY")
    ok("atomic write put a publishable config in place",
       b.stats_config_is_publishable(open(planted, encoding="utf-8").read()))

    # oracle_ip: both the local-config path and the missing-source path.
    src_dir = os.path.join(tmp, "addr-sources")
    os.mkdir(src_dir)
    missing = os.path.join(src_dir, "missing.md")
    msg = refused(z.oracle_ip, (missing,)).lower()
    ok("oracle_ip fails when the address source is missing",
       "source" in msg and ("found" in msg or "missing" in msg))

    cfg = os.path.join(src_dir, "sumo_config.json")
    open(cfg, "w", encoding="utf-8").write('{"rpc": "http://203.0.113.50:8080", "network": "private"}\n')
    ips = z.oracle_ip(sources=(cfg,))
    ok("oracle_ip reads an address from a local config", ips == (b"203.0.113.50",))

    md = os.path.join(src_dir, "ORACLE.md")
    open(md, "w", encoding="utf-8").write("host is `198.51.100.25` in the notes\n")
    ips = z.oracle_ip(sources=(md,))
    ok("oracle_ip reads an address from an oracle markdown file", ips == (b"198.51.100.25",))

    loopback = os.path.join(src_dir, "loopback.json")
    open(loopback, "w", encoding="utf-8").write('{"rpc": "http://127.0.0.1:8080"}\n')
    msg = refused(z.oracle_ip, (loopback,)).lower()
    ok("oracle_ip fails when the source has no usable address", "usable" in msg)

    # Explicit tmp files only, so this works on a clean checkout with no ORACLE.md.
    multi = os.path.join(src_dir, "multi.txt")
    open(multi, "w", encoding="utf-8").write(
        "version 1.2.3.4 and host 203.0.113.50 and also 127.0.0.1\n"
    )
    ips = z.oracle_ip(sources=(multi,))
    ok("oracle_ip returns every usable address in a source",
       ips == (b"1.2.3.4", b"203.0.113.50"))

    ips = z.oracle_ip(sources=(cfg, md, loopback, missing))
    ok("oracle_ip collects addresses from every source",
       ips == (b"203.0.113.50", b"198.51.100.25"))

    msg = refused(
        z.check_payload, "icon.ico", b"payload 198.51.100.25 only",
        (b"203.0.113.50", b"198.51.100.25"),
    ).lower()
    ok("check_payload refuses the second address too", "address" in msg)
    msg = refused(
        z.check_payload, "icon.ico", b"payload 203.0.113.50 only",
        (b"203.0.113.50", b"198.51.100.25"),
    ).lower()
    ok("check_payload refuses the first address", "address" in msg)
    z.check_payload("icon.ico", b"no addresses here", (b"203.0.113.50", b"198.51.100.25"))
    ok("check_payload allows a payload with none of the addresses", True)

    # Miner zip is packed from git (HEAD), not the working tree.
    data = z.git_show("miner/sumo_config.example.json")
    ok("zip git_show reads the example config", b"YOUR_SERVER" in data)
    try:
        z.git_show("miner/sumo_config.json")
        packed_real = True
    except SystemExit:
        packed_real = False
    ok("zip git_show refuses the ignored real miner config", not packed_real)
    try:
        z.git_show("stats/sumo_config.js")
        packed_stats = True
    except SystemExit:
        packed_stats = False
    ok("zip git_show refuses the ignored real stats config", not packed_stats)

    readme = open(os.path.join(b.ROOT, "server", "README.md"), encoding="utf-8").read()
    ok("README swap removes site.old first",
       "rm -rf /home/ubuntu/sumo/site.old" in readme)
    ok("README swap uses mv -T",
       "mv -T /home/ubuntu/sumo/site /home/ubuntu/sumo/site.old" in readme
       and "mv -T /home/ubuntu/sumo/site.new /home/ubuntu/sumo/site" in readme)

    swap_root = os.path.join(tmp, "sumo")
    os.makedirs(swap_root)
    write_site(os.path.join(swap_root, "site"), "v1")
    write_site(os.path.join(swap_root, "site.new"), "v2")
    swap_public_site(swap_root)
    ok("first swap puts the new site live",
       open(os.path.join(swap_root, "site", "marker.txt"), encoding="utf-8").read() == "v2")
    ok("first swap kept the previous site as site.old",
       open(os.path.join(swap_root, "site.old", "marker.txt"), encoding="utf-8").read() == "v1")
    ok("first swap did not nest folders",
       not os.path.exists(os.path.join(swap_root, "site.old", "site"))
       and not os.path.exists(os.path.join(swap_root, "site", "site")))

    write_site(os.path.join(swap_root, "site.new"), "v3")
    swap_public_site(swap_root)
    ok("second swap puts the newer site live",
       open(os.path.join(swap_root, "site", "marker.txt"), encoding="utf-8").read() == "v3")
    ok("second swap replaced site.old rather than nesting",
       open(os.path.join(swap_root, "site.old", "marker.txt"), encoding="utf-8").read() == "v2"
       and not os.path.exists(os.path.join(swap_root, "site.old", "site"))
       and not os.path.exists(os.path.join(swap_root, "site", "site")))

    write_site(os.path.join(swap_root, "site.new"), "v4")
    swap_public_site(swap_root)
    ok("third swap still updates the live site",
       open(os.path.join(swap_root, "site", "marker.txt"), encoding="utf-8").read() == "v4")
    ok("third swap still does not nest folders",
       open(os.path.join(swap_root, "site.old", "marker.txt"), encoding="utf-8").read() == "v3"
       and not os.path.exists(os.path.join(swap_root, "site.old", "site"))
       and not os.path.exists(os.path.join(swap_root, "site", "site")))

    # ---- tidy devnet zip layout: only SUMO Frog.bat (one menu launcher) + START HERE on top, the rest in files/ ----
    miner_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "miner")
    top = [a for a, _ in z.DEVNET_TOP]
    ok("devnet top level is only START HERE.txt and the SUMO Frog.bat launcher",
       sorted(top) == sorted(["START HERE.txt", "SUMO Frog.bat"]))
    ok("devnet layout: one folder deep, only files/",
       all(a.count("/") <= 1 and (a.count("/") == 0 or a.startswith("files/")) for a, _ in z.DEVNET_LAYOUT))
    ok("devnet layout: every source exists", all(os.path.isfile(os.path.join(miner_dir, src)) for _, src in z.DEVNET_LAYOUT))
    ok("devnet layout: no example config, config + wallet-free",
       "files/sumo_config.json" in [a for a, _ in z.DEVNET_LAYOUT]
       and not any("key" in a.lower() and a.endswith(".json") for a, _ in z.DEVNET_LAYOUT))
    repo_root = os.path.join(miner_dir, "..")

    def staged(src):  # the bytes git stores (the index), which is what build_zips packs
        r = subprocess.run(["git", "show", f":miner/{src}"], cwd=repo_root, capture_output=True)
        assert r.returncode == 0, src
        return r.stdout
    raw = {arc: staged(src) for arc, src in z.DEVNET_LAYOUT
           if arc.endswith((".bat", ".txt")) and not arc.endswith("requirements.txt")}
    ok("every devnet .bat and guide is plain ASCII", all(all(c < 128 for c in d) for d in raw.values()))
    ok("every devnet .bat and guide is stored in git with Windows (CRLF) line endings only (index, not the working copy)",
       all(d.count(b"\r\n") == d.count(b"\n") and d.count(b"\r") == d.count(b"\n") for d in raw.values()))
    launcher = open(os.path.join(miner_dir, "devnet", "SUMO Frog.bat"), encoding="utf-8").read()
    ok("launcher: runs from files/, calls _start.bat first, and stops (code 2) or fails (code 1) before the menu",
       'cd /d "%~dp0files"' in launcher and 'call "%~dp0files\\_start.bat"' in launcher
       and launcher.index("call \"%~dp0files\\_start.bat\"") < launcher.index(":menu")
       and launcher.index("if errorlevel 2 goto stopsafe") < launcher.index("if errorlevel 1 goto fail") < launcher.index(":menu")
       and "%~dp0_setup" not in launcher)
    lines = [l.strip() for l in launcher.splitlines()]
    menu_items = [l for l in lines if l.startswith("echo") and l.split()[1:2] and l.split()[1] in "123456"]
    ok("launcher menu: 1 Mine SUMO, 2 Check balance, 3 Get test SOL, 4 Set payout address, 5 Withdraw SOL, 6 Exit",
       [" ".join(l.split()[1:]) for l in menu_items] == ["1 Mine SUMO", "2 Check balance", "3 Get test SOL",
                                                       "4 Set payout address", "5 Withdraw SOL", "6 Exit"])
    order = ["if errorlevel 6 goto bye", "if errorlevel 5 goto withdraw", "if errorlevel 4 goto payout",
             "if errorlevel 3 goto faucet", "if errorlevel 2 goto balance", "if errorlevel 1 goto mine"]
    pos = [launcher.find(x) for x in order]
    ok("launcher menu keys are tested highest first: 6, 5, 4, 3, 2, 1 (the other way round would make every key mine)",
       all(p >= 0 for p in pos) and pos == sorted(pos))
    ok("launcher never passes --yes (or -y) to anything: Withdraw and Set payout always ask",
       not any(tok.lower() in ("--yes", "-y", "/y") for l in lines for tok in l.split()))
    ok("launcher keeps its Withdraw / Set payout screens that say nothing is sent until you type y",
       "nothing is sent until you type  y" in launcher)
    miner_src = open(os.path.join(miner_dir, "sumo_miner.py"), encoding="utf-8").read()
    wd = miner_src[miner_src.index("def cmd_withdraw"):miner_src.index("def _worker")]
    ok("sumo_miner.py withdraw still asks 'Send now? [y/N]' unless --yes is given, and the launcher never gives it",
       'input("Send now? [y/N] ")' in wd and "if not args.yes:" in wd and "--yes" not in launcher)
    sp = miner_src[miner_src.index("def cmd_set_payout"):miner_src.index("def cmd_withdraw")]
    ok("sumo_miner.py set-payout still asks to type YES", 'input("Type YES to save it: ")' in sp)
    for label, call in (("payout", 'sumo_miner.py set-payout -- "%ADDR%"'), ("withdraw", 'sumo_miner.py withdraw -- "%ADDR%"')):
        sec = launcher[launcher.index("\n:" + label + "\n"):]
        sec = sec[:sec.index("\n:done\n")] if label == "withdraw" else sec[:sec.index("\n:withdraw\n")]
        strip = 'set "ADDR=%ADDR:"=%"'
        ok(f"launcher :{label} strips double quotes from the pasted address before using it",
           strip in sec and sec.index(strip) < sec.index(call))
        ok(f"launcher :{label} passes the address after -- so it can never be read as an option", call in sec)
    ok("launcher warns when any of the five old buttons sits next to it, before the menu",
       all(f'if exist "%~dp0{n}" set "OLDBTN=1"' in launcher for n in
           ("Mine SUMO.bat", "Check balance.bat", "Get test SOL.bat", "Set payout address.bat", "Withdraw SOL.bat"))
       and launcher.index("if defined OLDBTN goto oldbuttons") < launcher.index(":menu"))
    old_block = launcher[launcher.index("\n:oldbuttons\n"):]
    old_block = old_block[:old_block.index("\n:bye\n")]
    ok("old-button warning: says delete the five buttons, never the wallet, and returns to the menu",
       "Please delete the five old buttons" in old_block and "NEVER delete sumo-devnet-key.json" in old_block
       and "SECOND wallet" in old_block and "goto menu" in old_block
       and all(n in old_block for n in ("Mine SUMO.bat", "Check balance.bat", "Get test SOL.bat",
                                        "Set payout address.bat", "Withdraw SOL.bat")))
    ok("launcher MINING line escapes both arrows (^>^>)", "echo  ^>^> MINING" in launcher and ">^>" not in launcher.replace("^>^>", ""))
    ok("launcher no longer sends people to menu option 3 for test SOL (faucet.solana.com is the real route)",
       "choose 3" not in launcher and "https://faucet.solana.com" in launcher)
    ok("launcher: a single key press picks 1-6; any other key (or Ctrl+C) goes back to the menu, not to mining",
       "choice /c 123456 /n" in launcher and "if errorlevel 6 goto bye" in launcher
       and launcher.index("if errorlevel 1 goto mine") < launcher.index("goto menu", launcher.index("if errorlevel 1 goto mine")))
    def section(label, until=None):
        text = launcher[launcher.index("\n:" + label + "\n"):]
        return text[:text.index("\n:" + until + "\n")] if until else text[:text.index("\n:", 5)]
    for label, cmd, until in (("mine", "mine", "balance"), ("balance", "balance", None), ("faucet", "faucet", None),
                              ("payout", "set-payout", None), ("withdraw", "withdraw", None)):
        ok(f"launcher :{label} runs sumo_miner.py {cmd} with the venv python",
           f'"%PY%" sumo_miner.py {cmd}' in section(label, until))
    for label in ("balance", "faucet", "payout", "withdraw"):
        ok(f"launcher :{label} comes back to the menu afterwards", "goto done" in section(label) or "goto menu" in section(label))
    done_block = launcher[launcher.index("\n:done\n"):]
    done_block = done_block[:done_block.index("\n:", 5)]
    ok("launcher :done pauses and returns to the menu", "pause" in done_block and "goto menu" in done_block)
    ok("launcher: after mining stops it pauses and returns to the menu, and failures return too",
       "Mining stopped." in launcher and launcher.count("goto menu") >= 5 and ":action_failed" in launcher)
    ok("launcher has no ( ) blocks, so a folder like 'sumo (1)' (a repeat download) can't break it",
       not any(l.endswith("(") or l.startswith(")") or l.lower().startswith(("else", "for ")) for l in lines))
    ok("launcher :withdraw sends an address only when one was typed",
       "if defined ADDR goto withdraw_to" in launcher and '"%PY%" sumo_miner.py withdraw -- "%ADDR%"' in launcher)
    ok("launcher never copies, moves or deletes anything",
       not any(w in l.lower().split()[:1] for l in lines for w in ("copy", "move", "del", "erase", "rmdir", "xcopy")))
    mine = launcher[launcher.index("\n:mine\n"):]
    mine = mine[:mine.index("\n:balance\n")]
    ok("launcher :mine looks for the wallet inside files/ first", mine.index("%~dp0files\\sumo-devnet-key.json") < mine.index("new-key"))
    ok("launcher: no old per-button .bat files are packed",
       not any(a.endswith(".bat") and a not in ("SUMO Frog.bat", "files/_start.bat", "files/_setup.bat")
               for a, _ in z.DEVNET_LAYOUT))
    attrs = open(os.path.join(repo_root, ".gitattributes"), encoding="utf-8").read()
    ok(".gitattributes keeps .bat files and the devnet guides byte-for-byte (no line-ending conversion)",
       "*.bat -text" in attrs and "miner/devnet/*.txt -text" in attrs)
    chk = subprocess.run(["git", "check-attr", "text", "--", "miner/devnet/SUMO Frog.bat", "miner/devnet/_start.bat",
                          "miner/devnet/START HERE.txt", "miner/devnet/HOW TO MINE.txt", "miner/_setup.bat"],
                         cwd=repo_root, capture_output=True, text=True).stdout.splitlines()
    ok("git really treats those five files as no-conversion", len(chk) == 5 and all(l.endswith("text: unset") for l in chk))
    for bad in (b"echo hi\ngoto x\n", b"echo hi\r\ngoto x\n", b"echo hi\r\r\n", "echo caf\u00e9\r\n".encode("utf-8")):
        ok("build_zips refuses a .bat with a bare LF, a bare CR or a non-ASCII byte",
           "must be plain ASCII" in refused(z.check_windows_text, "SUMO Frog.bat", bad))
    z.check_windows_text("SUMO Frog.bat", b"echo hi\r\ngoto x\r\n")
    z.check_windows_text("files/requirements.txt", b"solders>=0.21\n")
    ok("build_zips accepts a clean CRLF .bat and leaves requirements.txt alone", True)
    # ---- wallet safety on update (Ribbit's note 1) ----
    start = open(os.path.join(miner_dir, "devnet", "_start.bat"), encoding="utf-8").read()
    lower = start.lower()
    ok("_start.bat warns 'two wallets found' and tells people not to delete the wallet",
       "TWO WALLETS FOUND" in start and "DON'T DELETE sumo-devnet-key.json" in start)
    two = 'if exist "%~dp0..\\sumo-devnet-key.json" if exist "%~dp0sumo-devnet-key.json" goto two_wallets'
    first_move = start.index('move "')
    ok("_start.bat checks for two wallets (and two payout files) BEFORE moving anything",
       two in start and start.index(two) < first_move
       and "goto two_payouts" in start and start.index("goto two_payouts") < first_move)
    ok("_start.bat stops with exit code 2 in every stop case",
       all(f":{lab}" in start for lab in ("two_wallets", "wallet_move_failed", "two_payouts", "payout_move_failed"))
       and start.count("exit /b 2") == 4)
    ok("_start.bat checks the wallet really moved before doing anything else",
       'if exist "%~dp0..\\sumo-devnet-key.json" goto wallet_move_failed' in start
       and start.index("goto wallet_move_failed") < start.index("call "))
    cmds = [l for l in start.splitlines() if not l.lower().startswith(("rem", "echo"))]
    ok("_start.bat only ever runs 'move' on the wallet and payout files: no copy, delete or overwrite",
       sum('move "' in l for l in cmds) == 2
       and not any(w in l.lower() for l in cmds for w in ("copy ", " del ", "erase", "rmdir", "move /y", "xcopy")))
    for lab in ("wallet_move_failed", "payout_move_failed"):
        block = start[start.index(":" + lab):]
        block = block[:block.index("exit /b 2")]
        block = " ".join(l[4:].strip() if l.lower().startswith("echo") else l for l in block.splitlines())
        ok(f"_start.bat :{lab} tells people to MOVE the file, not copy it",
           "MOVE it (do not copy)" in block and "copy it" not in block.lower().replace("do not copy", ""))
        ok(f"_start.bat :{lab} explains a leftover copy brings the stop back",
           "A copy left next to SUMO Frog.bat would make the miner stop again" in block)
    payout_block = start[start.index(":payout_move_failed"):]
    ok("_start.bat payout message does not assume the person has a wallet in files",
       "Your wallet is already" not in payout_block)
    ok("_start.bat has no 'copy it' anywhere in what it shows",
       "copy it" not in " ".join(l.lower() for l in start.splitlines() if l.lower().startswith("echo")))
    ok("_start.bat says no wallet was moved or made when it stops on two wallets",
       "No wallet was moved or made" in start and "Nothing was changed" not in start)
    ok("launcher stops safely on the two-wallet case and never makes a wallet then",
       "if errorlevel 2 goto stopsafe" in launcher and ":stopsafe" in launcher
       and 'if exist "%~dp0sumo-devnet-key.json" goto stopsafe' in mine
       and mine.index('if exist "%~dp0sumo-devnet-key.json" goto stopsafe') < mine.index("new-key"))
    for guide in ("START HERE.txt", "HOW TO MINE.txt"):
        text = open(os.path.join(miner_dir, "devnet", guide), encoding="utf-8").read()
        flat = " ".join(text.split())
        ok(f"{guide}: says never delete sumo-devnet-key.json", "NEVER delete sumo-devnet-key.json" in flat)
        ok(f"{guide}: no 'can be deleted' wording anywhere", "can be deleted" not in flat.lower()
           and "may be deleted" not in flat.lower())
        old_names = ("Mine SUMO.bat", "Check balance.bat", "Get test SOL.bat", "Set payout address.bat", "Withdraw SOL.bat")
        ok(f"{guide}: tells people to use SUMO Frog.bat and to delete the five old buttons by name (never the wallet)",
           "SUMO Frog.bat" in flat and "delete the five old buttons" in flat and "SECOND wallet" in flat
           and all(n in flat for n in old_names)
           and "never sumo-devnet-key.json" in flat and "Delete only those five .bat files" in flat)
        ok(f"{guide}: never tells people to copy the wallet file",
           "copy sumo-devnet-key" not in flat.lower() and "copy it" not in flat.lower())
        ok(f"{guide}: explains the 'Two wallets found' stop", "Two wallets found" in flat)
    print(f"site publish checks: {passed} passed")


if __name__ == "__main__":
    main()
