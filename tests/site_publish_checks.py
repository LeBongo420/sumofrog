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

    print(f"site publish checks: {passed} passed")


if __name__ == "__main__":
    main()
