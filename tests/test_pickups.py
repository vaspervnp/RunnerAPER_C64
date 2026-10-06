"""Phase 6: coins, power-ups, score, stations (src/pickups.asm).

Each test runs on a flat track: every row the generator makes from then on
loses its obstacles and items, and gets the ones the test planted (written
when the row is made, before it is drawn). Rows drawn before that are left
out of the picture checks.

  - a coin under the feet: +1 coin, +10 points, its character gone from the
    picture (shown screen, frame after frame: both buffers in turn);
  - a jump flies over a coin;
  - power-ups: sprite 6 over their row, then the timer (the CPC's x 2), the
    effect, the name on the track (scrolling with it);
  - magnet: the coins of the lanes around the runner fly to it, no traces;
  - stations: the name, the next station, Piraeus +1000;
  - score: a point a row (2 with turbo);
  - no frame lost with the magnet at the highest speed.
"""

import os
import struct
import sys
import unittest

from vice import EV_CHECKPOINT, EV_STOPPED, Vice
from world_view import COIN_RAIL, COIN_ROOF

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import mktext64  # noqa: E402

WORLD_RING = 0x0400
SCREEN_A, SCREEN_B = 0x4000, 0x4400
PF_ROWS = 21
LANE_X = (9, 16, 23)
COIN_COL = 3
LABEL_ROW = 8
F_STATION, F_BRIDGE = 0x02, 0x80
D_FLAGS, D_COLL, D_ITEM = 0, 6, 9
COIN, MAGNET, TURBO, SLOW, SPRING, HELMET, TICKET = range(1, 8)
KEY_JUMP = 4
DURATIONS = {MAGNET: 500, TURBO: 400, SLOW: 400, SPRING: 500, TICKET: 750}
TIMERS = {MAGNET: "pu_magnet", TURBO: "pu_turbo", SLOW: "pu_slow", SPRING: "pu_spring", TICKET: "pu_ticket"}
TEXTS = mktext64.load_all()


def bcd(data):
    return int("".join(f"{b:02x}" for b in reversed(data)))


class Track:
    def __init__(self, speed=2):
        self.vm = vm = Vice()
        vm.run_frames(2)
        for name, value in (("test_mode", 1), ("test_keys", 0), ("no_crash", 1), ("speed_hi", 0), ("speed_lo", 0)):
            vm.poke(name, value)
        vm.run_frames(1)
        for n in range(64):                      # nothing in the rows made so far
            vm.poke(WORLD_RING + n * 16 + D_COLL, bytes(6))
        self.first = vm.peek16("gen_row") + 1    # rows drawn from here on
        self.speed = speed
        self.plan = {}
        self.cp_gen = vm.checkpoint("gen_done")
        self.cp_frame = vm.checkpoint("frame_done")

    def close(self):
        self.vm.close()

    def ahead(self, k):
        return self.vm.peek16("gen_row") + k

    def plant(self, row, lane, item=0, flags=0):
        assert row > self.vm.peek16("gen_row")
        cells, f = self.plan.get(row, ([0] * 6, 0))
        if item:
            cells[3 + lane] = item
        self.plan[row] = (cells, f | flags)

    def go(self, speed=None):
        self.vm.poke("speed_hi", self.speed if speed is None else speed)

    def _made(self):
        row = self.vm.peek16("gen_row")
        at = WORLD_RING + (row & 63) * 16
        cells, flags = self.plan.get(row, ([0] * 6, 0))
        self.vm.poke(at + D_COLL, bytes(cells))
        old = self.vm.peek8(at + D_FLAGS)
        self.vm.poke(at + D_FLAGS, (old & ~F_STATION & 0xFF) | flags)

    def frame(self, keys=None):
        vm = self.vm
        if keys is not None:
            vm.poke("test_keys", keys)
        while True:
            vm._pending.clear()
            vm.cont()
            while True:
                _, body = vm.wait_event((EV_CHECKPOINT,))
                cid = struct.unpack("<I", body[:4])[0]
                if cid in (self.cp_gen, self.cp_frame):
                    break
            vm.wait_event((EV_STOPPED,))
            if cid == self.cp_gen:
                self._made()
                continue
            if keys is not None:
                vm.poke("test_keys", 0)
            return

    def until_feet(self, row, check=None, limit=1500):
        for _ in range(limit):
            self.frame()
            if check:
                check()
            if self.vm.peek16("feet_row") > row:
                return
        raise AssertionError(f"the runner never got past row {row}")

    def frames(self, n, check=None):
        for _ in range(n):
            self.frame()
            if check:
                check()

    # --- what is shown -------------------------------------------------------
    def shown(self):
        vm = self.vm
        screen = SCREEN_A if vm.peek8("cur_buf") == 0 else SCREEN_B
        return vm.peek16("disp_top"), vm.peek(screen, PF_ROWS * 40)

    def desc(self, row):
        return self.vm.peek(WORLD_RING + (row & 63) * 16, 16)

    def score(self):
        return bcd(self.vm.peek("score", 3))

    def coins(self):
        return bcd(self.vm.peek("coins", 2))

    def distance(self):
        return self.vm.peek16("distance")

    def until(self, cond, limit=1500):
        for _ in range(limit):
            if cond():
                return
            self.frame()
        raise AssertionError("never happened")


