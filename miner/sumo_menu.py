"""The Sumo Frog main menu screen (Pixy's design): an 80 x 30 truecolour console picture.

Pure drawing, no network and no files: sumo_miner.py gives it the version, the short wallet text and the
balance text, and prints what it returns. Never given a secret key, only text that is safe to show.
Art: two stacked art pixels become one console cell with the half block characters (U+2580, U+2584,
U+2588). This file is plain ASCII (the special characters are written as unicode escapes).
"""

COLS, ROWS = 80, 30

NAVY, PANEL, BLACK = "#0E1030", "#161C4A", "#000000"
CREAM, GREY, PINK, LPINK = "#FFFAF0", "#A0A0B8", "#FF248C", "#FF78BE"
YELLOW, ORANGE, GREEN, TEAL = "#FFE440", "#FF9238", "#78FF60", "#00B8A8"
PURPLE, TAN = "#581C70", "#E2D6B6"
PIXEL = {'.': None, '#': BLACK, 'P': PINK, 'p': LPINK, 'Y': YELLOW, 'O': ORANGE, 'G': GREEN,
         'V': PURPLE, 'W': CREAM, 't': TAN, 'C': TEAL}

UP, DOWN, DOT, ARROW, FULL = "\u2580", "\u2584", "\u00b7", "\u25ba", "\u2588"
SINGLE = "\u2500\u2502\u250c\u2510\u2514\u2518"
DOUBLE = "\u2550\u2551\u2554\u2557\u255a\u255d"

# FROG is 28 x 32 art pixels, LOGO is 23 x 7 art pixels.
FROG = [
    '.#........................#.',
    '#G##....................##G#',
    'G##G#..................#G##G',
    '#GG#....................#GG#',
    '#GG#..####........####..#GG#',
    '#GG#.#WWWW########WWWW#.#GG#',
    '#GG#.#WW##GGGGGGGG##WW#.#GG#',
    '#GG##GWW##GGGGGGGG##WWG##GG#',
    '#GG##GGGGGGGGGGGGGGGGGG##GG#',
    '#GG##GGGGGGCGGGGCGGGGGG##GG#',
    '#GG##G#GGGGGGGGGGGGGG#G##GG#',
    '#GGG#GG##############GG#GGG#',
    '.#GG#GGG#VVVVVVVVVV#GGG#GG#.',
    '.#GG#GGGG##########GGGG#GG#.',
    '.#GGG#GGGGGttttttGGGGG#GGG#.',
    '..#GG#GGGttttttttttGGG#GG#..',
    '..#GG#CGGttttttttttGGC#GG#..',
    '...##GGGttttttttttttGGG##...',
    '..##GCGGttttttttttttGGCG#V..',
    '...#CGGGttttttttttttGCGC#...',
    '...#GCGCGttttttttttGCGCG#...',
    '..##PPPPPPPPPPPPPPPPPPPP##..',
    '...#VVVVVVVVPPPPVVVVVVVV#...',
    '..#GGGGGGGG#PPPP#GGGGGGGG#..',
    '..#GCGGGG###PPPP###GGGGCG#..',
    '..#CGCGC#VV#VVVV#VV#CGCGC#..',
    '.#GCGC##VVVV####VVVV##CGCG#.',
    '#CCCCCC#VVVVVVVVVVVV#CCCCCC#',
    '.######VVVVVVVVVVVVVV######.',
    'VVVVVVWWWWWWWWWWWWWWWWVVVVVV',
    'ppppVVVVVVVVVVVVVVVVVVVVpppp',
    'PPPPppppppppppppppppppppPPPP',
]
LOGO = [
    '.YYYY.YY.YY.Y...Y..YYY.',
    'YY....YY.YY.YY.YY.YY.YY',
    'YY....YY.YY.YYYYY.YY.YY',
    '.YYY..YY.YY.Y.Y.Y.YY.YY',
    '...OO.OO.OO.O...O.OO.OO',
    '...OO.OO.OO.O...O.OO.OO',
    'OOOO...OOO..O...O..OOO.',
]

FROG[18] = FROG[18].replace('V', '.')   # one stray purple pixel from the crop

ITEMS = ["Mine SUMO", "Check balance", "Get test SOL", "Set payout address", "Withdraw SOL", "Exit"]
PROMPT = "Press a number from 1 to 6"
PROMPT_ROW = 26
PROMPT_COL = (COLS - len(PROMPT) - 2) // 2


def prompt_cursor():
    """1-based (row, column) where the console cursor should wait, on the block after the prompt."""
    return PROMPT_ROW + 1, PROMPT_COL + len(PROMPT) + 2


