#!/usr/bin/env python3
"""Offline checks for the public-site publish dest guard and the miner zip path.
No network. Run: python3 tests/site_publish_checks.py
"""
import os
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

    print(f"site publish checks: {passed} passed")


if __name__ == "__main__":
    main()
