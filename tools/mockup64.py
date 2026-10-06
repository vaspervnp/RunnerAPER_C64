"""Game screen mockups, built from the converted data (charset bytes, tile
character codes, column colour RAM, sprite bytes) exactly as the VIC-II
would show them: 20 playfield rows, the black band, the 3 HUD rows.

    python3 tools/mockup64.py [palette]   -> build/mockup_<scene>[_<palette>].png
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assets64 as A  # noqa: E402
import png2c64 as P  # noqa: E402
from c64palette import RGB, TRANSPARENT, colour  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD = os.path.join(ROOT, "build")
SCALE = 3

# A scene: 20 rows, top first. A row is (left side, [3 track tiles], right side)
# or a bridge row name. A track tile with "+coin" carries a coin in its middle.
R, RB = "rail_a", "rail_b"
SCENES = {
    "city": [
        ("tree_1", [R, "signal_0", R], "ground_b"),
        ("tree_0", [RB, "signal_1", RB], "ground_a"),
        "footbridge_2", "footbridge_1", "footbridge_0", "footbridge_shadow",
        ("ground_a", ["wagon1_end_top", "stop_0", RB], "tree_2"),
        ("bush", ["wagon1_body_a", "stop_1", "wagon2_end_top"], "tree_1"),
        ("trans_fu_0", ["wagon1_body_b", R, "wagon2_body_a"], "tree_0"),
        ("trans_fu_1", ["wagon1_end_bottom", RB, "wagon2_body_b+roof"], "trans_fu_1"),
        ("road_a", ["wagon1_coupler", R, "wagon2_body_a+roof"], "road_a"),
        ("road_b", ["loco1_nose_top", RB, "wagon2_body_b+roof"], "kiosk_1"),
        ("car_1", ["loco1_pantograph", R, "wagon2_body_a"], "kiosk_0"),
        ("car_0", ["loco1_body", RB, "wagon2_end_bottom"], "road_b"),
        ("road_a", ["loco1_nose", R + "+coin", "ramp_up_2"], "road_a"),
        ("road_b", [RB, RB + "+coin", "ramp_up_1"], "car_1"),
        ("road_cross_1", [R, R + "+coin", "ramp_up_0"], "car_0"),
        ("road_cross_0", [RB, RB, RB], "road_cross_0"),
        ("road_a", [R, R, R], "road_a"),
        ("kiosk_1", [RB, RB, RB], "road_b"),
        ("kiosk_0", [R, R, R], "road_a"),
    ],
    "station": [
        ("road_a", [R, R, R], "road_a"),
        "roadbridge_5", "roadbridge_4", "roadbridge_3", "roadbridge_2", "roadbridge_1", "roadbridge_0",
        ("road_b", [RB, R + "+coin", RB], "road_b"),
        ("plat_end", [R, RB + "+coin", R], "plat_end"),
        ("plat_plain", [RB, R + "+coin", "loco2_nose_top"], "plat_plain"),
        ("plat_bench", [R, RB, "loco2_body"], "plat_bench"),
        ("plat_roof", [RB, R, "loco2_pantograph"], "plat_roof"),
        ("plat_sign", [R, RB, "loco2_body"], "plat_sign"),
        ("plat_roof", ["signal_0", R, "loco2_nose"], "plat_roof"),
        ("plat_plain", ["signal_1", RB, R], "plat_plain"),
        ("plat_bench", [R, R, RB], "plat_bench"),
        ("plat_plain", [RB, RB, R], "plat_plain"),
        ("plat_end", [R, R, RB], "plat_end"),
        ("tree_2", [RB, RB, R], "ground_b"),
        ("tree_1", [R, R, RB], "ground_a"),
        ("tree_0", [RB, RB, R], "ground_a"),
    ],
}

# sprites: (sheet, frame, x, y) in hires pixels inside the playfield
SPRITES = {
    "city": [("shadow", "shadow", 148, 128), ("runner", "run0", 148, 128), ("runner_outline", "run0", 148, 128),
             ("powerups", "magnet", 76, 116)],
    "station": [("shadow", "shadow", 148, 120), ("runner", "run1", 148, 120), ("runner_outline", "run1", 148, 120),
                ("powerups", "helmet", 212, 128)],
}


def hud_rows(sheets):
    """3 rows x 40 of (char code, colour RAM)."""
    font = {ch: i for i, (_, chars) in enumerate(A.FONT_GLYPHS) for ch in chars}
    rows = [[(0, 8 | A.HUD_BG) for _ in range(40)] for _ in range(3)]

    def text(r, x, s, col):
        for i, ch in enumerate(s):
            rows[r][x + i] = (font[ch], 8 | col)

    def icon(r, x, name, off=False):
        fr = sheets["hud"][name]
        for i, (code, c11) in enumerate(zip(fr["chars"][0], fr["colours"][0])):
            rows[r][x + i] = (code, 8 | (0 if off else (c11 or 0)))

    text(0, 1, "000062", colour("white"))
    text(0, 9, "020000", colour("cyan"))
    icon(0, 24, "ic_coin")
    text(0, 27, "0015", colour("yellow"))
    icon(0, 34, "ic_life")
    text(0, 37, "3", colour("white"))
    # route: start, line with stations, here, end
    route = sheets["hud"]
    for x in range(1, 39):
        name = "route_start" if x == 1 else "route_end" if x == 38 else \
            "route_here" if x == 9 else "route_station" if x % 6 == 1 else "route_line"
        fr = route[name]
        rows[1][x] = (fr["chars"][0][0], 8 | (fr["colours"][0][0] or 0))
    for i, p in enumerate(A.POWERUPS):
        x = 1 + i * 6 + (i // 3) * 2
        on = i in (0, 4)
        icon(2, x, f"ic_{p}", off=not on)
        for b in range(3):
            lit = (3, 2)[i // 4] if on else 0
            level = 4 if b < lit else 0
            fr = route = sheets["hud"][f"bar{level}"]
            rows[2][x + 2 + b] = (fr["chars"][0][0], 8 | (fr["colours"][0][0] or 0))
    return rows


def playfield_rows(scene, sheets):
    """20 rows x 40 of (char code, colour RAM)."""
    rows = []
    cols = A.COLUMN_COLOURS
    coin_rail = P.coin_code(sheets, "coin_rail")
    coin_roof = P.coin_code(sheets, "coin_roof")
    for spec in SCENES[scene][:20]:
        if isinstance(spec, str):
            codes = sheets["bridges"][spec]["chars"][0]
        else:
            left, tracks, right = spec
            codes = list(sheets["side_l"][left]["chars"][0])
            for t in tracks:
                name, _, extra = t.partition("+")
                tile = list(sheets["track"][name]["chars"][0])
                if extra:
                    tile[A.COIN_COL] = coin_rail if extra == "coin" else coin_roof
                codes += tile
            codes += sheets["side_r"][right]["chars"][0]
        assert len(codes) == 40, spec
        rows.append([(c, 8 | cols[x]) for x, c in enumerate(codes)])
    return rows


def render(scene, palette=None):
    cs, sheets = P.convert_chars()
    sprites = {(s, f): (d, own, mc) for s, f, d, own, mc in P.convert_sprites()}
    pf = playfield_rows(scene, sheets)
    hud = hud_rows(sheets)
    bg, mc1, mc2 = A.screen_colours(palette)
    w, h = 320, 20 * 8 + 8 + 24
    img = [[bg] * w for _ in range(h)]

    def draw_chars(rows, y0, globals_):
        for r, row in enumerate(rows):
            for cx, (code, cram) in enumerate(row):
                data = cs.chars[code]
                for y, byte in enumerate(data):
                    for x in range(4):
                        bits = (byte >> (6 - 2 * x)) & 3
                        c = (globals_[0], globals_[1], globals_[2], cram & 7)[bits]
                        img[y0 + r * 8 + y][cx * 8 + 2 * x] = c
                        img[y0 + r * 8 + y][cx * 8 + 2 * x + 1] = c

    draw_chars(pf, 0, (bg, mc1, mc2))
    for y in range(160, 168):
        img[y] = [colour("black")] * w
    draw_chars(hud, 168, (A.HUD_BG, mc1, mc2))

    for sheet, frame, sx, sy in SPRITES[scene]:
        data, own, mc = sprites[(sheet, frame)]
        px = P.decode_sprite(data, mc, own)
        for y, row in enumerate(px):
            for x, c in enumerate(row):
                if c == TRANSPARENT:
                    continue
                for dx in ((0, 1) if mc else (0,)):
                    X, Y = sx + x * (2 if mc else 1) + dx, sy + y
                    if 0 <= X < w and 0 <= Y < 160:
                        img[Y][X] = c
    return img


def save(img, path):
    from PIL import Image
    h, w = len(img), len(img[0])
    border = 16
    out = Image.new("RGB", (w + 2 * border, h + 2 * border), RGB[colour("black")])
    pic = Image.new("RGB", (w, h))
    pic.putdata([RGB[c] for row in img for c in row])
    out.paste(pic, (border, border))
    out.resize((out.width * SCALE, out.height * SCALE), Image.NEAREST).save(path)


def main():
    palette = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(BUILD, exist_ok=True)
    for scene in SCENES:
        suffix = f"_{palette}" if palette else ""
        path = os.path.join(BUILD, f"mockup_{scene}{suffix}.png")
        save(render(scene, palette), path)
        print(path)


if __name__ == "__main__":
    main()
