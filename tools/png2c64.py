"""gfx/png sheets -> charset, tiles and sprites for the assembler.

    python3 tools/png2c64.py            writes src/data/{charset.bin, sprites.bin, gfx.asm, gfx.inc}
                                        and build/gfx_report.txt

Characters: every 4x8 cell of a character sheet becomes 8 bytes of
multicolor bitmap; identical cells share one character. The build fails
when a pixel has a colour its cell cannot show (see assets64: BG/MC1/MC2 or
the column's colour RAM) or when more than 256 characters are needed.
Font glyphs get codes 0.. in FONT_GLYPHS order (text bytes = glyph index);
coin characters get their own codes (their bytes are rewritten at run
time) and are never shared.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import assets64 as A  # noqa: E402
from c64palette import NAMES, TRANSPARENT, load_indices  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PNG = os.path.join(ROOT, "gfx", "png")
OUT = os.path.join(ROOT, "src", "data")
BUILD = os.path.join(ROOT, "build")


class GfxError(Exception):
    pass


def load_sheet(name):
    """-> {frame: rows of colour indices}, in the order of the .json."""
    w, h, rows = load_indices(os.path.join(PNG, name + ".png"))
    with open(os.path.join(PNG, name + ".json")) as f:
        meta = json.load(f)
    frames = {}
    for fr in meta["frames"]:
        r = fr["frame"]
        frames[fr["filename"]] = [row[r["x"]:r["x"] + r["w"]] for row in rows[r["y"]:r["y"] + r["h"]]]
    return frames


def encode_cell(cell, c11, globals_, where):
    """4x8 colour indices -> (8 bytes, colour RAM). c11 None = free: taken from
    the pixels (the one colour that is not BG/MC1/MC2)."""
    bg, mc1, mc2 = globals_
    if c11 is None:
        extra = {c for row in cell for c in row} - {bg, mc1, mc2}
        if len(extra) > 1:
            raise GfxError(f"{where}: more than one colour of its own ({', '.join(NAMES[c] for c in extra)})")
        c11 = extra.pop() if extra else None
        if c11 is not None and c11 > 7:
            raise GfxError(f"{where}: {NAMES[c11]} cannot be a multicolor character's own colour (0-7 only)")
    out = []
    for y, row in enumerate(cell):
        byte = 0
        for x, c in enumerate(row):
            if c == bg or c == TRANSPARENT:
                bits = 0
            elif c == mc1:
                bits = 1
            elif c == mc2:
                bits = 2
            elif c == c11:
                bits = 3
            else:
                allowed = [NAMES[bg], NAMES[mc1], NAMES[mc2]] + ([NAMES[c11]] if c11 is not None else [])
                raise GfxError(f"{where}: pixel ({x},{y}) is {NAMES[c]}, the cell can only show {'/'.join(allowed)}")
            byte |= bits << (6 - 2 * x)
        out.append(byte)
    return bytes(out), c11


def decode_cell(data, c11, globals_):
    """8 bytes -> 4x8 colour indices (the round trip)."""
    bg, mc1, mc2 = globals_
    src = (bg, mc1, mc2, c11 if c11 is not None else bg)
    return [[src[(b >> (6 - 2 * x)) & 3] for x in range(4)] for b in data]


class Charset:
    def __init__(self):
        self.chars = []            # code -> 8 bytes
        self.lookup = {}           # bytes -> code (shareable characters only)
        self.owner = []            # code -> first user, for the report

    def add(self, data, who, share=True):
        if share and data in self.lookup:
            return self.lookup[data]
        code = len(self.chars)
        self.chars.append(data)
        self.owner.append(who)
        if share:
            self.lookup.setdefault(data, code)
        return code


def convert_chars(palette=None, limit=256):
    """-> (charset, {sheet: {frame: dict(chars=[[code]], colours=[[c11]], cells=[[bytes]])}})"""
    cs = Charset()
    sheets = {}
    for sheet in A.CHAR_ORDER:
        globals_ = A.sheet_colours(sheet, palette)
        spec = A.CHAR_SHEETS[sheet]
        frames = load_sheet(sheet)
        out = {}
        for name, w, h in spec["frames"]:
            if name not in frames:
                raise GfxError(f"{sheet}.png: frame '{name}' missing")
            px = frames[name]
            if len(px) != h or len(px[0]) != w:
                raise GfxError(f"{sheet}/{name}: {len(px[0])}x{len(px)}, expected {w}x{h}")
            cols = spec["cols"]((name, w, h))
            if len(cols) != w // 4:
                raise GfxError(f"{sheet}/{name}: {w // 4} columns, the layout has {len(cols)}")
            chars, colours = [], []
            for cy in range(h // 8):
                crow, ccol = [], []
                for cx in range(w // 4):
                    cell = [row[cx * 4:cx * 4 + 4] for row in px[cy * 8:cy * 8 + 8]]
                    data, c11 = encode_cell(cell, cols[cx], globals_, f"{sheet}/{name} cell ({cx},{cy})")
                    who = f"{sheet}/{name}"
                    if spec.get("fixed"):
                        code = cs.add(data, who, share=False)
                        cs.lookup.setdefault(data, code)
                    elif sheet == "coins":
                        code = cs.add(data, who, share=False) if name.endswith("_0") else None
                    else:
                        code = cs.add(data, who)
                    crow.append(code)
                    ccol.append(c11)
                chars.append(crow)
                colours.append(ccol)
            out[name] = dict(chars=chars, colours=colours, pixels=px)
        sheets[sheet] = out
    if limit and len(cs.chars) > limit:
        raise GfxError(f"{len(cs.chars)} characters, only {limit} fit\n{report(cs)}")
    return cs, sheets


def coin_code(sheets, coin):
    return sheets["coins"][f"{coin}_0"]["chars"][0][0]


def coin_phase_bytes(sheets, palette=None):
    """{coin: [8 bytes per phase]}"""
    globals_ = A.screen_colours(palette)
    out = {}
    for coin in A.COINS:
        phases = []
        for p in range(A.COIN_PHASES):
            px = sheets["coins"][f"{coin}_{p}"]["pixels"]
            phases.append(encode_cell(px, A.TRACK_MID, globals_, f"coins/{coin}_{p}")[0])
        out[coin] = phases
    return out


# --- sprites --------------------------------------------------------------
def encode_sprite(px, mc, where):
    """12x21 (multicolor) or 24x21 (hires) colours -> (64 bytes, own colour)."""
    w = 12 if mc else 24
    if len(px) != 21 or len(px[0]) != w:
        raise GfxError(f"{where}: {len(px[0])}x{len(px)}, expected {w}x21")
    shared = {A.SPRITE_MC0, A.SPRITE_MC1} if mc else set()
    own = {c for row in px for c in row} - shared - {TRANSPARENT}
    if len(own) > 1:
        raise GfxError(f"{where}: more than one colour of its own ({', '.join(NAMES[c] for c in own)})")
    own = own.pop() if own else 0
    data = []
    for row in px:
        bits = 0
        for c in row:
            if mc:
                v = 0 if c == TRANSPARENT else 1 if c == A.SPRITE_MC0 else 3 if c == A.SPRITE_MC1 else 2
                bits = (bits << 2) | v
            else:
                bits = (bits << 1) | (0 if c == TRANSPARENT else 1)
        data += [(bits >> 16) & 255, (bits >> 8) & 255, bits & 255]
    return bytes(data + [0]), own


def decode_sprite(data, mc, own):
    rows = []
    for y in range(21):
        bits = (data[y * 3] << 16) | (data[y * 3 + 1] << 8) | data[y * 3 + 2]
        if mc:
            src = (TRANSPARENT, A.SPRITE_MC0, own, A.SPRITE_MC1)
            rows.append([src[(bits >> (22 - 2 * x)) & 3] for x in range(12)])
        else:
            rows.append([own if (bits >> (23 - x)) & 1 else TRANSPARENT for x in range(24)])
    return rows


def convert_sprites():
    """-> list of (sheet, frame, 64 bytes, own colour, mc)"""
    out = []
    for sheet, spec in A.SPRITE_SHEETS.items():
        frames = load_sheet(sheet)
        for name in spec["frames"]:
            data, own = encode_sprite(frames[name], spec["mc"], f"{sheet}/{name}")
            out.append((sheet, name, data, own, spec["mc"]))
    return out


# --- output ---------------------------------------------------------------
def ident(s):
    return s.upper().replace("-", "_")


def write_outputs(cs, sheets, sprites):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "charset.bin"), "wb") as f:
        f.write(b"".join(cs.chars) + bytes(8 * (256 - len(cs.chars))))
    with open(os.path.join(OUT, "sprites.bin"), "wb") as f:
        f.write(b"".join(d for _, _, d, _, _ in sprites))

    inc = ["; generated by tools/png2c64.py - do not edit", ""]
    inc.append(f"CHARS_USED = {len(cs.chars)}")
    for coin in A.COINS:
        inc.append(f"CH_{ident(coin)} = {coin_code(sheets, coin)}")
    for i, (name, _) in enumerate(A.FONT_GLYPHS):
        inc.append(f"FONT_{ident(name)} = {i}")
    for sheet, prefix in (("track", "T"), ("side_l", "S"), ("bridges", "B")):
        for i, (name, _, _) in enumerate(A.CHAR_SHEETS[sheet]["frames"]):
            inc.append(f"{prefix}_{ident(name)} = {i}")
    inc.append(f"TRACK_TILES = {len(A.TRACK_TILES)}")
    inc.append(f"SIDE_TILES = {len(A.SIDE_KINDS)}")
    for i, (sheet, name, _, own, _) in enumerate(sprites):
        inc.append(f"SPR_{ident(sheet)}_{ident(name)} = {i}")
        inc.append(f"SPR_{ident(sheet)}_{ident(name)}_COL = {own}")
    inc.append(f"SPRITE_MC0 = {A.SPRITE_MC0}")
    inc.append(f"SPRITE_MC1 = {A.SPRITE_MC1}")
    with open(os.path.join(OUT, "gfx.inc"), "w") as f:
        f.write("\n".join(inc) + "\n")

    asm = ["; generated by tools/png2c64.py - do not edit", ""]

    def table(label, sheet, frames=None):
        asm.append(label)
        for name, _, _ in A.CHAR_SHEETS[sheet]["frames"]:
            if frames is None or name in frames:
                codes = [c for row in sheets[sheet][name]["chars"] for c in row]
                asm.append(f"        .byte {', '.join(str(c) for c in codes)}   ; {name}")

    table("track_chars", "track")
    table("side_l_chars", "side_l")
    table("side_r_chars", "side_r")
    table("bridge_chars", "bridges")
    asm.append("hud_chars")
    for name, _, _ in A.CHAR_SHEETS["hud"]["frames"]:
        fr = sheets["hud"][name]
        asm.append(f"        .byte {', '.join(str(c) for c in fr['chars'][0])}   ; {name}")
    asm.append("hud_colours")
    for name, _, _ in A.CHAR_SHEETS["hud"]["frames"]:
        fr = sheets["hud"][name]
        asm.append(f"        .byte {', '.join(str(8 | (c or 0)) for c in fr['colours'][0])}   ; {name}")
    asm.append("coin_phases")
    for coin, phases in coin_phase_bytes(sheets).items():
        for p, data in enumerate(phases):
            asm.append(f"        .byte {', '.join(f'${b:02x}' for b in data)}   ; {coin} {p}")
    asm.append("column_colours")
    asm.append(f"        .byte {', '.join(str(8 | c) for c in A.COLUMN_COLOURS)}")
    with open(os.path.join(OUT, "gfx.asm"), "w") as f:
        f.write("\n".join(asm) + "\n")


def report(cs):
    counts = {}
    for who in cs.owner:
        counts[who.split("/")[0]] = counts.get(who.split("/")[0], 0) + 1
    lines = [f"characters: {len(cs.chars)} / 256"] + [f"  {k:8s} {v}" for k, v in counts.items()]
    frames = {}
    for who in cs.owner:
        frames[who] = frames.get(who, 0) + 1
    lines += ["new characters by frame:"] + [f"  {k}: {v}" for k, v in frames.items()]
    return "\n".join(lines)


def main():
    try:
        cs, sheets = convert_chars()
        sprites = convert_sprites()
    except GfxError as e:
        sys.exit(f"png2c64: {e}")
    write_outputs(cs, sheets, sprites)
    text = report(cs) + f"\nsprites: {len(sprites)} ({len(sprites) * 64} bytes)\n"
    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, "gfx_report.txt"), "w") as f:
        f.write(text)
    print(f"png2c64: {len(cs.chars)}/256 characters, {len(sprites)} sprites (build/gfx_report.txt)")


if __name__ == "__main__":
    main()
