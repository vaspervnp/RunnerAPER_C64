"""Graphics manifest: screen colours, column layout, sheets and how they convert.

Sheets are gfx/png/<sheet>.png + .json (frames left to right), drawn in C64
colours. In character sheets one pixel = one multicolor pixel (4 per
character, shown 2:1). Sprite sheets: multicolor 12x21 or hires 24x21.

Every character pixel is one of four sources (the 2-bit value):
  %00 BG ($d021)  %01 MC1 ($d022)  %10 MC2 ($d023)  %11 the cell's colour RAM
The colour RAM of the playfield never changes (it does not scroll), so each
screen column has one fixed %11 colour: COLUMN_COLOURS. HUD cells (rows
21-23) each have their own.
"""

from c64palette import colour

# --- screen colours (MC2 is the open choice: "brown" or "grey") -------------
PALETTES = {
    "brown": dict(bg="dark_grey", mc1="light_grey", mc2="brown"),
    "grey": dict(bg="dark_grey", mc1="light_grey", mc2="grey"),
}
PALETTE = "grey"


def screen_colours(palette=None):
    p = PALETTES[palette or PALETTE]
    return colour(p["bg"]), colour(p["mc1"]), colour(p["mc2"])


# The HUD has its own background: the split IRQ sets $d021 with the HUD's
# first line and the top IRQ puts it back.
HUD_BG = colour("blue")


def sheet_colours(sheet, palette=None):
    bg, mc1, mc2 = screen_colours(palette)
    return (HUD_BG, mc1, mc2) if sheet == "hud" else (bg, mc1, mc2)


# --- columns ------------------------------------------------------------------
LEFT_COLS, TRACK_COLS, RIGHT_COLS = 9, 7, 10
TRACK_X = [LEFT_COLS + i * TRACK_COLS for i in range(3)]      # 9, 16, 23
RIGHT_X = LEFT_COLS + 3 * TRACK_COLS                           # 30

SIDE = colour("green")
TRACK_EDGE = colour("red")          # signal heads, the ends of the stop beam
TRACK_MID = colour("yellow")        # coins, loco fronts, wagon stripes
TRACK_COLOURS = [TRACK_EDGE] + [TRACK_MID] * 5 + [TRACK_EDGE]
COLUMN_COLOURS = [SIDE] * LEFT_COLS + TRACK_COLOURS * 3 + [SIDE] * RIGHT_COLS
assert len(COLUMN_COLOURS) == 40
COIN_COL = 3                        # coins sit in the middle column of a track

# --- character sheets -------------------------------------------------------
TRAIN_TYPES = (1, 2)                # two liveries, told apart by pattern
TRACK_TILES = (
    ["rail_a", "rail_b", "stop_0", "stop_1", "signal_0", "signal_1"]
    + [f"wagon{t}_{part}" for t in TRAIN_TYPES
       for part in ("end_bottom", "body_a", "body_b", "end_top", "coupler")]
    + [f"loco{t}_{part}" for t in TRAIN_TYPES for part in ("nose", "body", "pantograph", "nose_top")]
    + [f"ramp_up_{i}" for i in range(3)]
    + [f"ramp_down_{i}" for i in range(3)]
)
# animated coin characters: tile + its 4 shine phases (the charset bytes of
# the character are rewritten, so every coin on screen turns at once)
COINS = ["coin_rail", "coin_roof"]
COIN_PHASES = 4

SIDE_KINDS = ["road_a", "road_b", "road_cross_0", "road_cross_1", "kiosk_0", "kiosk_1",
              "car_0", "car_1", "ground_a", "ground_b", "path", "fence", "tree_0", "tree_1", "tree_2",
              "bush", "trans_uf_0", "trans_uf_1", "trans_fu_0", "trans_fu_1",
              "plat_end", "plat_plain", "plat_bench", "plat_roof", "plat_sign"]
# bottom to top, as many rows as on the CPC (the generator's timing depends on it)
FOOTBRIDGE_ROWS = ["footbridge_shadow"] + [f"footbridge_{i}" for i in range(3)]
ROADBRIDGE_ROWS = ["roadbridge_shadow"] + [f"roadbridge_{i}" for i in range(6)]
BRIDGE_ROWS = FOOTBRIDGE_ROWS + ROADBRIDGE_ROWS

