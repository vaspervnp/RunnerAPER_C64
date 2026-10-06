"""Draws the first set of graphics into gfx/png/<sheet>.png + .json.

The sheets are ordinary indexed PNGs in C64 colours, one pixel per
multicolor pixel: they can be painted over in Aseprite afterwards (then
that sheet is no longer regenerated from here: pass the sheet names to
redo, e.g. `python3 tools/mkgfx.py track font`).

The HUD icons, the power-ups and the runner are adapted from the CPC
sheets (../APERRunner/gfx/png); the rest is drawn for the C64's limits:
4 colours per cell, %11 fixed per screen column (assets64).

Art legend: '.' BG  'l' MC1  'm' MC2  'g' green  'y' yellow  'r' red
            'w' white  ' ' transparent / keep what is below
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assets64 as A  # noqa: E402
from c64palette import RGB, TRANSPARENT, colour, nearest, save_indices  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PNG = os.path.join(ROOT, "gfx", "png")
CPC_PNG = os.path.join(ROOT, "..", "APERRunner", "gfx", "png")

BG, MC1, MC2 = A.screen_colours()
LEGEND = {".": BG, "l": MC1, "m": MC2, "g": colour("green"), "y": colour("yellow"),
          "r": colour("red"), "w": colour("white"), "k": colour("black"), "b": colour("blue"),
          "c": colour("cyan"), "o": colour("orange"), " ": TRANSPARENT}


# --- canvas helpers ---------------------------------------------------------
def blank(w, h, c=BG):
    return [[c] * w for _ in range(h)]


def art(lines):
    return [[LEGEND[ch] for ch in line] for line in lines]


def over(dst, src, x=0, y=0):
    """Paints src onto dst (transparent pixels keep dst). Returns dst."""
    for j, row in enumerate(src):
        for i, c in enumerate(row):
            if c != TRANSPARENT and 0 <= y + j < len(dst) and 0 <= x + i < len(dst[0]):
                dst[y + j][x + i] = c
    return dst


def hline(img, x0, x1, y, c):
    for x in range(max(0, x0), min(len(img[0]) - 1, x1) + 1):
        img[y][x] = c


def vline(img, x, y0, y1, c):
    for y in range(y0, y1 + 1):
        img[y][x] = c


def flip_v(img):
    return [row[:] for row in img[::-1]]


def flip_h(img):
    return [row[::-1] for row in img]


def copy(img):
    return [row[:] for row in img]


def write_sheet(name, frames):
    """frames: list of (frame name, pixel rows). One row of frames, left to right."""
    h = max(len(px) for _, px in frames)
    w = sum(len(px[0]) for _, px in frames)
    sheet = blank(w, h, TRANSPARENT)
    meta, x = [], 0
    for fname, px in frames:
        over(sheet, [[c for c in row] for row in px], x, 0)
        for j, row in enumerate(px):           # keep transparency inside frames
            for i, c in enumerate(row):
                sheet[j][x + i] = c
        fw, fh = len(px[0]), len(px)
        meta.append({"filename": fname, "frame": {"x": x, "y": 0, "w": fw, "h": fh}})
        x += fw
    os.makedirs(PNG, exist_ok=True)
    save_indices(os.path.join(PNG, name + ".png"), sheet)
    with open(os.path.join(PNG, name + ".json"), "w") as f:
        json.dump({"frames": meta, "meta": {"pixel_aspect": "2:1" if name not in ("runner_outline", "shadow") else "1:1"}},
                  f, indent=1)


# --- track (28x8, columns: edge red | 5 yellow | edge red) -------------------
RAIL_L, RAIL_R = 5, 22
SLEEPERS = (1, 2, 5, 6)
WAGON_L, WAGON_R = 2, 25


def rail(variant=0):
    img = blank(28, 8)
    specks = [(1, 0), (26, 3), (0, 6), (25, 7), (3, 4)] if variant == 0 else [(2, 2), (27, 5), (1, 7), (24, 1), (26, 6)]
    for x, y in specks:
        img[y][x] = MC2
    for y in SLEEPERS:
        hline(img, 3, 24, y, MC2)
    for x in (RAIL_L, RAIL_R):
        vline(img, x, 0, 7, MC1)
    return img


def coin_shapes():
    """4 phases of a 4x8 coin ('y' body, 'l' shine), transparent around."""
    return [
        art(["    ", " yy ", "yyly", "yyyy", "yyyy", "yyyy", " yy ", "    "]),
        art(["    ", " yy ", " yl ", " yy ", " yy ", " yy ", " yy ", "    "]),
        art(["    ", "  y ", "  y ", "  l ", "  y ", "  y ", "  y ", "    "]),
        art(["    ", " yy ", " ly ", " yy ", " yy ", " yy ", " yy ", "    "]),
    ]


def roof(livery, rows=8, vent=False):
    """Wagon roof seen from above, columns WAGON_L..WAGON_R. The middle column
    (x 12-15) is plain MC2 on both liveries: coins can sit on it."""
    img = blank(28, rows, TRANSPARENT)
    for y in range(rows):
        hline(img, WAGON_L, WAGON_R, y, MC1 if livery == 1 else MC2)
        img[y][WAGON_L] = MC2 if livery == 1 else MC1
        img[y][WAGON_R] = MC2 if livery == 1 else MC1
        if livery == 1:
            img[y][4] = img[y][23] = LEGEND["y"]
        else:
            img[y][4] = img[y][23] = MC1
        hline(img, 12, 15, y, MC2)
    if vent:
        for y in (2, 5):
            for x in (7, 8, 19, 20):
                img[y][x] = BG
    return img


def wagon(livery, part):
    base = rail(0)
    if part == "body_a":
        return over(base, roof(livery))
    if part == "body_b":
        return over(base, roof(livery, vent=True))
    if part == "end_bottom":                  # end nearest the player: bottom of the tile
        over(base, roof(livery, 6))
        hline(base, WAGON_L, WAGON_R, 6, MC2 if livery == 1 else MC1)
        return base
    if part == "end_top":
        return _end_top(livery)
    if part == "coupler":
        for y in range(8):
            hline(base, 13, 14, y, MC2)
        hline(base, 11, 16, 0, MC1)
        hline(base, 11, 16, 7, MC1)
        return base
    raise ValueError(part)


def _end_top(livery):
    base = rail(0)
    hline(base, WAGON_L, WAGON_R, 1, MC2 if livery == 1 else MC1)
    over(base, roof(livery, 6), 0, 2)
    return base


def loco(livery, part):
    base = rail(0)
    body = MC1 if livery == 1 else MC2
    if part in ("body", "pantograph"):
        over(base, roof(livery))
        if part == "pantograph":
            p = art(["          ",
                     "    ll    ",
                     "   l  l   ",
                     "  l    l  ",
                     "  l    l  ",
                     "   l  l   ",
                     "    ll    ",
                     "          "])
            over(base, p, 9, 0)
            hline(base, 12, 15, 3, MC1)
        return base
    if part == "nose":                       # cab front, facing the player
        for y in range(0, 7):
            hline(base, WAGON_L, WAGON_R, y, body)
        hline(base, 4, 23, 2, MC2 if livery == 1 else BG)     # windscreen frame
        hline(base, 5, 22, 3, BG)                             # windscreen
        hline(base, 5, 22, 4, BG)
        hline(base, 4, 23, 5, LEGEND["y"])
        hline(base, 4, 23, 6, LEGEND["y"])                    # warning yellow
        base[5][2] = base[5][3] = base[6][2] = base[6][3] = LEGEND["r"]   # lamps (edge columns)
        base[5][24] = base[5][25] = base[6][24] = base[6][25] = LEGEND["r"]
        return base
    if part == "nose_top":                   # rear cab, far end
        for y in range(1, 8):
            hline(base, WAGON_L, WAGON_R, y, body)
        hline(base, 4, 23, 1, LEGEND["y"])
        base[1][2] = base[1][3] = base[1][24] = base[1][25] = LEGEND["r"]
        hline(base, 5, 22, 3, BG)
        hline(base, 4, 23, 4, MC2 if livery == 1 else BG)
        return base
    raise ValueError(part)


def stop(part):
    base = rail(0)
    if part == 0:                            # the beam
        for y in (2, 3, 4, 5):
            for x in range(1, 27):
                c = LEGEND["r"] if x < 4 or x > 23 else (LEGEND["y"] if (x // 4) % 2 else MC1)
                base[y][x] = c
        hline(base, 1, 26, 6, MC2)
        return base
    for y in range(0, 8):                    # buffers and the rails' end
        for x in (5, 6, 21, 22):
            base[y][x] = MC2 if y < 5 else BG
    hline(base, 3, 24, 0, MC2)
    for y in range(5, 8):
        hline(base, 3, 24, y, BG)
    return base


def signal(part):
    base = rail(1)
    if part == 0:                            # head: lit red lamp over a dark one
        over(base, art(["lll ", "lrl ", "lrl ", "lll ", "l.l ", "l.l ", "lll ", " m  "]), 0, 0)
        return base
    vline(base, 1, 0, 7, MC2)                # post, with its foot
    hline(base, 0, 2, 6, MC2)
    return base


def ramp(up, i):
    """Ramps onto a roof: row 0 lowest .. row 2 highest; the grip lines get
    closer at the bottom, which reads as a slope. Down ramps are the same rows
    in the other order, so they cost no characters."""
    if not up:
        return ramp(True, 2 - i)
    base = rail(0)
    step = (2, 3, 4)[i]
    for y in range(8):
        hline(base, WAGON_L + 1, WAGON_R - 1, y, MC2 if y % step == 0 else MC1)
        base[y][WAGON_L] = base[y][WAGON_R] = MC2
    return base


def track_sheet():
    frames = [("rail_a", rail(0)), ("rail_b", rail(1)), ("stop_0", stop(0)), ("stop_1", stop(1)),
              ("signal_0", signal(0)), ("signal_1", signal(1))]
    for t in A.TRAIN_TYPES:
        for part in ("end_bottom", "body_a", "body_b", "end_top", "coupler"):
            frames.append((f"wagon{t}_{part}", wagon(t, part)))
    for t in A.TRAIN_TYPES:
        for part in ("nose", "body", "pantograph", "nose_top"):
            frames.append((f"loco{t}_{part}", loco(t, part)))
    frames += [(f"ramp_up_{i}", ramp(True, i)) for i in range(3)]
    frames += [(f"ramp_down_{i}", ramp(False, i)) for i in range(3)]
    return frames


def coins_sheet():
    frames = []
    rail_mid = [row[12:16] for row in rail(0)]
    roof_mid = [row[12:16] for row in roof(1)]
    for coin, bg in (("coin_rail", rail_mid), ("coin_roof", roof_mid)):
        for p, shape in enumerate(coin_shapes()):
            frames.append((f"{coin}_{p}", over(copy(bg), shape)))
    return frames


# --- sides: composed from a small library of characters ---------------------
# Left side: 9 columns, column 8 touches the tracks. Right side: 10 columns,
# column 0 touches the tracks. Fills are symmetric so both sides share them;
# only the few characters with a direction come in _L / _R pairs.
SIDE_CHARS = {
    "ASPH": ["...."] * 8,
    "DASH": ["....", ".ll.", ".ll.", ".ll.", ".ll.", ".ll.", ".ll.", "...."],
    "KERB_L": ["..lm"] * 8,
    "KERB_R": ["ml.."] * 8,
    "PAVE": ["mmmm"] * 7 + ["...."],
    "FENCE_L": ["gll."] + ["gl.."] * 3 + ["gll."] + ["gl.."] * 3,
    "FENCE_R": [".llg"] + ["..lg"] * 3 + [".llg"] + ["..lg"] * 3,
    "ZEBRA": ["ll.."] * 8,
    "KIOSK_TL": ["mmmm", "mggg", "mgll", "mgll", "mggg", "mggg", "mggg", "mggg"],
    "KIOSK_TR": ["mmmm", "gggm", "llgm", "llgm", "gggm", "gggm", "gggm", "gggm"],
    "KIOSK_BL": ["mlll", "mlll", "mlmm", "mlmm", "mlll", "mlll", "mmmm", "...."],
    "KIOSK_BR": ["lllm", "lllm", "mmlm", "mmlm", "lllm", "lllm", "mmmm", "...."],
    "CAR_TL": ["....", ".lll", ".lmm", ".lmm", ".lll", ".lll", ".lll", ".lll"],
    "CAR_TR": ["....", "lll.", "mml.", "mml.", "lll.", "lll.", "lll.", "lll."],
    "CAR_BL": [".lll", ".lll", ".lmm", ".lll", ".lll", ".lll", "....", "...."],
    "CAR_BR": ["lll.", "lll.", "mml.", "lll.", "lll.", "lll.", "....", "...."],
    "G1": ["gggg", "gmgg", "gggg", "gggg", "ggg.", "gggg", "gggg", "gggg"],
    "G2": ["gggg", "gggg", "g.gg", "gggg", "gggg", "gggg", "ggmg", "gggg"],
    "FEDGE_L": ["gg..", "ggm.", "gg..", "gg..", "gg..", "gg..", "ggm.", "gg.."],
    "FEDGE_R": ["..gg", ".mgg", "..gg", "..gg", "..gg", "..gg", ".mgg", "..gg"],
    "PATH": ["gmmg", "gmmg", "mmgg", "mmgg", "gmmg", "gmmg", "ggmm", "ggmm"],
    "FENCEW": ["mmmg", "gmgg", "gmgg", "gmgg", "mmmg", "gmgg", "gmgg", "gmgg"],
    "BUSH": ["....", ".gg.", "gmgg", "ggmg", "gggg", ".gg.", "....", "gggg"],
    "PLAT_EDGE_L": ["mll."] * 8,
    "PLAT_EDGE_R": [".llm"] * 8,
    "RAMP": ["mmmm", "m.mm", "mmmm", "mm.m", "mmmm", "m.mm", "mmmm", "mm.m"],
    "BENCH_L": ["mmmm", "mlll", "mlll", "mmmm", "ml..", "ml..", "mmmm", "...."],
    "BENCH_R": ["mmmm", "lllm", "lllm", "mmmm", "..lm", "..lm", "mmmm", "...."],
    "ROOF": ["llll", "llll", "mmmm", "llll", "llll", "llll", "mmmm", "llll"],
    "SIGN_L": ["llll", "gggg", "glgl", "glgl", "gllg", "gggg", "llll", "llll"],
    "SIGN_M": ["llll", "gggg", "lglg", "lglg", "lllg", "gggg", "llll", "llll"],
    "SIGN_R": ["llll", "gggg", "glgg", "llgg", "glgg", "gggg", "llll", "llll"],
}
TREE = [                                     # 4 columns x 3 rows over grass
    "     ......     ",
    "   ..llllll..   ",
    "  .llggglggll.  ",
    " .lgglggggglgg. ",
    " .lggggglgggg.g.",
    ".lgglgggggglgg..",
    ".lggggg.ggggg.g.",
    ".lgg.ggggg.gg.g.",
    ".gggggg.gggg.g..",
    ".lg.gggggg.gg.g.",
    ".gggg.ggg.g.g.g.",
    ".gg.ggg.gg.g.g..",
    ".g.ggg.g.g.g.g..",
    " .gg.g.g.g.g.g. ",
    " ..g.g.g.g.g... ",
    "  ..g.g.......  ",
    "   ..........   ",
    "     ..mm..     ",
    "      .mm.      ",
    "      .mm.      ",
    "       ..       ",
    "                ",
    "                ",
    "                ",
]
for _row in range(3):                        # row 0 = bottom
    for _col in range(4):
        SIDE_CHARS[f"TREE_{_row}{_col}"] = [
            "".join("g" if ch == " " else ch for ch in line[_col * 4:_col * 4 + 4])
            for line in TREE[(2 - _row) * 8:(3 - _row) * 8]]

_G = ["G1", "G2"] * 5
_ROAD_L = ["ASPH", "ASPH", "ASPH", "ASPH", "ASPH", "KERB_L", "PAVE", "PAVE", "FENCE_L"]
SIDE_L = {
    "road_a": ["ASPH", "ASPH", "DASH", "ASPH", "ASPH", "KERB_L", "PAVE", "PAVE", "FENCE_L"],
    "road_b": _ROAD_L,
    "road_cross_0": ["ZEBRA"] * 5 + ["KERB_L", "PAVE", "PAVE", "FENCE_L"],
    "road_cross_1": ["ZEBRA"] * 5 + ["KERB_L", "PAVE", "PAVE", "FENCE_L"],
    "kiosk_0": _ROAD_L[:6] + ["KIOSK_BL", "KIOSK_BR", "FENCE_L"],
    "kiosk_1": _ROAD_L[:6] + ["KIOSK_TL", "KIOSK_TR", "FENCE_L"],
    "car_0": ["ASPH", "ASPH", "CAR_BL", "CAR_BR"] + _ROAD_L[4:],
    "car_1": ["ASPH", "ASPH", "CAR_TL", "CAR_TR"] + _ROAD_L[4:],
    "ground_a": _G[:8] + ["FEDGE_L"],
    "ground_b": _G[1:9] + ["FEDGE_L"],
    "path": ["G1", "G2", "PATH", "G2", "G1", "G2", "G1", "G2", "FEDGE_L"],
    "fence": _G[:7] + ["FENCEW", "FEDGE_L"],
    "tree_0": ["G1", "TREE_00", "TREE_01", "TREE_02", "TREE_03", "G1", "G2", "G1", "FEDGE_L"],
    "tree_1": ["G2", "TREE_10", "TREE_11", "TREE_12", "TREE_13", "G2", "G1", "G2", "FEDGE_L"],
    "tree_2": ["G1", "TREE_20", "TREE_21", "TREE_22", "TREE_23", "G1", "G2", "G1", "FEDGE_L"],
    "bush": _G[:5] + ["BUSH"] + _G[6:8] + ["FEDGE_L"],
    "trans_uf_0": _G[:5] + ["KERB_L", "PAVE", "PAVE", "FENCE_L"],
    "trans_uf_1": _G[1:8] + ["G2", "FENCE_L"],
    "trans_fu_0": _G[:8] + ["FENCE_L"],
    "trans_fu_1": _G[1:6] + ["KERB_L", "PAVE", "PAVE", "FENCE_L"],
    "plat_end": ["ASPH", "ASPH", "ASPH", "KERB_L", "RAMP", "RAMP", "RAMP", "RAMP", "PLAT_EDGE_L"],
    "plat_plain": ["ASPH", "ASPH", "ASPH", "KERB_L", "PAVE", "PAVE", "PAVE", "PAVE", "PLAT_EDGE_L"],
    "plat_bench": ["ASPH", "ASPH", "ASPH", "KERB_L", "PAVE", "BENCH_L", "BENCH_R", "PAVE", "PLAT_EDGE_L"],
    "plat_roof": ["ASPH", "ASPH", "ASPH", "KERB_L", "ROOF", "ROOF", "ROOF", "ROOF", "PLAT_EDGE_L"],
    "plat_sign": ["ASPH", "ASPH", "ASPH", "KERB_L", "ROOF", "SIGN_L", "SIGN_M", "SIGN_R", "PLAT_EDGE_L"],
}


def _right(cols):
    """Left composition -> right: reversed, directed characters swapped, and
    the outer column repeated (the right side is one column wider)."""
    swap = {"KERB_L": "KERB_R", "FENCE_L": "FENCE_R", "FEDGE_L": "FEDGE_R", "PLAT_EDGE_L": "PLAT_EDGE_R"}
    out = [swap.get(c, c) for c in cols[::-1]]
    objects = ("TREE_", "KIOSK_", "CAR_", "BENCH_", "SIGN_")   # multi-character: keep their order
    i = 0
    while i < len(out):
        pre = next((o for o in objects if out[i].startswith(o)), None)
        j = i
        while pre and j < len(out) and out[j].startswith(pre):
            j += 1
        if j > i + 1:
            out[i:j] = out[i:j][::-1]
        i = max(j, i + 1)
    extra = {"G1": "G2", "G2": "G1"}.get(out[-1], out[-1])
    return out + [extra if not extra.startswith(objects) else "G1"]


SIDE_R = {k: _right(v) for k, v in SIDE_L.items()}
SIDE_R["road_a"] = ["FENCE_R", "PAVE", "PAVE", "KERB_R", "ASPH", "ASPH", "DASH", "ASPH", "ASPH", "ASPH"]


def compose(cols):
    rows = [[] for _ in range(8)]
    for name in cols:
        for y, line in enumerate(SIDE_CHARS[name]):
            rows[y] += [LEGEND[ch] for ch in line]
    return rows


def side_left(kind):
    return compose(SIDE_L[kind])


def side_right(kind):
    return compose(SIDE_R[kind])


# --- bridges (160 px = 40 columns) ------------------------------------------
def bridge(name):
    """Rows bottom to top. Railings and parapets MC1/MC2, decks MC2: the
    same colours in every column, and the deck (%10) hides the runner."""
    img = blank(160, 8)
    kind, i = name.rsplit("_", 1)
    if i == "shadow":                        # the beam on its piers, shade on the track
        for y in range(8):
            hline(img, 0, 159, y, BG)
        hline(img, 0, 159, 0, MC2)
        hline(img, 0, 159, 1, MC2)
        for x in range(0, 160, 40):
            for y in range(2, 8):
                hline(img, x + 34, x + 37, y, MC2)
        return img
    i = int(i)
    if kind == "footbridge":
        if i in (0, 2):                      # railings
            for y in range(8):
                hline(img, 0, 159, y, MC2)
            hline(img, 0, 159, 3 if i == 0 else 4, MC1)
            for x in range(0, 160, 6):
                vline(img, x, 0, 7, MC1)
        else:                                # deck
            for y in range(8):
                hline(img, 0, 159, y, MC2)
            for x in range(2, 160, 8):
                img[2][x] = BG
                img[6][min(159, x + 3)] = BG
        return img
    if i in (0, 5):                          # parapets
        for y in range(8):
            hline(img, 0, 159, y, MC1)
        hline(img, 0, 159, 2 if i == 0 else 5, MC2)
        hline(img, 0, 159, 7 if i == 0 else 0, MC2)
        return img
    for y in range(8):                       # road deck, two lanes each way
        hline(img, 0, 159, y, MC2)
    if i in (1, 4):                          # kerb lines
        hline(img, 0, 159, 7 if i == 1 else 0, BG)
    if i == 2:
        for x in range(0, 160, 12):
            hline(img, x, x + 5, 7, MC1)
    if i == 3:
        hline(img, 0, 159, 0, MC1)           # the middle line
    return img


# --- font (3x7 glyphs, white ink, column 3 and row 7 empty) -----------------
FONT = {
    "space": ["...", "...", "...", "...", "...", "...", "..."],
    "a": [".#.", "#.#", "#.#", "###", "#.#", "#.#", "#.#"], "b": ["##.", "#.#", "#.#", "##.", "#.#", "#.#", "##."],
    "c": [".##", "#..", "#..", "#..", "#..", "#..", ".##"], "d": ["##.", "#.#", "#.#", "#.#", "#.#", "#.#", "##."],
    "e": ["###", "#..", "#..", "##.", "#..", "#..", "###"], "f": ["###", "#..", "#..", "##.", "#..", "#..", "#.."],
    "g": [".##", "#..", "#..", "#.#", "#.#", "#.#", ".##"], "h": ["#.#", "#.#", "#.#", "###", "#.#", "#.#", "#.#"],
    "i": ["###", ".#.", ".#.", ".#.", ".#.", ".#.", "###"], "j": ["..#", "..#", "..#", "..#", "..#", "#.#", ".#."],
    "k": ["#.#", "#.#", "##.", "#..", "##.", "#.#", "#.#"], "l": ["#..", "#..", "#..", "#..", "#..", "#..", "###"],
    "m": ["#.#", "###", "###", "#.#", "#.#", "#.#", "#.#"], "n": ["##.", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#"],
    "o": [".#.", "#.#", "#.#", "#.#", "#.#", "#.#", ".#."], "p": ["##.", "#.#", "#.#", "##.", "#..", "#..", "#.."],
    "q": [".#.", "#.#", "#.#", "#.#", "#.#", "##.", ".##"], "r": ["##.", "#.#", "#.#", "##.", "#.#", "#.#", "#.#"],
    "s": [".##", "#..", "#..", ".#.", "..#", "..#", "##."], "t": ["###", ".#.", ".#.", ".#.", ".#.", ".#.", ".#."],
    "u": ["#.#", "#.#", "#.#", "#.#", "#.#", "#.#", "###"], "v": ["#.#", "#.#", "#.#", "#.#", "#.#", ".#.", ".#."],
    "w": ["#.#", "#.#", "#.#", "#.#", "###", "###", "#.#"], "x": ["#.#", "#.#", ".#.", ".#.", ".#.", "#.#", "#.#"],
    "y": ["#.#", "#.#", "#.#", ".#.", ".#.", ".#.", ".#."], "z": ["###", "..#", "..#", ".#.", "#..", "#..", "###"],
    "n0": ["###", "#.#", "#.#", "#.#", "#.#", "#.#", "###"], "n1": [".#.", "##.", ".#.", ".#.", ".#.", ".#.", "###"],
    "n2": ["##.", "..#", "..#", ".#.", "#..", "#..", "###"], "n3": ["##.", "..#", "..#", ".#.", "..#", "..#", "##."],
    "n4": ["#.#", "#.#", "#.#", "###", "..#", "..#", "..#"], "n5": ["###", "#..", "#..", "##.", "..#", "..#", "##."],
    "n6": [".##", "#..", "#..", "##.", "#.#", "#.#", ".#."], "n7": ["###", "..#", "..#", ".#.", ".#.", ".#.", ".#."],
    "n8": [".#.", "#.#", "#.#", ".#.", "#.#", "#.#", ".#."], "n9": [".#.", "#.#", "#.#", ".##", "..#", "..#", "##."],
    "gamma": ["###", "#..", "#..", "#..", "#..", "#..", "#.."], "delta": [".#.", ".#.", "#.#", "#.#", "#.#", "#.#", "###"],
    "theta": [".#.", "#.#", "#.#", "###", "#.#", "#.#", ".#."], "lambda": [".#.", ".#.", "#.#", "#.#", "#.#", "#.#", "#.#"],
    "xi": ["###", "...", "...", "###", "...", "...", "###"], "pi": ["###", "#.#", "#.#", "#.#", "#.#", "#.#", "#.#"],
    "sigma": ["###", "#..", ".#.", "..#", ".#.", "#..", "###"], "phi": [".#.", "###", "#.#", "#.#", "#.#", "###", ".#."],
    "psi": ["#.#", "#.#", "#.#", "###", ".#.", ".#.", ".#."], "omega": [".#.", "#.#", "#.#", "#.#", "#.#", ".#.", "#.#"],
    "dot": ["...", "...", "...", "...", "...", ".#.", "#.."], "colon": ["...", ".#.", "...", "...", "...", ".#.", "..."],
    "minus": ["...", "...", "...", "###", "...", "...", "..."], "excl": [".#.", ".#.", ".#.", ".#.", ".#.", "...", ".#."],
    "quest": ["##.", "..#", "..#", ".#.", ".#.", "...", ".#."], "slash": ["..#", "..#", ".#.", ".#.", ".#.", "#..", "#.."],
    "left": ["...", "..#", ".##", "###", ".##", "..#", "..."], "right": ["...", "#..", "##.", "###", "##.", "#..", "..."],
    "up": [".#.", "###", "###", ".#.", ".#.", ".#.", "..."], "down": ["...", ".#.", ".#.", ".#.", "###", "###", ".#."],
}


def glyph(name):
    rows = [[LEGEND["w"] if ch == "#" else BG for ch in line] + [BG] for line in FONT[name]]
    return rows + [[BG] * 4]


# --- adapted from the CPC sheets ---------------------------------------------
def cpc_frames(sheet):
    """-> {frame: rows of RGB (None = transparent)}"""
    from PIL import Image
    im = Image.open(os.path.join(CPC_PNG, sheet + ".png")).convert("RGBA")
    with open(os.path.join(CPC_PNG, sheet + ".json")) as f:
        meta = json.load(f)
    out = {}
    for fr in meta["frames"]:
        r = fr["frame"]
        out[fr["filename"]] = [[(None if im.getpixel((r["x"] + x, r["y"] + y))[3] < 128 else im.getpixel((r["x"] + x, r["y"] + y))[:3])
                                for x in range(r["w"])] for y in range(r["h"])]
    return out


def dist(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b))


def fit_cells(px, bg_rgb, fixed):
    """Maps an RGB image onto multicolor cells: each 4x8 cell gets BG/MC1/MC2
    (fixed) plus its own best colour (0-7)."""
    h, w = len(px), len(px[0])
    out = blank(w, h)
    for cx in range(0, w, 4):
        cell = [px[y][x] for y in range(h) for x in range(cx, cx + 4) if px[y][x] is not None]
        votes = {}
        for p in cell:
            c = nearest(p)
            if c < 8 and c not in fixed and dist(p, bg_rgb) > 900:
                votes[c] = votes.get(c, 0) + 1
        own = max(votes, key=votes.get) if votes else None
        choices = list(fixed) + ([own] if own is not None else [])
        for y in range(h):
            for x in range(cx, cx + 4):
                p = px[y][x]
                out[y][x] = fixed[0] if p is None or dist(p, bg_rgb) < 900 else min(choices, key=lambda c: dist(RGB[c], p))
    return out


def hud_sheet():
    cpc = {k: [row[:8] for row in v[:8]] for k, v in cpc_frames("hud").items()}   # icons: 8x8 top left
    panel = (0, 0, 0x80)                     # CPC HUD panel blue
    hud_bg = A.HUD_BG
    frames = []
    fixed = (hud_bg, MC1, MC2)
    for p in A.POWERUPS:
        on = cpc[f"ic_{p}"]
        frames.append((f"ic_{p}", fit_cells(on, panel, fixed)))
    frames.append(("ic_coin", fit_cells(cpc["ic_coin"], panel, fixed)))
    frames.append(("ic_life", fit_cells(cpc["ic_life"], panel, fixed)))
    for i in range(5):                       # timer bar: i pixels lit
        img = blank(4, 8, hud_bg)
        for y in range(2, 6):
            for x in range(4):
                img[y][x] = LEGEND["y"] if x < i else MC2
        frames.append((f"bar{i}", img))
    route = {
        "route_line": ["....", "....", "....", "llll", "llll", "....", "....", "...."],
        "route_station": ["....", ".ww.", ".ww.", "wwww", "wwww", ".ww.", ".ww.", "...."],
        "route_here": [".rr.", "rrrr", "rrrr", "rrrr", "rrrr", "rrrr", ".rr.", "...."],
        "route_start": ["....", "w...", "w...", "wlll", "wlll", "w...", "w...", "...."],
        "route_end": ["....", "...w", "...w", "lllw", "lllw", "...w", "...w", "...."],
    }
    for name in A.HUD_ROUTE:
        frames.append((name, [[hud_bg if ch == "." else LEGEND[ch] for ch in line] for line in route[name]]))
    return frames


def sprite_from_cpc(px, mc_map):
    """CPC frame (RGB, None transparent) -> (12x21 multicolor body, 24x21 hires
    outline): black goes to the outline, the rest to the nearest of mc_map.
    The content is centred and bottom aligned; outline pixels left or right of
    the 12 columns are pulled in to the outer hires pixel of the edge column."""
    h, w = len(px), len(px[0])
    pts = [(x, y) for y in range(h) for x in range(w) if px[y][x] is not None]
    bx0, bx1 = min(x for x, _ in pts), max(x for x, _ in pts)
    by1 = max(y for _, y in pts)
    x0 = (bx0 + bx1 + 1) // 2 - 6
    body = blank(12, 21, TRANSPARENT)
    outline = blank(24, 21, TRANSPARENT)
    black = colour("black")
    for sx, sy in pts:
        y = 20 - (by1 - sy)
        if y < 0:
            continue
        x = sx - x0
        p = px[sy][sx]
        if sum(p) < 90:
            if x < 0:
                outline[y][0] = black
            elif x > 11:
                outline[y][23] = black
            else:
                outline[y][2 * x] = outline[y][2 * x + 1] = black
        elif 0 <= x < 12:
            body[y][x] = min(mc_map, key=lambda c: dist(RGB[c], p))
    return body, outline


# runner, seen from behind: r shirt (own colour), b jeans (MC0), s skin (MC1);
# h hair and k shoes are black and go to the hires outline sprite only
RUNNER_ART = {
    "run0": [
        "............", "....hhhh....", "...hhhhhh...", "...hhhhhh...", "...shhhhs...", "....ssss....",
        "..rrrrrrrr..", ".rrrrrrrrrr.", ".rrrrrrrrrr.", ".srrrrrrrrr.", ".s.rrrrrr.r.", "...rrrrrr.s.",
        "...bbbbbb...", "...bbbbbb...", "...bbb.bbb..", "...bb...bb..", "...bb...bb..", "...bb...kk..",
        "...bb.......", "...bb.......", "...kk.......",
    ],
    "run1": [
        "............", "....hhhh....", "...hhhhhh...", "...hhhhhh...", "...shhhhs...", "....ssss....",
        "..rrrrrrrr..", ".rrrrrrrrrr.", ".rrrrrrrrrr.", ".rrrrrrrrrr.", ".srrrrrrrrs.", ".srrrrrrrrs.",
        "...bbbbbb...", "...bbbbbb...", "...bb..bb...", "...bb..bb...", "...bb..bb...", "...bb..bb...",
        "...bb..bb...", "...kk..kk...", "............",
    ],
}
RUNNER_ART["run2"] = [row[::-1] for row in RUNNER_ART["run0"]]
RUNNER_ART["run3"] = RUNNER_ART["run1"]


def runner_frame(rows):
    """-> (12x21 multicolor body, 24x21 hires outline: black hair, shoes and a
    one-pixel rim around the body)."""
    m = {"r": colour("red"), "b": A.SPRITE_MC0, "s": A.SPRITE_MC1}
    body = [[m.get(ch, TRANSPARENT) for ch in row] for row in rows]
    solid = [[ch != "." for ch in row for _ in (0, 1)] for row in rows]       # hires mask
    black = colour("black")
    outline = blank(24, 21, TRANSPARENT)
    for y in range(21):
        for x in range(24):
            ch = rows[y][x // 2]
            if ch in "hk":
                outline[y][x] = black
            elif not solid[y][x] and any(0 <= y + dy < 21 and 0 <= x + dx < 24 and solid[y + dy][x + dx]
                                         for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                outline[y][x] = black
    return body, outline


def runner_sheets():
    frames = [(name, runner_frame(RUNNER_ART[name])) for name in A.RUNNER_FRAMES]
    return [(n, b) for n, (b, _) in frames], [(n, o) for n, (_, o) in frames]


def powerup_sheet():
    cpc = cpc_frames("items")
    out = []
    for p in A.POWERUPS:
        px = cpc[f"pu_{p}"]
        votes = {}
        for row in px:
            for q in row:
                if q is not None and sum(q) > 90:
                    c = nearest(q)
                    if c not in (A.SPRITE_MC0, A.SPRITE_MC1):
                        votes[c] = votes.get(c, 0) + 1
        own = max(votes, key=votes.get) if votes else colour("white")
        b, _ = sprite_from_cpc(px, (own, A.SPRITE_MC0, A.SPRITE_MC1))
        out.append((p, b))
    return out


def shadow_sheet():
    img = blank(24, 21, TRANSPARENT)
    for y, (x0, x1) in enumerate([(7, 16), (5, 18), (4, 19), (5, 18), (7, 16)]):
        hline(img, x0, x1, 16 + y, colour("black"))
    return [("shadow", img)]


SHEET_MAKERS = {
    "track": track_sheet,
    "coins": coins_sheet,
    "side_l": lambda: [(k, side_left(k)) for k in A.SIDE_KINDS],
    "side_r": lambda: [(k, side_right(k)) for k in A.SIDE_KINDS],
    "bridges": lambda: [(n, bridge(n)) for n in A.BRIDGE_ROWS],
    "font": lambda: [(n, glyph(n)) for n, _ in A.FONT_GLYPHS],
    "hud": hud_sheet,
    "runner": lambda: runner_sheets()[0],
    "runner_outline": lambda: runner_sheets()[1],
    "powerups": powerup_sheet,
    "shadow": shadow_sheet,
}


def main(names):
    for name in names or SHEET_MAKERS:
        write_sheet(name, SHEET_MAKERS[name]())
        print("gfx/png/" + name + ".png")


if __name__ == "__main__":
    main(sys.argv[1:])