def build_grid(version, wallet_text, wallet_ok, balance_text, balance_ok, selected=1):
    """grid[row][col] = (char, fg_hex, bg_hex) for the whole 80 x 30 screen.
    wallet_ok / balance_ok False = show the text in grey (no wallet, offline) instead of green / yellow."""
    grid = [[(" ", None, NAVY) for _ in range(COLS)] for _ in range(ROWS)]

    def put(r, c, text, fg=CREAM, bg=NAVY):
        for i, ch in enumerate(text):
            if 0 <= c + i < COLS:
                grid[r][c + i] = (ch, fg, bg)

    def fill(r, c0, c1, bg):
        for c in range(c0, c1 + 1):
            grid[r][c] = (" ", None, bg)

    def box(r0, c0, r1, c1, style, fg, bg):
        h, v, tl, tr, bl, br = style
        for c in range(c0 + 1, c1):
            put(r0, c, h, fg, bg)
            put(r1, c, h, fg, bg)
        for r in range(r0 + 1, r1):
            put(r, c0, v, fg, bg)
            put(r, c1, v, fg, bg)
        put(r0, c0, tl, fg, bg)
        put(r0, c1, tr, fg, bg)
        put(r1, c0, bl, fg, bg)
        put(r1, c1, br, fg, bg)

    def blit(sprite, r0, c0, xscale=1, yscale=1):
        rows = [row for row in sprite for _ in range(yscale)]
        if len(rows) % 2:
            rows.append("." * len(rows[0]))
        for cr in range(len(rows) // 2):
            for x in range(len(rows[0])):
                top, bot = PIXEL[rows[2 * cr][x]], PIXEL[rows[2 * cr + 1][x]]
                if top is None and bot is None:
                    continue
                if top == bot:
                    cell = (FULL, top, NAVY)
                elif top is None:
                    cell = (DOWN, bot, NAVY)
                elif bot is None:
                    cell = (UP, top, NAVY)
                else:
                    cell = (UP, top, bot)
                for k in range(xscale):
                    grid[r0 + cr][c0 + x * xscale + k] = cell

    for r, c, ch, col in [(0, 36, DOT, CREAM), (0, 53, "+", YELLOW), (0, 70, DOT, CREAM), (8, 34, DOT, CREAM),
                          (8, 62, DOT, CREAM), (8, 75, "+", LPINK), (11, 31, DOT, CREAM), (16, 6, DOT, CREAM),
                          (16, 72, DOT, CREAM), (25, 5, DOT, CREAM), (25, 75, "+", YELLOW)]:
        put(r, c, ch, col)

    blit(FROG, 0, 1)
    blit(LOGO, 1, 32, xscale=2, yscale=2)
    put(9, 32, "FROG MINER", CREAM)
    version = str(version)[:12]
    put(9, 77 - len(version), version, GREY)
    put(10, 32, "TEST COINS / TEST CHAIN", LPINK)

    box(12, 32, 15, 77, SINGLE, CREAM, PANEL)
    for r in (13, 14):
        fill(r, 33, 76, PANEL)
    wallet_text, balance_text = str(wallet_text)[:30], str(balance_text)[:30]
    put(13, 34, "WALLET", GREY, PANEL)
    put(13, 75 - len(wallet_text), wallet_text, GREEN if wallet_ok else GREY, PANEL)
    put(14, 34, "BALANCE", GREY, PANEL)
    put(14, 75 - len(balance_text), balance_text, YELLOW if balance_ok else GREY, PANEL)

    mc0, mc1 = 16, 63
    box(17, mc0, 24, mc1, DOUBLE, PINK, PANEL)
    put(17, mc0 + 2, " MAIN MENU ", YELLOW, PANEL)
    for i, label in enumerate(ITEMS):
        r = 18 + i
        if i + 1 == selected:      # highlighted row: dark text on a light bar plus an arrow
            fill(r, mc0 + 1, mc1 - 1, CREAM)
            put(r, mc0 + 2, ARROW, NAVY, CREAM)
            put(r, mc0 + 4, f"[{i + 1}]", NAVY, CREAM)
            put(r, mc0 + 8, label, NAVY, CREAM)
        else:
            fill(r, mc0 + 1, mc1 - 1, PANEL)
            put(r, mc0 + 4, f"[{i + 1}]", YELLOW, PANEL)
            put(r, mc0 + 8, label, CREAM, PANEL)

    put(PROMPT_ROW, PROMPT_COL, PROMPT, CREAM)
    put(PROMPT_ROW, PROMPT_COL + PROMPT.index("1"), "1", YELLOW)
    put(PROMPT_ROW, PROMPT_COL + PROMPT.index("6"), "6", YELLOW)
    put(PROMPT_ROW, PROMPT_COL + len(PROMPT) + 1, FULL, YELLOW)

    for c in range(COLS):
        grid[27][c] = (UP, PINK, PURPLE)
        grid[28][c] = (" ", None, BLACK)
        grid[29][c] = (UP, PURPLE, BLACK)
    for r, step in ((28, 6), (29, 12)):
        for k in range(-6, 7):
            c = 40 + step * k
            if 0 <= c < COLS:
                put(r, c, "|" if k == 0 else ("\\" if k > 0 else "/"), PINK, BLACK)

    for r in range(ROWS):               # blank cells take the colour of the cell before, so runs merge
        last = CREAM
        for c in range(COLS):
            ch, fg, bg = grid[r][c]
            if fg is None:
                fg = last
            else:
                last = fg
            grid[r][c] = (ch, fg, bg)
    return grid


def _rgb(hex_colour):
    return int(hex_colour[1:3], 16), int(hex_colour[3:5], 16), int(hex_colour[5:7], 16)


def to_ansi(grid, skip_last_cell=False):
    """The grid as ANSI 24-bit colour text. Every row is placed with an absolute cursor move (no line
    feeds, so nothing scrolls). skip_last_cell leaves out the bottom-right cell: writing it in a window
    that is exactly 30 rows tall can make some consoles scroll."""
    out = []
    for r, row in enumerate(grid):
        out.append(f"\x1b[{r + 1};1H")
        last = None
        cells = row[:-1] if (skip_last_cell and r == len(grid) - 1) else row
        for ch, fg, bg in cells:
            if (fg, bg) != last:
                f, b = _rgb(fg), _rgb(bg)
                out.append(f"\x1b[38;2;{f[0]};{f[1]};{f[2]};48;2;{b[0]};{b[1]};{b[2]}m")
                last = (fg, bg)
            out.append(ch)
        out.append("\x1b[0m")
    row, col = prompt_cursor()
    out.append(f"\x1b[{row};{col}H")
    return "".join(out)


def render(version, wallet_text, wallet_ok, balance_text, balance_ok, selected=1, skip_last_cell=False):
    return to_ansi(build_grid(version, wallet_text, wallet_ok, balance_text, balance_ok, selected), skip_last_cell)
