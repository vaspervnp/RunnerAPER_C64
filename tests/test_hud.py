"""Phase 7: the HUD (src/hud.asm), screen rows 21-23.

What the screen shows, read back (characters of both screens, colour RAM),
equals the values in memory: score, best, coins, lives, the runner on the
route, the six power-ups (icon lit or black, bar pixels = timer / step
rounded up). Both screens always hold the same HUD.
"""

import unittest

from vice import Vice

SCREEN_A, SCREEN_B, CRAM = 0x4000, 0x4400, 0xD800
HUD_ROW = 21
SCORE_X, HI_X, COINS_X, LIVES_X = 1, 9, 27, 37
ROUTE_FIRST, ROUTE_LAST = 1, 38
PU_X = (1, 7, 13, 21, 27, 33)
PU_STEPS = (42, 34, 34, 42, 0, 63)
TIMERS = ("pu_magnet", "pu_turbo", "pu_slow", "pu_spring", None, "pu_ticket")
HC_BAR, HC_LINE, HC_STATION, HC_HERE, HC_START, HC_END = 16, 21, 22, 23, 24, 25


def bcd(data):
    return int("".join(f"{b:02x}" for b in reversed(data)))


class Hud:
    def __init__(self, vm):
        self.vm = vm
        self.n0 = vm.addr("FONT_N0")
        self.chars = vm.peek("hud_chars", 26)
        self.colours = vm.peek("hud_colours", 26)

    def read(self):
        vm = self.vm
        a = vm.peek(SCREEN_A + HUD_ROW * 40, 120)
        b = vm.peek(SCREEN_B + HUD_ROW * 40, 120)
        cram = [c & 15 for c in vm.peek(CRAM + HUD_ROW * 40, 120)]
        return a, b, cram

    def number(self, row, x, digits):
        return int("".join(str(c - self.n0) for c in row[x:x + digits]))


class HudTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vm = vm = Vice()
        vm.run_frames(2)
        for name, value in (("test_mode", 1), ("test_keys", 0), ("no_crash", 1), ("no_pickups", 1)):
            vm.poke(name, value)
        cls.hud = Hud(vm)

    @classmethod
    def tearDownClass(cls):
        cls.vm.close()

    def check(self):
        """the HUD on the screen = the values in memory"""
        vm, h = self.vm, self.hud
        a, b, cram = h.read()
        self.assertEqual(a, b, "both screens hold the same HUD")
        score = bcd(vm.peek("score", 3))
        best = bcd(vm.peek("best", 3))
        self.assertEqual(h.number(a, SCORE_X, 6), score)
        self.assertEqual(h.number(a, HI_X, 6), max(score, best))
        self.assertEqual(h.number(a, COINS_X, 4), bcd(vm.peek("coins", 2)))
        self.assertEqual(h.number(a, LIVES_X, 1), vm.peek8("lives"))
        here = vm.peek8("route_x")
        for x in range(ROUTE_FIRST, ROUTE_LAST + 1) if not vm.peek8("msg_timer") else ():
            if x == here:
                want = HC_HERE
            elif x == ROUTE_FIRST:
                want = HC_START
            elif x == ROUTE_LAST:
                want = HC_END
            else:
                want = HC_STATION if (x - ROUTE_FIRST) % 6 == 0 else HC_LINE
            self.assertEqual(a[40 + x], h.chars[want], f"route column {x}")
            self.assertEqual(cram[40 + x], h.colours[want] & 15, f"route column {x} colour")
        for i, x in enumerate(PU_X):
            if TIMERS[i] is None:
                pixels = 12 if vm.peek8("helmet") else 0
            else:
                t = vm.peek16(TIMERS[i])
                pixels = min(12, -(-t // PU_STEPS[i]))
            lit = pixels > 0
            for k in (0, 1):
                self.assertEqual(cram[80 + x + k], (h.colours[2 * i + k] & 15) if lit else 8,
                                 f"power-up {i} icon colour (pixels {pixels})")
            for k in range(3):
                level = max(0, min(4, pixels - 4 * k))
                self.assertEqual(a[80 + x + 2 + k], h.chars[HC_BAR + level], f"power-up {i} bar {k}, pixels {pixels}")

    def test_1_start(self):
        self.vm.run_frames(1)
        self.check()
        self.assertEqual(self.hud.number(self.hud.read()[0], HI_X, 6), 20000)

    def test_2_values(self):
        vm = self.vm
        vm.poke("speed_hi", 0)
        vm.poke("score", bytes([0x56, 0x34, 0x12]))
        vm.poke("coins", bytes([0x42, 0x00]))
        vm.poke("lives", 2)
        vm.poke("pu_magnet", (250).to_bytes(2, "little"))
        vm.poke("pu_slow", (1).to_bytes(2, "little"))
        vm.poke("pu_ticket", (750).to_bytes(2, "little"))
        vm.poke("helmet", 6)
        vm.poke("route_x", 20)
        vm.run_frames(1)
        self.check()
        a = self.hud.read()[0]
        self.assertEqual(self.hud.number(a, HI_X, 6), 123456, "the best is this score")

    def test_3_bars_run_down(self):
        vm = self.vm
        vm.poke("pu_turbo", (200).to_bytes(2, "little"))
        vm.poke("pu_spring", (90).to_bytes(2, "little"))
        vm.poke("helmet", 0)
        vm.poke("route_x", 5)
        vm.poke("speed_hi", 2)
        vm.poke("no_pickups", 0)                # the timers run (no items: no_crash world)
        for _ in range(120):
            vm.run_frames(1)
            self.check()
        self.assertEqual(vm.peek16("pu_spring"), 0)

    def test_4_cost(self):
        """everything redrawn at once (score, best, coins, lives, route, 6 power-ups)"""
        vm = self.vm
        vm.poke("speed_hi", 0)
        vm.poke("hud_shown", bytes([0xFF] * 16))
        vm.run_to("hud_update")
        start = vm.registers()
        vm.run_to("frame_done")
        end = vm.registers()
        cycles = (end["LIN"] - start["LIN"]) % 312 * 63 + end["CYC"] - start["CYC"]
        print(f"\n  hud_update, all redrawn: ~{cycles} cycles")
        self.assertLess(cycles, 6000)
        self.check()


if __name__ == "__main__":
    unittest.main()
