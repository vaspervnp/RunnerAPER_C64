"""Phase 2: the graphics pipeline (no emulator).

The converter must give back exactly the pictures it was given (round trip),
keep within 256 characters, and refuse what the VIC-II cannot show.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import assets64 as A  # noqa: E402
import png2c64 as P  # noqa: E402
from c64palette import TRANSPARENT, colour  # noqa: E402


class GfxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cs, cls.sheets = P.convert_chars()
        cls.sprites = P.convert_sprites()

    def test_limit(self):
        self.assertLessEqual(len(self.cs.chars), 256)
        print(f"\n  {len(self.cs.chars)}/256 characters")

    def test_round_trip_chars(self):
        for sheet in A.CHAR_ORDER:
            g = A.sheet_colours(sheet)
            for name, fr in self.sheets[sheet].items():
                for cy, (crow, ccol) in enumerate(zip(fr["chars"], fr["colours"])):
                    for cx, (code, c11) in enumerate(zip(crow, ccol)):
                        if code is None:                     # coin phases 1-3: data only
                            continue
                        got = P.decode_cell(self.cs.chars[code], c11, g)
                        want = [[g[0] if c == TRANSPARENT else c for c in row[cx * 4:cx * 4 + 4]]
                                for row in fr["pixels"][cy * 8:cy * 8 + 8]]
                        self.assertEqual(got, want, f"{sheet}/{name} cell ({cx},{cy})")

    def test_round_trip_sprites(self):
        frames = {s: P.load_sheet(s) for s in A.SPRITE_SHEETS}
        for sheet, name, data, own, mc in self.sprites:
            self.assertEqual(len(data), 64)
            self.assertEqual(P.decode_sprite(data, mc, own), frames[sheet][name], f"{sheet}/{name}")

    def test_font_codes(self):
        for i, (name, _) in enumerate(A.FONT_GLYPHS):
            self.assertEqual(self.sheets["font"][name]["chars"][0][0], i)

    def test_coins_own_characters(self):
        codes = [P.coin_code(self.sheets, c) for c in A.COINS]
        self.assertEqual(len(set(codes)), len(codes))
        for code in codes:                                   # no tile reuses them by accident
            self.assertNotIn(code, self.cs.lookup.values())
        phases = P.coin_phase_bytes(self.sheets)
        for coin in A.COINS:
            self.assertEqual(len(phases[coin]), A.COIN_PHASES)
            self.assertEqual(self.cs.chars[P.coin_code(self.sheets, coin)], phases[coin][0])

    def test_tiles_fill_the_screen(self):
        for name, fr in self.sheets["side_l"].items():
            self.assertEqual(len(fr["chars"][0]), A.LEFT_COLS)
        for name, fr in self.sheets["side_r"].items():
            self.assertEqual(len(fr["chars"][0]), A.RIGHT_COLS)
        self.assertEqual(A.LEFT_COLS + 3 * A.TRACK_COLS + A.RIGHT_COLS, 40)

    def test_wrong_colour_is_refused(self):
        g = A.screen_colours()
        cell = [[g[0]] * 4 for _ in range(8)]
        cell[3][2] = colour("red")
        with self.assertRaises(P.GfxError):
            P.encode_cell(cell, colour("green"), g, "test")
        P.encode_cell(cell, colour("red"), g, "test")        # in a red column it is fine
        cell[4][1] = colour("orange")                        # free cell, own colour > 7
        with self.assertRaises(P.GfxError):
            P.encode_cell([[colour("orange")] * 4] * 8, None, g, "test")

    def test_too_many_characters(self):
        with self.assertRaises(P.GfxError):
            P.convert_chars(limit=len(self.cs.chars) - 1)

    def test_column_colours(self):
        self.assertEqual(len(A.COLUMN_COLOURS), 40)
        self.assertTrue(all(c < 8 for c in A.COLUMN_COLOURS))


if __name__ == "__main__":
    unittest.main()
