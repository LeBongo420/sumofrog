#!/usr/bin/env python3
"""Build the v4 (8-bit synthwave) web pages from their sources.

  docs/whitepaper.md   -> docs/whitepaper.html
  docs/mining-guide.md -> docs/mining-guide.html
  (template below)     -> docs/index.html    (home page)
  (template below)     -> stats/index.html   (the stats page served by the Sumo gateway)
  mockups_8bit/v4      -> home header + metadata frog in docs/, stats/ and assets/
  art/pixy             -> per-page headers, $SUMO token logo and favicons

Fonts (Press Start 2P, DotGothic16, SIL OFL) are embedded in each page, so every page is one
self-contained file plus its images. Usage: python3 scripts/build_site.py  (needs `markdown`, Pillow)
"""
import argparse
import base64
import os
import re
import shutil

import markdown
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V4 = os.path.join(ROOT, "mockups_8bit", "v4")
FONTS = os.path.join(ROOT, "docs", "fonts")


def font_face(family, file):
    data = base64.b64encode(open(os.path.join(FONTS, file), "rb").read()).decode()
    return (f'@font-face {{ font-family:"{family}"; src:url(data:font/woff2;base64,{data}) format("woff2"); '
            f'font-display:swap; }}')


CSS = """
:root { --navy:#0e1030; --navy2:#1e2660; --purple:#581c70; --magenta:#ff248c; --pink:#ff78be;
        --yellow:#ffe440; --white:#fffaf0; --grey:#a0a0b8; --black:#000; --neon:#78ff60; --orange:#ff9238;
        --pixel:"Press Start 2P", monospace; --body:"VT323", "Press Start 2P", monospace; }
* { box-sizing:border-box; }
html { background:var(--black); }
body { margin:0; color:var(--white); font-family:var(--body); font-size:22px; line-height:1.55;
       background:var(--navy); min-height:100vh; }
.wrap { max-width:960px; margin:0 auto; background:var(--navy); box-shadow:0 0 0 4px var(--black), 0 0 0 8px var(--magenta); }
.hero { display:block; width:100%; height:auto; image-rendering:pixelated; border-bottom:4px solid var(--black); }
nav { display:flex; flex-wrap:wrap; gap:12px; align-items:center; padding:12px 16px; background:var(--navy);
      border-bottom:4px solid var(--magenta); }
nav .mascot { width:48px; height:48px; image-rendering:pixelated; flex:0 0 48px; border:3px solid var(--black); background:var(--navy); }
nav a, nav span.tag { font-family:var(--pixel); font-size:14px; line-height:1; padding:9px 10px; color:var(--white);
      text-decoration:none; border:3px solid var(--grey); background:var(--navy2); }
nav a:hover, nav a:focus { border-color:var(--yellow); color:var(--yellow); }
nav a[aria-current] { background:var(--white); color:var(--black); border-color:var(--white); }
nav a[aria-current]::before { content:"> "; }
nav span.tag { margin-left:auto; background:var(--white); color:var(--black); border-color:var(--white); }
main { padding:28px 36px 40px; }
h1, h2, h3 { font-family:var(--pixel); font-weight:normal; line-height:1.5; }
h1 { font-size:24px; color:var(--yellow); text-shadow:3px 3px 0 var(--magenta); margin:.4em 0 .3em; }
h3 { font-size:13px; color:var(--pink); margin:0 0 1.4em; }
h2 { font-size:16px; color:var(--yellow); margin:2.2em 0 .8em; padding:10px 0 10px 14px;
     border-left:8px solid var(--magenta); background:linear-gradient(90deg, var(--navy2), transparent); }
h2::before { content:"\\25B6  "; color:var(--white); }
p, li { max-width:46em; }
strong { color:var(--yellow); }
em { color:var(--pink); }
a { color:var(--yellow); text-decoration:underline; text-decoration-thickness:2px; text-underline-offset:3px; }
blockquote { clear:both; margin:1.4em 0; padding:14px 18px; background:var(--black); border:4px solid var(--yellow); }
blockquote p { margin:0; }
blockquote strong:first-child { background:var(--yellow); color:var(--black); padding:0 .3em; }
table { border-collapse:collapse; margin:1.2em 0; width:100%; }
th, td { border:3px solid var(--navy2); padding:.45em .8em; text-align:left; vertical-align:middle; }
th { font-family:var(--pixel); font-size:12px; font-weight:normal; color:var(--yellow); background:var(--black); }
tr:nth-child(even) td { background:rgba(30,38,96,.55); }
code { font-family:Consolas, "DejaVu Sans Mono", monospace; font-size:.9em; color:var(--neon); background:var(--black);
       padding:.1em .35em; }
hr { border:0; height:4px; margin:2em 0; background:repeating-linear-gradient(90deg, var(--magenta) 0 12px, transparent 12px 20px); }
img { max-width:100%; }
main p > img { display:block; margin:1em 0 .3em; border:4px solid var(--black); box-shadow:0 0 0 3px var(--grey); image-rendering:auto; }
.logo { float:right; width:128px; height:128px; image-rendering:pixelated; margin:0 0 1em 1.5em; }
footer { padding:16px 36px 24px; border-top:4px solid var(--magenta); color:var(--grey); font-size:15px; }
@media (max-width:640px) { main { padding:18px 16px 28px; } h1 { font-size:18px; } h2 { font-size:13px; }
  .logo { width:84px; height:84px; } nav a, nav span.tag { font-size:11px; } body { font-size:20px; } }
"""


