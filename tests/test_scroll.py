"""Phase 1: multicolor char mode, double-buffered vertical scroll, HUD split.

Checked at the end of the top IRQ of every frame (the picture of that frame
is decided there):
  - the shown screen holds world row (disp_top - r) in screen row r, whole
    (no half-copied row ever shows): the characters of that row;
  - the position disp_top*8 + YSCROLL advances by exactly the speed;
  - in pixels, each picture is the previous one moved down by the speed,
    the band $d7-$de is black and the HUD never moves;
  - no frame overruns and the hidden buffer is always ready in time.
"""

import unittest

from vice import Vice
from world_view import model_rows, row_chars

SCREEN_A, SCREEN_B = 0x4000, 0x4400
PF_ROWS = 21
BUF_Y = -1                      # VICE canvas line = raster line - 1
PF_FIRST, PF_LAST = 0x37, 0xD6  # playfield lines (24-row window starts at $37)
BAND = range(0xD7, 0xDF)
HUD = range(0xDF, 0xF7)


def expected_row(world_row):
    """The characters of a world row (the world is made on easy at boot)."""
    return bytes(row_chars(model_rows(400)[world_row]))


class Scroll:
    """One VICE, scrolling at a given speed (pixels per frame, 8.8)."""

    def __init__(self, speed):
        self.vm = Vice()
        vm = self.vm
        vm.run_frames(3)
        whole = int(speed)
        vm.poke("speed_lo", int(round((speed - whole) * 256)) & 0xFF)
        vm.poke("speed_hi", whole)
        vm.run_frames(4)                          # let the new speed settle
        for name in ("overruns", "stalls"):
            vm.poke(name, 0)
        vm.poke("max_load", b"\x00\x00")

    def close(self):
        self.vm.close()

    def state(self):
        """(position in pixels, YSCROLL, shown screen address, top world row)"""
        vm = self.vm
        vm.run_to("irq_top_done")
        y = vm.peek8(0xD011) & 7
        screen = SCREEN_A if (vm.peek8(0xD018) >> 4) == 0 else SCREEN_B
        top = vm.peek16("disp_top")
        return top * 8 + y, y, screen, top

    def picture(self):
        """The finished picture of the previous frame, one list per raster line."""
        dw, dh, xo, yo, iw, ih, px = self.vm.display()
        return {line: px[(line + BUF_Y) * dw + xo:(line + BUF_Y) * dw + xo + 320]
                for line in range(PF_FIRST, HUD.stop)}


class ScrollTest(unittest.TestCase):
    def run_speed(self, speed, frames, pixels=False):
        sc = Scroll(speed)
        self.addCleanup(sc.close)
        vm = sc.vm
        positions, ys, pictures = [], set(), []
        for _ in range(frames):
            pos, y, screen, top = sc.state()
            positions.append(pos)
            ys.add(y)
            shown = vm.peek(screen, PF_ROWS * 40)
            for r in range(PF_ROWS):
                self.assertEqual(shown[r * 40:(r + 1) * 40], expected_row((top - r) & 0xFFFF),
                                 f"speed {speed}: screen row {r} of ${screen:04X} is not world row {top - r}")
            if pixels:
                pictures.append((sc.picture(), pos))  # picture of the frame before
        deltas = [b - a for a, b in zip(positions, positions[1:])]
        self.assertEqual(vm.peek8("overruns"), 0)
        self.assertEqual(vm.peek8("stalls"), 0)
        return deltas, ys, pictures, vm.peek16("max_load")

    def test_speeds(self):
        for speed in (2, 3, 4):
            with self.subTest(speed=speed):
                deltas, ys, _, load = self.run_speed(speed, 40)
                self.assertEqual(set(deltas), {speed})
                self.assertLess(load, 312, "a frame took longer than one frame")

    def test_half_speed(self):
        deltas, *_ = self.run_speed(2.5, 40)
        self.assertEqual(set(deltas), {2, 3})
        for a, b in zip(deltas, deltas[1:]):
            self.assertEqual(a + b, 5)                 # 2/3 alternate

    def test_pixels(self):
        # speeds 3 and 2.5: YSCROLL goes through all of 0-7, so the band is
        # seen in every case, with different raster jitter each time
        for speed in (3, 2.5, 4):
            with self.subTest(speed=speed):
                self.check_pixels(speed, 60)

    def check_pixels(self, speed, frames):
        deltas, ys, pictures, _ = self.run_speed(speed, frames, pixels=True)
        if speed != 4:
            self.assertEqual(ys, set(range(8)))
        # pictures[k] = picture shown at position pictures[k-1][1]
        shown = [(pictures[k][0], pictures[k - 1][1]) for k in range(1, len(pictures))]
        hud = shown[0][0][HUD.start]
        for (prev, prev_pos), (cur, cur_pos) in zip(shown, shown[1:]):
            d = cur_pos - prev_pos
            self.assertIn(d, (int(speed), int(speed + 0.5)))
            for line in range(PF_FIRST + d, PF_LAST + 1):
                self.assertEqual(cur[line], prev[line - d], f"line ${line:02X} did not move by {d}")
            for line in BAND:
                self.assertEqual(set(cur[line]), {0}, f"band line ${line:02X} not black")
            self.assertNotEqual(set(cur[PF_LAST]), {0})        # the playfield reaches the band
            self.assertNotEqual(set(cur[PF_FIRST]), {0})
            self.assertEqual(cur[HUD.start], hud)
            for line in HUD:
                self.assertEqual(cur[line], prev[line], f"HUD line ${line:02X} moved")

    def test_load_at_max_speed(self):
        *_, load = self.run_speed(4, 100)
        print(f"\n  max frame load at speed 4: line {load} of 312")
        self.assertLess(load, 312)


class CyclesTest(unittest.TestCase):
    """Cycle counts from the raster position (LIN/CYC) at entry and exit."""

    @classmethod
    def setUpClass(cls):
        cls.vm = Vice()
        cls.vm.run_frames(5)
        cls.vm.poke("speed_hi", 4)

    @classmethod
    def tearDownClass(cls):
        cls.vm.close()

    def cycles(self, start, end, var=None):
        """Cycles from `start` to `end` (wall time: includes bad lines and any
        IRQ that comes in between), and the value of `var` at `start`."""
        a = self.vm.run_to(start)
        value = self.vm.peek8(var) if var else None
        b = self.vm.run_to(end)
        return ((b["LIN"] - a["LIN"]) % 312) * 63 + (b["CYC"] - a["CYC"]), value

    def test_cycle_budget(self):
        results = {}
        for _ in range(40):                              # both stages, both buffers
            c, stage = self.cycles("copy_go", "copy_done", "copy_stage")
            results.setdefault(f"build stage {stage}", []).append(c)
        for _ in range(4):
            results.setdefault("top IRQ", []).append(self.cycles("irq_top", "irq_top_done")[0])
            results.setdefault("split IRQ", []).append(self.cycles("irq_split", "irq_split_end")[0])
        print()
        for k, v in sorted(results.items()):
            print(f"  {k}: {min(v)}-{max(v)} cycles")
        # wall time: the split IRQ (~750) may fall inside a stage.
        # stage 0: 8 rows + the new row's descriptor (world.asm, ~1600-5000)
        # stage 1: 12 rows + its 40 characters
        self.assertLess(max(results["build stage 0"]), 9000)
        self.assertLess(max(results["build stage 1"]), 7000)
        self.assertLess(max(results["split IRQ"]), 900)
        self.assertLess(max(results["top IRQ"]), 200)


if __name__ == "__main__":
    unittest.main()
