#!/usr/bin/env python3
"""Build miner/sumo_art.py: the console miner's pixel frames, in the approved v4 look.

Usage: python3 scripts/make_miner_art.py   (needs Pillow; the miner itself doesn't)

Each frame is a small pixel scene (60 x 42 px, one character per pixel per row pair in the
console, drawn with half-block characters) using the v4 16-colour synthwave palette and the v4
frog sprite from mockups_8bit/v4/art.py. Also writes PNG previews to mockups_8bit/v4/console/.
"""
import math, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mockups_8bit", "v4"))
from art import (PAL, BLK, NAV, NV2, PUR, MAG, PNK, ORG, YEL, WHT, NEO, GRY, BAYER,
                 frog, outline, blank, comp)  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

W, H, HZ = 60, 42, 29          # scene size in pixels, horizon row
OUT = os.path.join(ROOT, "miner", "sumo_art.py")
PREV = os.path.join(ROOT, "mockups_8bit", "v4", "console")


def background(frame):
    im = Image.new("RGB", (W, H), PAL[NAV]); px = im.load(); d = ImageDraw.Draw(im)
    for y in range(HZ - 9, HZ):                      # dithered purple glow above the horizon
        f = (y - (HZ - 9)) / 9
        for x in range(W):
            if BAYER[y % 4][x % 4] / 16 < f: px[x, y] = PAL[PUR]
    random.seed(4)
    for _ in range(9):
        x, y = random.randrange(1, W - 1), random.randrange(1, 12); px[x, y] = PAL[WHT]
    # striped synthwave sun, off to the left so it doesn't sit on the frog's head
    cx, cy, r = 12, 13, 9
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                f = (y - (cy - r)) / (2 * r)
                c = YEL if f < 0.4 else ORG if f < 0.65 else MAG
                if c == ORG and BAYER[y % 4][x % 4] / 16 < (f - 0.4) * 2: c = YEL
                px[x, y] = PAL[c]
    for y in (cy + 2, cy + 5, cy + 7):
        for x in range(cx - r, cx + r + 1):
            if px[x, y] in (PAL[YEL], PAL[ORG], PAL[MAG]): px[x, y] = PAL[NAV]
    # Mt Fuji (left, in front of the sun's lower half) with a grey snow cap
    d.polygon([(0, HZ), (0, HZ - 2), (6, 21), (10, 21), (19, HZ)], fill=PAL[BLK])
    for y in range(21, 24):
        for x in range(3, 14):
            if px[x, y] == PAL[BLK] and (x + y) % 2 == 0: px[x, y] = PAL[GRY]
    # pagoda silhouette with lit windows (right)
    for t, (w, y) in enumerate([(12, HZ - 1), (10, HZ - 6), (8, HZ - 11), (6, HZ - 16)]):
        x0 = 51 - w // 2
        d.rectangle([x0, y - 4, x0 + w, y], fill=PAL[BLK])
        d.line([(x0 - 2, y - 4), (x0 + w + 2, y - 4)], fill=PAL[BLK])
        px[x0 - 2, y - 5] = PAL[BLK]; px[x0 + w + 2, y - 5] = PAL[BLK]
        px[51, y - 2] = PAL[YEL]
    d.line([(51, HZ - 25), (51, HZ - 20)], fill=PAL[BLK])
    # small neon torii gate (left of the frog)
    tx, ty = 16, HZ - 1
    d.line([(tx + 1, ty - 7), (tx + 1, ty)], fill=PAL[MAG]); d.line([(tx + 7, ty - 7), (tx + 7, ty)], fill=PAL[MAG])
    d.line([(tx - 1, ty - 9), (tx + 9, ty - 9)], fill=PAL[MAG]); d.line([(tx, ty - 6), (tx + 8, ty - 6)], fill=PAL[MAG])
    # neon horizon and perspective grid floor
    d.line([(0, HZ), (W, HZ)], fill=PAL[MAG])
    d.rectangle([0, HZ + 1, W, H], fill=PAL[BLK])
    for y in (HZ + 3, HZ + 7, HZ + 12):
        d.line([(0, y), (W, y)], fill=PAL[MAG])
    for k in range(-7, 8):
        d.line([(30 + k * 5, HZ), (30 + k * 20, H + 8)], fill=PAL[MAG])
    # the sumo ring (dohyo): purple, white rope circle
    d.ellipse([8, 32, 51, 41], fill=PAL[PUR], outline=PAL[PNK])
    d.ellipse([16, 34, 43, 39], outline=PAL[WHT])
    # stone lanterns at the ring corners
    for lx in (4, 55):
        d.rectangle([lx - 2, 30, lx + 2, 34], fill=PAL[GRY], outline=PAL[BLK]); px[lx, 32] = PAL[YEL]
        d.line([(lx - 3, 29), (lx + 3, 29)], fill=PAL[GRY]); d.line([(lx, 35), (lx, 38)], fill=PAL[GRY])
        d.line([(lx - 2, 39), (lx + 2, 39)], fill=PAL[GRY])
    # drifting cherry-blossom petals (move each frame)
    random.seed(9)
    for _ in range(6):
        x0, y0 = random.randrange(W), random.randrange(HZ)
        x = (x0 + frame * 2) % W; y = (y0 + frame * 3) % HZ
        px[x, y] = PAL[PNK]
        if x + 1 < W: px[x + 1, y] = PAL[WHT]
    return im


