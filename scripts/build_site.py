#!/usr/bin/env python3
"""Build the v4 (8-bit synthwave) web pages from their sources.

  docs/whitepaper.md   -> docs/whitepaper.html
  docs/mining-guide.md -> docs/mining-guide.html
  (template below)     -> docs/index.html    (home page)
  (template below)     -> stats/index.html   (the stats page served by the Sumo gateway)
  mockups_8bit/v4      -> header + logo images in docs/, stats/ and assets/

Fonts (Press Start 2P, DotGothic16, SIL OFL) are embedded in each page, so every page is one
self-contained file plus its images. Usage: python3 scripts/build_site.py  (needs `markdown`, Pillow)
"""
import base64
import os
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
.hero { display:block; width:100%; image-rendering:pixelated; border-bottom:4px solid var(--black); }
nav { display:flex; flex-wrap:wrap; gap:12px; align-items:center; padding:12px 16px; background:var(--navy);
      border-bottom:4px solid var(--magenta); }
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


def page(title, nav, body, foot="", script=""):
    fonts = font_face("Press Start 2P", "PressStart2P-latin.woff2") + "\n" + font_face("VT323", "VT323-latin.woff2")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="icon" href="sumo_logo.png">
<style>{fonts}
{CSS}</style></head>
<body><div class="wrap">
<img class="hero" src="sumo_header.png" alt="SUMO: the frog you mine. An 8-bit sumo frog under a synthwave sunset, with a torii gate, a pagoda and a cherry tree." width="960" height="144">
<nav>{nav}<span class="tag">TESTNET</span></nav>
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


def md_page(src, out, title, foot=""):
    body = markdown.markdown(open(os.path.join(ROOT, "docs", src), encoding="utf-8").read(), extensions=["tables"])
    body = '<img class="logo" src="sumo_logo.png" alt="" width="128" height="128">\n' + body
    html = page(title, docs_nav(out), body, foot)
    open(os.path.join(ROOT, "docs", out), "w", encoding="utf-8").write(html)
    print("wrote docs/" + out)


STATS_BODY = """<img class="logo" src="sumo_logo.png" alt="" width="128" height="128">
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
// Served by the Sumo gateway: talk to the same server. Opened as a file: use sumo_config.js.
const RPC = qs.get("rpc") || (location.protocol.startsWith("http") ? location.origin : SUMO.rpc);
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



HOME_BODY = """<img class="logo" src="sumo_logo.png" alt="Sumo Frog pixel logo" width="128" height="128">
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
<p>There are <strong>no official social media accounts</strong>. Any account claiming to speak for Sumo Frog is not
official. Author: <strong>lebongo420</strong>.</p>
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
    html = page("SUMO FROG ($SUMO) stats", nav, STATS_BODY, foot, STATS_SCRIPT)
    CSS = base
    open(os.path.join(ROOT, "stats", "index.html"), "w", encoding="utf-8").write(html)
    print("wrote stats/index.html")


def images():
    hdr = Image.open(os.path.join(V4, "site_header.png")).convert("RGB").crop((0, 0, 960, 144))
    frog = Image.open(os.path.join(V4, "sumo_frog_512.png")).convert("RGBA")
    logo = frog.resize((256, 256), Image.NEAREST)
    for d in ("docs", "stats"):
        hdr.save(os.path.join(ROOT, d, "sumo_header.png"), optimize=True)
        logo.save(os.path.join(ROOT, d, "sumo_logo.png"), optimize=True)
    # token metadata image (the gateway serves it as /sumo_frog.png): 512px pixel frog on navy
    meta = Image.new("RGBA", (512, 512), (14, 16, 48, 255))
    meta.alpha_composite(frog)
    meta.convert("RGB").save(os.path.join(ROOT, "stats", "sumo_frog.png"), optimize=True)
    shutil.copy(os.path.join(ROOT, "stats", "sumo_frog.png"), os.path.join(ROOT, "assets", "sumo_frog.png"))
    print("wrote header, logo and metadata images")


if __name__ == "__main__":
    images()
    home_page()
    md_page("whitepaper.md", "whitepaper.html", "SUMO FROG ($SUMO) whitepaper (draft)")
    md_page("mining-guide.md", "mining-guide.html", "How to mine SUMO FROG ($SUMO)")
    stats_page()