class PickupTest(unittest.TestCase):
    def track(self, **kw):
        t = Track(**kw)
        self.addCleanup(t.close)
        return t

    def coin_check(self, t):
        """every coin character shown is a coin in its row, and every coin in a
        row (drawn since the track) is shown"""
        def check():
            top, chars = t.shown()
            ring = t.vm.peek(WORLD_RING, 64 * 16)
            for r in range(PF_ROWS):
                n = top - r
                if n < t.first:
                    continue
                d = ring[(n & 63) * 16:(n & 63) * 16 + 16]
                if d[D_FLAGS] & F_BRIDGE:
                    continue
                for lane in range(3):
                    shown = chars[r * 40 + LANE_X[lane] + COIN_COL] in (COIN_RAIL, COIN_ROOF)
                    self.assertEqual(shown, d[D_ITEM + lane] == COIN,
                                     f"row {n} lane {lane}: coin shown {shown}, item {d[D_ITEM + lane]}")
        return check

    def label_check(self, t, text, row):
        """the label written when world row `row` was at screen row LABEL_ROW"""
        codes = TEXTS["el" if t.vm.peek8("language") else "en"][text]
        first = 9 + (22 - len(codes)) // 2
        top, chars = t.shown()
        r = top - row
        self.assertTrue(0 <= r < PF_ROWS)
        self.assertEqual(list(chars[r * 40 + first:r * 40 + first + len(codes)]), codes,
                         f"{text} at screen row {r}")
        return r

    def test_coin_taken_and_erased(self):
        t = self.track()
        rows = [t.ahead(4), t.ahead(6)]
        for n in rows:
            t.plant(n, 1, COIN)
        t.plant(t.ahead(5), 0, COIN)             # another lane: stays
        t.go()
        t.until_feet(rows[-1] + 2, self.coin_check(t))
        self.assertEqual(t.coins(), 2)
        self.assertEqual(t.score(), t.distance() + 20)
        self.assertEqual(t.desc(rows[0] + 1)[D_ITEM], COIN)

    def test_jump_flies_over_a_coin(self):
        t = self.track()
        n = t.ahead(6)
        t.plant(n, 1, COIN)
        t.go()
        while t.vm.peek16("feet_row") < n - 2:
            t.frame()
        t.frame(KEY_JUMP)
        t.until_feet(n + 1, self.coin_check(t))
        self.assertEqual(t.coins(), 0)
        self.assertEqual(t.desc(n)[D_ITEM + 1], COIN)

    def test_powerup_sprite_label_and_timer(self):
        t = self.track()
        n = t.ahead(5)
        t.plant(n, 1, MAGNET)
        t.go()
        vm = t.vm
        seen = 0
        while vm.peek16("pu_magnet") == 0:
            t.frame()
            if vm.peek8("spr_ena") & 0x40:
                seen += 1
                self.assertEqual(vm.peek8(vm.addr("spr_ptr") + 6),
                                 (vm.addr("sprites") - 0x4000) // 64 + vm.addr("SPR_POWERUPS_MAGNET"))
                self.assertEqual(vm.peek8(vm.addr("spr_x") + 6), 156 + 12)
        self.assertGreater(seen, 10, "the power-up is shown on its way")
        self.assertIn(vm.peek16("pu_magnet"), (499, 500))
        self.assertFalse(vm.peek8("spr_ena") & 0x40, "taken: no sprite")
        label_row = vm.peek16("disp_top") - LABEL_ROW
        self.label_check(t, "pu_magnet", label_row)
        rows_seen = set()
        for _ in range(40):                      # it scrolls down with the world
            t.frame()
            rows_seen.add(self.label_check(t, "pu_magnet", label_row))
        self.assertGreater(len(rows_seen), 5)
        before = vm.peek16("pu_magnet")
        t.frames(10)
        self.assertEqual(vm.peek16("pu_magnet"), before - 10)

    def test_every_powerup(self):
        t = self.track()
        vm = t.vm
        kinds = [TURBO, SLOW, SPRING, HELMET, TICKET]
        rows = [t.ahead(5 + 25 * k) for k in range(len(kinds))]
        for n, kind in zip(rows, kinds):
            t.plant(n, 1, kind)
        coin = rows[-1] + 4
        t.plant(coin, 1, COIN)
        t.go()
        for n, kind in zip(rows, kinds):
            t.until(lambda: vm.peek16("feet_row") >= n and t.desc(n)[D_ITEM + 1] == 0)
            if kind == HELMET:
                self.assertNotEqual(vm.peek8("helmet"), 0)
                continue
            self.assertIn(vm.peek16(TIMERS[kind]), (DURATIONS[kind] - 1, DURATIONS[kind]), TIMERS[kind])
            speed = vm.peek8("eff_hi") * 256 + vm.peek8("eff_lo")
            if kind == TURBO:
                self.assertEqual(speed, 0x300, "turbo: 2.0 + 1.0")
                t.frames(8)
                self.assertGreater(t.score() - t.distance(), 0, "turbo: 2 points a row")
            if kind == SLOW:
                self.assertEqual(speed, 0x100, "slow: half")
                self.assertEqual(vm.peek16("pu_turbo"), 0, "slow ends turbo")
                vm.poke("pu_slow", b"\x02\x00")  # (not 400 frames of slow)
                t.frames(3)
                self.assertEqual(vm.peek16("pu_slow"), 0)
                t.frames(1)
                self.assertEqual(vm.peek8("eff_hi") * 256 + vm.peek8("eff_lo"), 0x200)
            if kind == SPRING:
                t.frame(KEY_JUMP)
                self.assertEqual(vm.peek8("arc_len"), 32, "springs: the long arc")
        coins_score = t.score()
        t.until_feet(coin)
        self.assertEqual(t.coins(), 1)
        self.assertGreaterEqual(t.score() - coins_score, 20, "ticket: 20 a coin")
        self.assertLess(t.score() - coins_score, 30)

    def test_magnet(self):
        t = self.track()
        vm = t.vm
        rows = [t.ahead(8 + 3 * k) for k in range(5)]
        for n in rows:
            for lane in range(3):
                t.plant(n, lane, COIN)
        t.go()
        vm.poke("pu_magnet", b"\x00\x04")
        flying = 0
        check = self.coin_check(t)
        for _ in range(600):
            t.frame()
            check()
            if vm.peek8("spr_ena") & 0x38:
                flying += 1
            if t.vm.peek16("feet_row") > rows[-1] + 4 and not any(vm.peek("fly_on", 3)):
                break
        self.assertEqual(t.coins(), 15, "all three lanes")
        self.assertGreater(flying, 10)

    def test_stations_and_piraeus(self):
        t = self.track()
        vm = t.vm
        a, b = t.ahead(5), t.ahead(30)
        t.plant(a, 0, flags=F_STATION)
        t.plant(b, 0, flags=F_STATION)
        t.go()
        t.until(lambda: vm.peek8("station_next") == 2)
        self.assertEqual(vm.peek8("route_x"), 7, "the HUD's route: on the first station")
        self.label_check(t, "station_1", vm.peek16("disp_top") - LABEL_ROW)
        vm.poke("station_next", 6)
        vm.poke("language", 1)
        extra = t.score() - t.distance()
        t.until(lambda: vm.peek8("station_next") == 1)
        self.assertEqual(vm.peek8("route_x"), 1, "after Piraeus: the route from the start")
        self.label_check(t, "station_6", vm.peek16("disp_top") - LABEL_ROW)
        self.assertEqual(t.score() - t.distance() - extra, 1000)

    def test_score_a_point_a_row(self):
        t = self.track()
        t.go()
        t.frames(200)
        self.assertGreater(t.distance(), 40)
        self.assertEqual(t.score(), t.distance())

    def test_no_frame_lost_with_the_magnet(self):
        t = self.track(speed=4)
        vm = t.vm
        start = t.ahead(3)
        for n in range(start, start + 150):
            for lane in range(3):
                t.plant(n, lane, COIN)
        t.go()
        vm.poke("pu_magnet", b"\xff\x7f")
        vm.poke("pu_turbo", b"\xff\x7f")
        for name in ("overruns", "stalls"):
            vm.poke(name, 0)
        vm.poke("max_load", b"\x00\x00")
        t.until_feet(start + 140)
        self.assertGreater(t.coins(), 140)
        self.assertEqual(vm.peek8("overruns"), 0)
        self.assertEqual(vm.peek8("stalls"), 0)
        load = vm.peek16("max_load")
        print(f"\n  max frame load with the magnet at speed 4: line {load}")
        self.assertLess(load, 312)


if __name__ == "__main__":
    unittest.main()