def sprite(pose):
    g = frog(pose, 40)
    im = Image.new("RGBA", (32, 40), (0, 0, 0, 0))
    for y, row in enumerate(g):
        for x, c in enumerate(row):
            if c is not None: im.putpixel((x, y), PAL[c] + (255,))
    return im


def spark(px, cx, cy, r, c):
    for k in range(-r, r + 1):
        for x, y in ((cx + k, cy), (cx, cy + k)):
            if 0 <= x < W and 0 <= y < H: px[x, y] = PAL[WHT if k == 0 else c]


def coin(px, cx, cy):
    for y in range(cy - 3, cy + 4):
        for x in range(cx - 3, cx + 4):
            if (x - cx) ** 2 + (y - cy) ** 2 <= 10: px[x, y] = PAL[YEL]
            elif (x - cx) ** 2 + (y - cy) ** 2 <= 16: px[x, y] = PAL[BLK]
    px[cx - 1, cy - 1] = PAL[WHT]
    for y in range(cy - 2, cy + 3): px[cx + 1, y] = PAL[ORG]


def scene(pose, frame, fx=0, found=False):
    im = background(frame); sp = sprite(pose); im.paste(sp, (14, 0), sp); px = im.load()
    if fx == 1:
        spark(px, 18, 36, 2, YEL); spark(px, 41, 36, 2, YEL)
    elif fx == 2:
        spark(px, 17, 33, 1, YEL); spark(px, 42, 33, 1, YEL)
    if found:
        coin(px, 26, 4); coin(px, 46, 6)
        for p in ((20, 8), (50, 14), (36, 2), (11, 25)): spark(px, p[0], p[1], 1, YEL)
    return im


def to_rows(im):
    idx = {c: "0123456789ABCDEF"[i] for i, c in enumerate(PAL)}
    return ["".join(idx[im.getpixel((x, y))] for x in range(W)) for y in range(H)]


# mini "SUMO" logotype, 5x7 letters, yellow top / orange bottom (4 console rows)
LET = {"S": [".####", "##...", "##...", ".###.", "...##", "...##", "####."],
       "U": ["##.##"] * 6 + [".###."],
       "M": ["#...#", "##.##", "#####", "#.#.#", "#...#", "#...#", "#...#"],
       "O": [".###.", "##.##", "##.##", "##.##", "##.##", "##.##", ".###."]}


def logo_rows():
    w = 4 * 6 + 1
    g = [[NAV] * w for _ in range(8)]
    for i, ch in enumerate("SUMO"):
        for y, row in enumerate(LET[ch]):
            for x, c in enumerate(row):
                if c == "#": g[y][1 + i * 6 + x] = YEL if y < 4 else ORG
    return ["".join("0123456789ABCDEF"[c] for c in r) for r in g]


def main():
    frames = {
        "mine": [to_rows(scene("up", 0)), to_rows(scene("down", 1, fx=1)), to_rows(scene("down", 2, fx=2)),
                 to_rows(scene("up", 3)), to_rows(scene("down", 4, fx=1)), to_rows(scene("down", 5, fx=2))],
        "found": [to_rows(scene("victory", 6, found=True))],
    }
    os.makedirs(PREV, exist_ok=True)
    for i, f in enumerate(frames["mine"][:3] + frames["found"]):
        im = Image.new("RGB", (W, H))
        for y, r in enumerate(f):
            for x, ch in enumerate(r): im.putpixel((x, y), PAL[int(ch, 16)])
        im.resize((W * 8, H * 8), Image.NEAREST).save(os.path.join(PREV, f"scene_{i}.png"))
    with open(OUT, "w") as fh:
        fh.write('"""Pixel frames for the Sumo Frog console miner. GENERATED by scripts/make_miner_art.py, do not edit.\n\n'
                 "Each frame is a list of rows; each character is one pixel, an index into PALETTE (hex digit).\n"
                 'Two pixel rows become one console line, drawn with the upper-half-block character."""\n')
        fh.write(f"PALETTE = {PAL!r}\n")
        fh.write(f"LOGO = {logo_rows()!r}\n")
        fh.write("FRAMES = {\n")
        for k, fl in frames.items():
            fh.write(f"    {k!r}: [\n")
            for f in fl:
                fh.write("        [\n" + "".join(f"            {r!r},\n" for r in f) + "        ],\n")
            fh.write("    ],\n")
        fh.write("}\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