# font: frame name, characters it draws (Greek capitals that look like Latin share)
FONT_GLYPHS = (
    [("space", " ")]
    + [(c.lower(), c + {"A": "Α", "B": "Β", "E": "Ε", "Z": "Ζ", "H": "Η", "I": "Ι", "K": "Κ", "M": "Μ",
                        "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "Y": "Υ", "X": "Χ"}.get(c, ""))
       for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    + [(f"n{d}", str(d)) for d in range(10)]
    + [("gamma", "Γ"), ("delta", "Δ"), ("theta", "Θ"), ("lambda", "Λ"), ("xi", "Ξ"), ("pi", "Π"),
       ("sigma", "Σ"), ("phi", "Φ"), ("psi", "Ψ"), ("omega", "Ω")]
    + [("dot", ".,"), ("colon", ":"), ("minus", "-"), ("excl", "!"), ("quest", "?;"), ("slash", "/"),
       ("left", "←"), ("right", "→"), ("up", "↑"), ("down", "↓")]
)

POWERUPS = ["magnet", "turbo", "slow", "spring", "helmet", "ticket"]
# a power-up that is off: the same characters with colour RAM 0 (black)
HUD_ICONS = [f"ic_{p}" for p in POWERUPS] + ["ic_coin", "ic_life"]
HUD_BARS = [f"bar{i}" for i in range(5)]                 # 0-4 pixels lit
HUD_ROUTE = ["route_line", "route_station", "route_here", "route_start", "route_end"]


def _cols(n, c):
    return [c] * n


# sheet -> dict(frames=[(name, w, h)], cols=fn(frame) -> per char column colour or None (free))
CHAR_SHEETS = {
    "font": dict(frames=[(n, 4, 8) for n, _ in FONT_GLYPHS], cols=lambda f: [None], fixed=True),
    "track": dict(frames=[(n, 28, 8) for n in TRACK_TILES], cols=lambda f: TRACK_COLOURS),
    "coins": dict(frames=[(f"{c}_{p}", 4, 8) for c in COINS for p in range(COIN_PHASES)],
                  cols=lambda f: [TRACK_MID]),
    "side_l": dict(frames=[(n, 36, 8) for n in SIDE_KINDS], cols=lambda f: _cols(LEFT_COLS, SIDE)),
    "side_r": dict(frames=[(n, 40, 8) for n in SIDE_KINDS], cols=lambda f: _cols(RIGHT_COLS, SIDE)),
    "bridges": dict(frames=[(n, 160, 8) for n in BRIDGE_ROWS], cols=lambda f: COLUMN_COLOURS),
    "hud": dict(frames=[(n, 8, 8) for n in HUD_ICONS] + [(n, 4, 8) for n in HUD_BARS + HUD_ROUTE],
                cols=lambda f: [None] * (f[1] // 4)),
}
CHAR_ORDER = ["font", "coins", "track", "side_l", "side_r", "bridges", "hud"]

# --- sprites ----------------------------------------------------------------
# shared sprite colours ($d025/$d026); each sprite adds its own ($d027+n)
SPRITE_MC0 = colour("blue")
SPRITE_MC1 = colour("light_red")
# the runner in 5 sizes (z 0..4, as the CPC's s1..s5): s1 on the ground, s3 on a
# roof, s2..s5 in the air
RUNNER_FRAMES = ([f"s1_{f}" for f in ("run0", "run1", "run2", "run3", "lean_l", "lean_r", "crash0", "crash1")]
                 + ["s2_jump_up", "s2_jump_down"]
                 + [f"s3_{f}" for f in ("run0", "run1", "run2", "run3", "lean_l", "lean_r",
                                         "jump_up", "jump_down", "crash0", "crash1")]
                 + ["s4_jump_up", "s4_jump_down", "s5_jump"])
SHADOWS = ["sh_ground", "sh_roof"]
SPRITE_SHEETS = {
    # multicolor body (sprite 0) + hires outline (sprite 1) per frame
    "runner": dict(frames=RUNNER_FRAMES, mc=True),
    "runner_outline": dict(frames=RUNNER_FRAMES, mc=False),
    "powerups": dict(frames=POWERUPS, mc=True),
    "shadow": dict(frames=SHADOWS, mc=False),
}

# the empty sprite block after the converted ones: a runner under a bridge
# deck is cut by pointing its sprites here for those lines (src/player.asm)
