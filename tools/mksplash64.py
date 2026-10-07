"""The REVIVE8BIT boot screen: gfx/splash/revive8b.png (an Amstrad CPC mode 0
screen, 640 x 400 = 160 x 200 wide pixels, like the C64's multicolor) ->
a C64 multicolor bitmap.

    python3 tools/mksplash64.py        (make: src/data/splash.bin)

Every pixel goes to the nearest C64 colour. A 4 x 8 cell has black (the
background, $D021) and three colours of its own: %01 and %10 from the
screen matrix, %11 from colour RAM. Where a cell has more, the three that
leave the least error are kept and the other pixels go to the nearest of
the four.

Output: src/data/splash.bin = bitmap (8000) + screen matrix (1000) + colour
RAM (1000); build/splash_preview.png (320 x 200, as the VIC-II shows it).
"""

import itertools
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import c64palette  # noqa: E402

SRC = os.path.join(ROOT, "gfx", "splash", "revive8b.png")
OUT = os.path.join(ROOT, "src", "data", "splash.bin")
PREVIEW = os.path.join(ROOT, "build", "splash_preview.png")
BG = 0                                           # black


def dist(a, b):
    ra, rb = c64palette.RGB[a], c64palette.RGB[b]
    return sum((x - y) ** 2 for x, y in zip(ra, rb))


def load():
    im = Image.open(SRC).convert("RGB")
    sx, sy = im.width // 160, im.height // 200
    if (sx, sy) != (4, 2):
        raise SystemExit(f"mksplash64: {SRC} is {im.width} x {im.height}, not 640 x 400")
    px = im.load()
    cache = {}

    def c64(rgb):
        if rgb not in cache:
            cache[rgb] = c64palette.nearest(rgb)
        return cache[rgb]
    return [[c64(px[x * sx + 1, y * sy]) for x in range(160)] for y in range(200)]


def best_three(cell):
    """the cell's three colours (besides black) with the least error"""
    found = sorted({c for c in cell if c != BG}, key=lambda c: -cell.count(c))
    if len(found) <= 3:
        return (found + [BG, BG, BG])[:3], 0
    best = None
    for three in itertools.combinations(found, 3):
        pal = (BG,) + three
        err = sum(min(dist(c, p) for p in pal) for c in cell)
        if best is None or err < best[0]:
            best = (err, list(three))
    over = sum(1 for c in cell if c not in best[1] and c != BG)
    return best[1], over


def convert(img):
    bitmap, screen, colram = bytearray(8000), bytearray(1000), bytearray(1000)
    over = 0
    for cy in range(25):
        for cx in range(40):
            cell = [img[cy * 8 + r][cx * 4 + c] for r in range(8) for c in range(4)]
            three, n = best_three(cell)
            over += n
            c01, c10, c11 = three
            i = cy * 40 + cx
            screen[i] = c01 << 4 | c10
            colram[i] = c11
            pal = [BG, c01, c10, c11]
            for r in range(8):
                b = 0
                for c in range(4):
                    col = img[cy * 8 + r][cx * 4 + c]
                    code = pal.index(col) if col in pal else min(range(4), key=lambda k: dist(col, pal[k]))
                    b |= code << (6 - 2 * c)
                bitmap[i * 8 + r] = b
    return bitmap, screen, colram, over


def decode(bitmap, screen, colram):
    """160 x 200 colour indices, as the VIC-II draws them"""
    out = []
    for y in range(200):
        row = []
        for x in range(160):
            i = (y // 8) * 40 + x // 4
            code = bitmap[i * 8 + y % 8] >> (6 - 2 * (x % 4)) & 3
            row.append((BG, screen[i] >> 4, screen[i] & 15, colram[i] & 15)[code])
        out.append(row)
    return out


def main():
    img = load()
    bitmap, screen, colram, over = convert(img)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(bitmap + screen + colram)
    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    pix = decode(bitmap, screen, colram)
    im = Image.new("P", (160, 200))
    im.putpalette(c64palette.flat_palette())
    im.putdata([c for row in pix for c in row])
    im.resize((320, 200), Image.NEAREST).save(PREVIEW)
    print(f"mksplash64: {over} of 32000 pixels changed colour to fit the cells ({100 * over / 32000:.1f} %)")


if __name__ == "__main__":
    main()
