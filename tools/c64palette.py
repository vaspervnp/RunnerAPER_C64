"""The C64 palette (VICE 'pepto-pal', the default of x64sc) and colour matching.

Run as a script to write gfx/palette/c64.gpl for Aseprite.
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

NAMES = ["black", "white", "red", "cyan", "purple", "green", "blue", "yellow",
         "orange", "brown", "light_red", "dark_grey", "grey", "light_green", "light_blue", "light_grey"]

# pepto PAL (VICE pepto-pal.vpl)
RGB = [
    (0x00, 0x00, 0x00), (0xFF, 0xFF, 0xFF), (0x68, 0x37, 0x2B), (0x70, 0xA4, 0xB2),
    (0x6F, 0x3D, 0x86), (0x58, 0x8D, 0x43), (0x35, 0x28, 0x79), (0xB8, 0xC7, 0x6F),
    (0x6F, 0x4F, 0x25), (0x43, 0x39, 0x00), (0x9A, 0x67, 0x59), (0x44, 0x44, 0x44),
    (0x6C, 0x6C, 0x6C), (0x9A, 0xD2, 0x84), (0x6C, 0x5E, 0xB5), (0x95, 0x95, 0x95),
]

BY_NAME = {n: i for i, n in enumerate(NAMES)}
TRANSPARENT = -1


def colour(name_or_index):
    return BY_NAME[name_or_index] if isinstance(name_or_index, str) else name_or_index


def nearest(rgb):
    """Index of the palette colour closest to rgb (exact for our own sheets)."""
    r, g, b = rgb[:3]
    return min(range(16), key=lambda i: (RGB[i][0] - r) ** 2 + (RGB[i][1] - g) ** 2 + (RGB[i][2] - b) ** 2)


def flat_palette():
    """256*3 list for PIL putpalette: entries 0-15 = C64, 16 = transparent key (magenta)."""
    pal = [c for rgb in RGB for c in rgb] + [0xFF, 0x00, 0xFF]
    return pal + [0] * (768 - len(pal))


TRANSPARENT_INDEX = 16


def load_indices(path):
    """PNG -> (width, height, rows of C64 colour indices; TRANSPARENT for transparent pixels).
    Indexed PNGs with our palette are read by index; anything else by nearest colour."""
    from PIL import Image
    im = Image.open(path)
    if im.mode == "P" and im.getpalette()[:48] == flat_palette()[:48]:
        trans = im.info.get("transparency")
        px = list(im.getdata())
        rows = [[TRANSPARENT if (p == TRANSPARENT_INDEX or p == trans) else p
                 for p in px[y * im.width:(y + 1) * im.width]] for y in range(im.height)]
        return im.width, im.height, rows
    im = im.convert("RGBA")
    px = list(im.getdata())
    rows = [[TRANSPARENT if p[3] < 128 else nearest(p) for p in px[y * im.width:(y + 1) * im.width]]
            for y in range(im.height)]
    return im.width, im.height, rows


def save_indices(path, rows, scale_x=1, scale=1):
    """Rows of C64 indices (TRANSPARENT allowed) -> indexed PNG with our palette."""
    from PIL import Image
    h, w = len(rows), len(rows[0])
    im = Image.new("P", (w, h))
    im.putpalette(flat_palette())
    im.putdata([TRANSPARENT_INDEX if c == TRANSPARENT else c for row in rows for c in row])
    im.info["transparency"] = TRANSPARENT_INDEX
    if scale_x != 1 or scale != 1:
        im = im.resize((w * scale_x * scale, h * scale), Image.NEAREST)
    im.save(path, transparency=TRANSPARENT_INDEX)


def write_gpl(path):
    with open(path, "w") as f:
        f.write("GIMP Palette\nName: C64 pepto PAL\nColumns: 8\n#\n")
        for (r, g, b), n in zip(RGB, NAMES):
            f.write(f"{r:3d} {g:3d} {b:3d}\t{n}\n")


if __name__ == "__main__":
    out = os.path.join(ROOT, "gfx", "palette")
    os.makedirs(out, exist_ok=True)
    write_gpl(os.path.join(out, "c64.gpl"))
