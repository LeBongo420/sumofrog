#!/usr/bin/env python3
"""Render a captured console screen (ANSI truecolor text) to a PNG, roughly how Windows cmd shows it.
Used to make screenshots of the miner without a Windows machine.
Usage: python3 scripts/ansi_to_png.py capture.txt out.png [columns]"""
import re
import sys

from PIL import Image, ImageDraw, ImageFont

CW, CH = 10, 20
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
BOLD = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 16)
DEF_FG, DEF_BG = (204, 204, 204), (12, 12, 12)  # cmd defaults
SGR = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


def parse(text, cols):
    grid, row = [], []
    fg, bg, bold = DEF_FG, DEF_BG, False
    pos = 0

    def newline():
        nonlocal row
        grid.append(row)
        row = []

    while pos < len(text):
        m = SGR.match(text, pos)
        if m:
            args, cmd = m.group(1), m.group(2)
            pos = m.end()
            if cmd == "m":
                p = [int(x) for x in args.split(";") if x] or [0]
                i = 0
                while i < len(p):
                    if p[i] == 0:
                        fg, bg, bold = DEF_FG, DEF_BG, False
                    elif p[i] == 1:
                        bold = True
                    elif p[i] == 38 and p[i + 1] == 2:
                        fg = tuple(p[i + 2:i + 5]); i += 4
                    elif p[i] == 48 and p[i + 1] == 2:
                        bg = tuple(p[i + 2:i + 5]); i += 4
                    i += 1
            elif cmd == "H":
                grid, row = [], []
            continue
        c = text[pos]
        pos += 1
        if c == "\n":
            newline()
        elif c == "\r":
            row = []
        elif len(row) < cols:
            row.append((c, fg, bg, bold))
    if row:
        grid.append(row)
    return grid


def render(text, out, cols=120):
    grid = parse(text, cols)
    while grid and not grid[-1]:
        grid.pop()
    rows = max(len(grid), 1)
    img = Image.new("RGB", (cols * CW + 16, rows * CH + 16), DEF_BG)
    d = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, (c, f, b, bold) in enumerate(row):
            X, Y = 8 + x * CW, 8 + y * CH
            d.rectangle([X, Y, X + CW - 1, Y + CH - 1], fill=b)
            if c == "\u2580":
                d.rectangle([X, Y, X + CW - 1, Y + CH // 2 - 1], fill=f)
            elif c == "\u2588":
                d.rectangle([X, Y, X + CW - 1, Y + CH - 1], fill=f)
            elif c != " ":
                d.text((X, Y + 1), c, font=BOLD if bold else FONT, fill=f)
    img.save(out)


if __name__ == "__main__":
    render(open(sys.argv[1], encoding="utf-8").read(), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 120)
