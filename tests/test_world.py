"""Phase 3: the world on the C64 (src/world.asm).

  - every row descriptor the C64 makes is the model's (tools/worldgen.py,
    itself checked against the CPC by test_world_cpc), on all three skills;
  - every row on the screen is the characters of its descriptor;
  - easy: at most two obstacles a lane within a CPC screen (34 rows);
  - all this at the highest speed without a frame lost.
"""

import unittest

from vice import Vice
from world_view import W, model_rows, row_chars

SCREEN_A, SCREEN_B = 0x4000, 0x4400
WORLD_RING = 0x0400
PF_ROWS = 21
ROWS = 700                     # world rows per skill (4 px a frame: 2 frames a row)


class WorldRun:
    def __init__(self, skill):
        self.vm = Vice()
        vm = self.vm
        vm.run_frames(2)
        vm.poke("skill", skill)
        vm.poke("restart", 1)
        vm.run_frames(3)
        vm.poke("speed_hi", 4)
        vm.poke("no_crash", 1)                   # (test_collisions has the crashes)
        vm.poke("no_pickups", 1)                 # (test_pickups has the items)
        vm.poke("speed_lo", 0)
        for name in ("overruns", "stalls"):
            vm.poke(name, 0)
        vm.poke("max_load", b"\x00\x00")


class WorldTest(unittest.TestCase):
    def run_skill(self, skill):
        run = WorldRun(skill)
        self.addCleanup(run.vm.close)
        vm = run.vm
        model = model_rows(ROWS + 80, skill)
        seen, screens = {}, 0
        while True:
            vm.run_to("irq_top_done")
            top = vm.peek16("disp_top")
            gen = vm.peek16("gen_row")
            ring = vm.peek(WORLD_RING, 64 * 16)
            for n in range(max(0, gen - 50), gen + 1):
                if n not in seen:
                    seen[n] = list(ring[(n & 63) * 16:(n & 63) * 16 + 13])
            # the picture: every row the characters of its descriptor
            screen = SCREEN_A if vm.peek8(0xD018) >> 4 == 0 else SCREEN_B
            shown = vm.peek(screen, PF_ROWS * 40)
            for r in range(PF_ROWS):
                n = top - r
                if n < 0:
                    continue
                desc = list(ring[(n & 63) * 16:(n & 63) * 16 + 16])
                self.assertEqual(list(shown[r * 40:r * 40 + 40]), row_chars(desc),
                                 f"skill {skill}: screen row {r} (world row {n}) differs from its descriptor")
            screens += 1
            if gen >= ROWS:
                break
            vm.run_frames(40)
        for n, desc in sorted(seen.items()):
            self.assertEqual(desc, model[n][:13], f"skill {skill}: world row {n} differs from the model")
        self.assertEqual(vm.peek8("overruns"), 0, "a frame was lost")
        self.assertEqual(vm.peek8("stalls"), 0, "the hidden screen was late")
        load = vm.peek16("max_load")
        print(f"\n  skill {skill}: {len(seen)} rows, {screens} screens checked, max load line {load}")
        self.assertLess(load, 312)

    def test_easy(self):
        self.run_skill(0)

    def test_medium(self):
        self.run_skill(1)

    def test_hard(self):
        self.run_skill(2)


class EasyRuleTest(unittest.TestCase):
    def test_two_obstacles_a_lane_a_screen(self):
        """Easy: a buffer stop or signal never starts while two other obstacles
        started in its lane within the last 34 rows (trains count, stay)."""
        rows = model_rows(6000, 0)
        for lane in range(3):
            starts = []                          # (row, class) of obstacle starts
            prev = 0
            for n, d in enumerate(rows):
                c = d[W.D_COLL + lane] & 15
                obstacle = c in (W.COL_STOP, W.COL_SIGNAL, W.COL_TRAIN, W.COL_NOSE, W.COL_GAP)
                if obstacle and not prev:
                    starts.append((n, c))
                prev = obstacle
            for i, (n, c) in enumerate(starts):
                if c in (W.COL_STOP, W.COL_SIGNAL) and i >= 2:
                    self.assertGreaterEqual(n - starts[i - 2][0], 34,
                                            f"lane {lane}: third obstacle at row {n} within 34 rows")


if __name__ == "__main__":
    unittest.main()