DEFAULT_HEADER = (
    "sumo_header.png",
    "SUMO: the frog you mine. An 8-bit sumo frog under a synthwave sunset, with a torii gate, a pagoda and a cherry tree.",
    960, 144,
)
GUIDE_HEADER = (
    "header_guide.jpg",
    "SUMO mining guide. An 8-bit sumo frog holding a pickaxe and a book, under a synthwave sunset with a torii gate, a pagoda and a cherry blossom tree.",
    1200, 675,
)
PAPER_HEADER = (
    "header_whitepaper.jpg",
    "SUMO whitepaper. An 8-bit sumo frog wearing glasses and holding a paper, next to the $SUMO token (a navy coin with a teal-to-purple rim and a cream belt knot), under a synthwave sunset with a torii gate and pagoda.",
    1200, 675,
)
STATS_HEADER = (
    "header_stats.jpg",
    "SUMO network stats. An 8-bit sumo frog with arms raised next to a computer showing a chart and a coin, under a synthwave sunset with a torii gate, a pagoda and a cherry blossom tree.",
    1200, 675,
)


def page(title, nav, body, foot="", script="", header=None):
    src, alt, width, height = header or DEFAULT_HEADER
    fonts = font_face("Press Start 2P", "PressStart2P-latin.woff2") + "\n" + font_face("VT323", "VT323-latin.woff2")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="favicon-16.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<style>{fonts}
{CSS}</style></head>
<body><div class="wrap">
<img class="hero" src="{src}" alt="{alt}" width="{width}" height="{height}">
<nav><img class="mascot" src="sumo_frog_icon.png" alt="The Sumo Frog mascot: a smiling 8-bit frog face in a neon pink frame." width="48" height="48">{nav}<span class="tag">TESTNET</span></nav>
<main>
{body}
</main>
<footer>{foot}Test coins on a test chain: worthless, can't be bought or sold. Not an investment.</footer>
</div>{script}</body></html>
"""


def docs_nav(current):
    items = [("index.html", "HOME"), ("mining-guide.html", "GUIDE"), ("whitepaper.html", "PAPER"),
             ("../stats/index.html", "STATS")]
    return "".join(f'<a href="{h}"{" aria-current=page" if h == current else ""}>{t}</a>' for h, t in items)


def md_page(src, out, title, foot="", header=None):
    body = markdown.markdown(open(os.path.join(ROOT, "docs", src), encoding="utf-8").read(), extensions=["tables"])
    body = '<img class="logo" src="sumo_logo.png" alt="The $SUMO token: a dark navy coin with a teal-to-purple rim and a cream sumo belt knot." width="128" height="128">\n' + body
    html = page(title, docs_nav(out), body, foot, header=header)
    open(os.path.join(ROOT, "docs", out), "w", encoding="utf-8").write(html)
    print("wrote docs/" + out)


STATS_BODY = """<img class="logo" src="sumo_logo.png" alt="The $SUMO token: a dark navy coin with a teal-to-purple rim and a cream sumo belt knot." width="128" height="128">
<h1>SUMO FROG ($SUMO)</h1>
<h3>A toy proof-of-work token on a Solana test network</h3>
<blockquote><p><strong>TEST CHAIN</strong> Network: <span id="net">...</span>. Test SUMO is worthless and can't be bought or sold.</p></blockquote>
<p id="err" role="alert"></p>
<div class="grid" id="cards"></div>
<h2>TOP MINERS</h2>
<table id="top"><tr><th>#</th><th>WALLET</th><th>SUMO</th></tr></table>
<h2>RECENT ACTIVITY</h2>
<table id="recent"><tr><th>WHEN</th><th>TRANSACTION</th></tr></table>
"""

STATS_CSS = """
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:14px; margin:1em 0 0; clear:both; }
.card { padding:12px 14px; background:var(--black); border:3px solid var(--grey); color:var(--grey); font-size:15px; line-height:1.4; }
.card b { display:block; margin-top:8px; font-family:var(--pixel); font-weight:normal; font-size:15px; color:var(--white); line-height:1.5; }
.card.hi { border-color:var(--yellow); } .card.hi b { color:var(--yellow); }
#err:not(:empty) { padding:10px 14px; background:var(--white); color:var(--black); }
#err:not(:empty)::before { content:"!! "; font-weight:bold; }
td:first-child { font-family:var(--pixel); font-size:12px; }
"""

STATS_SCRIPT = """
<script src="sumo_config.js"></script>
<script src="stats.js"></script>
<script>
const qs = new URLSearchParams(location.search);
// One setting: SUMO.network is "private" (default) or "devnet".
// Served by the private gateway itself (port 8080): talk to this same origin.
// Public https website, or opened as a file: use the config RPC (not this page's origin).
function defaultRpc() {
  const net = String(SUMO.network || "private").toLowerCase();
  if (net === "devnet" || net === "public-devnet") return SUMO.devnet_rpc;
  if (location.protocol === "http:" && location.port === "8080") return location.origin;
  return SUMO.rpc;
}
const RPC = qs.get("rpc") || defaultRpc();
const isDevnet = RPC.includes("devnet.solana.com");
const isLocal = RPC.includes("127.0.0.1") || RPC.includes("localhost");
document.getElementById("net").textContent = isDevnet ? "Solana devnet" : isLocal ? "local test validator" : "private Sumo test network";
const cl = isLocal ? "custom&customUrl=" + encodeURIComponent(RPC) : "devnet";
// The public explorer can't read the private network, so links only appear on devnet/local.
const ex = (kind, id) => (isDevnet || isLocal) ? `https://explorer.solana.com/${kind}/${id}?cluster=${cl}` : null;
const link = (url, text) => url ? `<a href="${url}">${text}</a>` : text;
const short = (s) => s.slice(0, 4) + "..." + s.slice(-4);
const fmt = (n) => Number(n).toLocaleString("en-GB", { maximumFractionDigits: 2 });
for (const [id, addr] of [["plink", SUMO.program_id], ["mlink", SUMO.mint]]) {
  const a = document.getElementById(id); const u = ex("address", addr); if (u) a.href = u; a.textContent = short(addr);
}
async function refresh() {
  try {
    const { config: c, top, recent } = await loadStats(RPC, SUMO);
    const ago = Math.round(Date.now() / 1000 - Number(c.lastSolveTs));
    const nextHalving = (c.blocksMined / c.halvingInterval + 1n) * c.halvingInterval;
    const cards = [
      ["BLOCKS MINED", fmt(c.blocksMined), true],
      ["BLOCK REWARD", fmt(Number(c.nextReward) / 1e9) + " SUMO", true],
      ["HALVING IN", fmt(nextHalving - c.blocksMined) + " blocks"],
      ["DIFFICULTY", c.difficultyBits.toFixed(2) + " bits"],
      ["GUESSES PER BLOCK", "~" + fmt(2 ** c.difficultyBits / 1e6) + "M"],
      ["SUPPLY", fmt(Number(c.totalMinted) / 1e9) + " / " + fmt(Number(c.maxSupply) / 1e9)],
      ["LAST BLOCK", c.blocksMined > 0n ? (ago < 120 ? ago + "s ago" : Math.round(ago / 60) + " min ago") : "none yet"],
      ["TARGET BLOCK TIME", c.targetBlockTime + "s"],
    ];
    document.getElementById("cards").innerHTML = cards.map(([k, v, hi]) => `<div class="card${hi ? " hi" : ""}">${k}<b>${v}</b></div>`).join("");
    document.getElementById("top").innerHTML = "<tr><th>#</th><th>WALLET</th><th>SUMO</th></tr>" +
      top.map((t, i) => `<tr><td>${i + 1}</td><td>${link(ex("address", t.owner), `<code>${short(t.owner)}</code>`)}</td><td>${fmt(t.amount)}</td></tr>`).join("");
    document.getElementById("recent").innerHTML = "<tr><th>WHEN</th><th>TRANSACTION</th></tr>" +
      recent.map((r) => `<tr><td>${r.time ? new Date(r.time * 1000).toLocaleString("en-GB") : "?"}</td><td>${link(ex("tx", r.sig), `<code>${short(r.sig)}</code>`)}</td></tr>`).join("");
    document.getElementById("err").textContent = "";
  } catch (e) { document.getElementById("err").textContent = e.message; }
}
refresh(); setInterval(refresh, 20000);
</script>
"""



HOME_BODY = """<img class="logo" src="sumo_logo.png" alt="The $SUMO token: a dark navy coin with a teal-to-purple rim and a cream sumo belt knot." width="128" height="128">
<h1>SUMO FROG ($SUMO)</h1>
<h3>The frog you mine. A fair-launch proof-of-work coin on Solana.</h3>
<blockquote><p><strong>NOT LAUNCHED</strong> $SUMO currently lives only on a <strong>private test network</strong>
(and Solana's public test networks for experiments). Test SUMO is <strong>worthless</strong>, cannot be bought or
sold, and will never carry over to any later network. This site is a preview.</p></blockquote>
<p>Sumo Frog is a hobby project: a token anyone can earn by doing a little work with their own computer, under rules
written down in advance. The idea is borrowed openly from Bitcoin. The mascot is an 8-bit sumo frog.</p>
<p>There is no company, no team allocation, no sale and no roadmap of promises. There is a program, a set of rules,
and whoever chooses to mine.</p>
<h2>THE RULES IN BRIEF</h2>
<table>
<tr><th>RULE</th><th>VALUE</th></tr>
<tr><td>Block reward</td><td><strong>20 SUMO</strong> per block</td></tr>
<tr><td>Block time</td><td>about <strong>one block per 60 seconds</strong></td></tr>
<tr><td>Halving</td><td>about <strong>once a year</strong> (every 525,600 blocks)</td></tr>
<tr><td>Maximum supply</td><td><strong>21,000,000 SUMO</strong></td></tr>
<tr><td>Premine</td><td><strong>none</strong> — creator starts at zero</td></tr>
<tr><td>Liquidity from creator</td><td><strong>none</strong> — no pool funded by the creator</td></tr>
</table>
<p>Mine it with your PC. Every SUMO comes from a solved block. When testing is done, the upgrade key will be given up
on the launch network so the rules can no longer change.</p>
<h2>HOW TO MINE</h2>
<p>On the test network, friends can run a small Windows miner: download the zip, install Python if needed, and
double-click <strong>Mine SUMO</strong>. Full steps, screenshots and safety notes are in the guide.</p>
<p><a href="mining-guide.html">Open the mining guide →</a></p>
<h2>LINKS</h2>
<ul>
<li><a href="whitepaper.html">Whitepaper</a> — the full rules</li>
<li><a href="mining-guide.html">Mining guide</a> — how to run the test miner</li>
<li><a href="../stats/index.html">Stats</a> — live blocks, reward and top miners (needs the test gateway)</li>
<li><a href="https://github.com/LeBongo420/sumofrog">Code on GitHub</a> — private for now; link is a placeholder until the repo is published</li>
</ul>
<p>There are <strong>no official social media accounts</strong>. The author's personal X handle is
<a href="https://x.com/lebongo420">lebongo420</a>. Any other account claiming to speak for Sumo Frog is not official.</p>
"""


def home_page():
    body = HOME_BODY
    foot = 'Author: lebongo420 &middot; hobby / learning project<br>'
    html = page("SUMO FROG ($SUMO)", docs_nav("index.html"), body, foot)
    open(os.path.join(ROOT, "docs", "index.html"), "w", encoding="utf-8").write(html)
    print("wrote docs/index.html")


def stats_page():
    global CSS
    base = CSS
    CSS = base + STATS_CSS
    nav = '<a href="../docs/index.html">HOME</a><a href="./" aria-current=page>STATS</a>'
    foot = 'Program <a id="plink"></a> &middot; Mint <a id="mlink"></a> &middot; refreshes every 20s<br>'
    html = page("SUMO FROG ($SUMO) stats", nav, STATS_BODY, foot, STATS_SCRIPT, header=STATS_HEADER)
    CSS = base
    open(os.path.join(ROOT, "stats", "index.html"), "w", encoding="utf-8").write(html)
    print("wrote stats/index.html")


def save_jpeg(src, dest, max_w=1200, quality=85):
    im = Image.open(src).convert("RGB")
    if im.width > max_w:
        height = int(round(im.height * max_w / im.width))
        im = im.resize((max_w, height), Image.Resampling.LANCZOS)
    im.save(dest, "JPEG", quality=quality, optimize=True)


def images():
    pixy = os.path.join(ROOT, "art", "pixy")
    hdr = Image.open(os.path.join(V4, "site_header.png")).convert("RGB").crop((0, 0, 960, 144))
    frog = Image.open(os.path.join(V4, "sumo_frog_512.png")).convert("RGBA")
    # Pixy's $SUMO token: favicon and small logo. Home still uses the thin v4 header.
    # The frog stays the mascot (headers + metadata image), not the token.
    token_256 = os.path.join(pixy, "token_256.png")
    token_32 = os.path.join(pixy, "token_32.png")
    token_16 = os.path.join(pixy, "token_16.png")
    frog_icon = Image.open(os.path.join(pixy, "frog_icon.png")).convert("RGBA")
    touch = frog_icon.resize((180, 180), Image.Resampling.NEAREST)
    for d in ("docs", "stats"):
        dest = os.path.join(ROOT, d)
        hdr.save(os.path.join(dest, "sumo_header.png"), optimize=True)
        shutil.copy(token_256, os.path.join(dest, "sumo_logo.png"))
        shutil.copy(token_32, os.path.join(dest, "favicon-32.png"))
        shutil.copy(token_16, os.path.join(dest, "favicon-16.png"))
        frog_icon.save(os.path.join(dest, "sumo_frog_icon.png"), optimize=True)
        touch.save(os.path.join(dest, "apple-touch-icon.png"), optimize=True)
    save_jpeg(os.path.join(pixy, "header_guide.jpg"), os.path.join(ROOT, "docs", "header_guide.jpg"))
    save_jpeg(os.path.join(pixy, "header_whitepaper.jpg"), os.path.join(ROOT, "docs", "header_whitepaper.jpg"))
    save_jpeg(os.path.join(pixy, "header_stats.jpg"), os.path.join(ROOT, "stats", "header_stats.jpg"))
    # token metadata image (the gateway serves it as /sumo_frog.png): 512px pixel frog on navy
    meta = Image.new("RGBA", (512, 512), (14, 16, 48, 255))
    meta.alpha_composite(frog)
    meta.convert("RGB").save(os.path.join(ROOT, "stats", "sumo_frog.png"), optimize=True)
    shutil.copy(os.path.join(ROOT, "stats", "sumo_frog.png"), os.path.join(ROOT, "assets", "sumo_frog.png"))
    print("wrote header, logo and metadata images")



# ---- public-site publish guard ----
# Never copy the real stats/sumo_config.js (it may hold the private server address).
# Publish only the example (YOUR_SERVER placeholder) or a devnet-only setting.
EXAMPLE_STATS = os.path.join(ROOT, "stats", "sumo_config.example.js")
LIVE_STATS = os.path.join(ROOT, "stats", "sumo_config.js")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DEVNET_HOST = "api.devnet.solana.com"
# Web files copied into a publish folder. Source markdown, fonts and screens stay out.
DOCS_PUBLISH = (
    "index.html", "mining-guide.html", "whitepaper.html",
    "sumo_header.png", "sumo_logo.png", "sumo_frog_icon.png",
    "favicon-16.png", "favicon-32.png", "apple-touch-icon.png",
    "header_guide.jpg", "header_whitepaper.jpg",
)
STATS_PUBLISH = (
    "index.html", "stats.js", "sumo_header.png", "sumo_logo.png", "sumo_frog_icon.png",
    "sumo_frog.png", "favicon-16.png", "favicon-32.png", "apple-touch-icon.png",
    "header_stats.jpg",
)


def stats_config_is_publishable(text):
    """True only for the YOUR_SERVER example or a config that talks to public devnet alone."""
    if IPV4.search(text):
        return False
    urls = [u.rstrip('",;') for u in re.findall(r'https?://\S+', text)]
    if not urls:
        return False

    def ok_url(u):
        return "YOUR_SERVER" in u or DEVNET_HOST in u

    if not all(ok_url(u) for u in urls):
        return False
    if "YOUR_SERVER" in text:
        return True
    return all(DEVNET_HOST in u for u in urls)


def publishable_stats_config(kind="example"):
    """Build a stats config from the example file only — never from stats/sumo_config.js."""
    text = open(EXAMPLE_STATS, encoding="utf-8").read()
    if kind == "example":
        out = text
    elif kind == "devnet":
        out = text.replace('"network": "private"', '"network": "devnet"', 1)
        out = out.replace('"rpc": "http://YOUR_SERVER:8080"', f'"rpc": "https://{DEVNET_HOST}"', 1)
    else:
        raise SystemExit('stats network must be "example" or "devnet"')
    if not stats_config_is_publishable(out):
        raise SystemExit("refusing to publish a stats config that is not the example or a devnet setting")
    return out


def write_publishable_stats_config(dest_dir, kind="example"):
    dest_dir = os.path.abspath(dest_dir)
    live_dir = os.path.abspath(os.path.join(ROOT, "stats"))
    if dest_dir == live_dir:
        raise SystemExit("refusing to write a published config into the live stats/ folder")
    dest = os.path.join(dest_dir, "sumo_config.js")
    if os.path.isfile(LIVE_STATS) and os.path.isfile(dest):
        try:
            if os.path.samefile(dest, LIVE_STATS):
                raise SystemExit("refusing to overwrite the real stats/sumo_config.js")
        except OSError:
            pass
    os.makedirs(dest_dir, exist_ok=True)
    open(dest, "w", encoding="utf-8").write(publishable_stats_config(kind))
    return dest


def stage_public_site(dest, kind="example"):
    """Copy the website into dest, with only a publishable stats config (never the real one)."""
    dest = os.path.abspath(dest)
    if dest == ROOT or dest.startswith(os.path.join(ROOT, "stats")) or dest.startswith(os.path.join(ROOT, "docs")):
        # Allow a folder *inside* /tmp etc.; only refuse writing over the live trees.
        if dest == os.path.abspath(os.path.join(ROOT, "stats")) or dest == os.path.abspath(os.path.join(ROOT, "docs")) or dest == ROOT:
            raise SystemExit("refusing to stage the public site over the live repo folders")
    os.makedirs(dest, exist_ok=True)
    for name in DOCS_PUBLISH:
        src = os.path.join(ROOT, "docs", name)
        if not os.path.isfile(src):
            raise SystemExit(f"missing docs/{name}; run this script without --publish-dir first")
        shutil.copy2(src, os.path.join(dest, name))
    stats_dest = os.path.join(dest, "stats")
    os.makedirs(stats_dest, exist_ok=True)
    for name in STATS_PUBLISH:
        if name == "sumo_config.js":
            raise SystemExit("internal error: real stats config must not be in the copy list")
        src = os.path.join(ROOT, "stats", name)
        if not os.path.isfile(src):
            raise SystemExit(f"missing stats/{name}")
        shutil.copy2(src, os.path.join(stats_dest, name))
    # Explicitly skip LIVE_STATS and the example filename (the published file is always sumo_config.js).
    write_publishable_stats_config(stats_dest, kind)
    published = open(os.path.join(stats_dest, "sumo_config.js"), encoding="utf-8").read()
    if not stats_config_is_publishable(published):
        os.remove(os.path.join(stats_dest, "sumo_config.js"))
        raise SystemExit("publish guard failed: staged stats config is not publishable")
    if os.path.isfile(LIVE_STATS):
        try:
            if os.path.samefile(os.path.join(stats_dest, "sumo_config.js"), LIVE_STATS):
                raise SystemExit("publish guard failed: staged config is the live file")
        except OSError:
            pass
    print("staged public site in", dest, f"(stats config: {kind})")
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Sumo Frog website, or stage a public copy")
    ap.add_argument("--publish-dir", help="copy the built site here with only the example or devnet stats config")
    ap.add_argument("--stats-network", choices=("example", "devnet"), default="example",
                    help="which stats config to put in --publish-dir (default: example with YOUR_SERVER)")
    args = ap.parse_args(argv)
    if args.publish_dir:
        return stage_public_site(args.publish_dir, args.stats_network)
    images()
    home_page()
    md_page("whitepaper.md", "whitepaper.html", "SUMO FROG ($SUMO) whitepaper (draft)", header=PAPER_HEADER)
    md_page("mining-guide.md", "mining-guide.html", "How to mine SUMO FROG ($SUMO)", header=GUIDE_HEADER)
    stats_page()


if __name__ == "__main__":
    main()
