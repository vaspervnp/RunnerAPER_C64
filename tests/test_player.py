"""Phase 4: the runner (src/player.asm, src/input.asm).

  - a lane change: 8 frames, 8,8,8,8,6,6,6,6 pixels, on the next lane's centre;
  - jumps: the CPC's arcs, every step 2 frames; the sprite 2 lines up a level;
    the shadow only in the air, on the level left; fast landing;
  - ramps and roofs: up a ramp a level a row, on the roof, down at the end;
  - under a bridge deck the runner is cut away (its pixels, line by line).
"""

import unittest

from vice import Vice
from world_view import W, model_rows

FOOT_Y = 0xC8
LANE_CENTRES = (100, 156, 212)
KEY_LEFT, KEY_RIGHT, KEY_JUMP, KEY_DOWN = 1, 2, 4, 8
BUF_Y = -1
RUNNER_COLOURS = {0, 2, 6, 10}           # outline black, shirt red, jeans blue, skin light red

ARC_GROUND = [1] * 12
ARC_ROOF = [3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 3, 3]


class Runner:
    def __init__(self, speed=2):
        self.vm = Vice()
        vm = self.vm
        vm.run_frames(2)
        vm.poke("test_mode", 1)
        vm.poke("test_keys", 0)
        vm.poke("speed_hi", speed)
        vm.run_frames(2)

    def close(self):
        self.vm.close()

    def tap(self, keys):
        """keys down for one frame, then up."""
        self.vm.poke("test_keys", keys)
        self.vm.run_frames(1)
        self.vm.poke("test_keys", 0)

    def state(self):
        vm = self.vm
        return dict(centre=vm.peek8("player_centre"), lane=vm.peek8("player_lane"), z=vm.peek8("player_z"),
                    base=vm.peek8("player_base"), feet=vm.peek16("feet_row"), support=vm.peek8("support"),
                    spr_y=vm.peek8("spr_y"), ena=vm.peek8("spr_ena"), shadow_y=vm.peek8("spr_y") and vm.peek8(vm.addr("spr_y") + 2))


class MoveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Runner(speed=0)               # the world stands: only the runner moves

    @classmethod
    def tearDownClass(cls):
        cls.r.close()

    def test_lane_change(self):
        r = self.r
        start = r.state()
        self.assertEqual((start["lane"], start["centre"]), (1, LANE_CENTRES[1]))
        r.vm.poke("test_keys", KEY_RIGHT)
        steps = []
        prev = start["centre"]
        for _ in range(9):
            r.vm.run_frames(1)
            r.vm.poke("test_keys", 0)
            c = r.state()["centre"]
            steps.append(c - prev)
            prev = c
        self.assertEqual(steps, [8, 8, 8, 8, 6, 6, 6, 6, 0])
        self.assertEqual(r.state()["lane"], 2)
        self.assertEqual(r.state()["centre"], LANE_CENTRES[2])
        r.tap(KEY_RIGHT)                      # off the track: stays
        r.vm.run_frames(9)
        self.assertEqual(r.state()["centre"], LANE_CENTRES[2])
        r.tap(KEY_LEFT)
        r.vm.run_frames(9)
        self.assertEqual((r.state()["lane"], r.state()["centre"]), (1, LANE_CENTRES[1]))

    def jump(self, keys_during=None):
        r = self.r
        r.vm.poke("test_keys", KEY_JUMP)
        zs, ys, shadows = [], [], []
        for k in range(40):
            r.vm.run_frames(1)
            r.vm.poke("test_keys", keys_during(k) if keys_during else 0)
            s = r.state()
            zs.append(s["z"])
            ys.append(s["spr_y"])
            shadows.append(s["ena"] & 4)
            if s["z"] == s["base"] and k > 2:
                break
        return zs, ys, shadows

    def test_jump_from_the_ground(self):
        self.r.vm.poke("player_base", 0)
        zs, ys, shadows = self.jump()
        want = [z for z in ARC_GROUND for _ in (0, 1)] + [0]
        self.assertEqual(zs, want)
        for z, y in zip(zs, ys):
            self.assertEqual(y, FOOT_Y - 20 - 2 * z)
        self.assertTrue(all(shadows[:-1]) and not shadows[-1], "the shadow is shown in the air only")

    def test_jump_from_a_roof(self):
        self.r.vm.poke("player_base", 2)       # (no world under it: the stand still keeps it)
        self.r.vm.poke("speed_hi", 0)
        zs, _, _ = self.jump()
        self.r.vm.poke("player_base", 0)
        self.assertEqual(zs[:24], [z for z in ARC_ROOF for _ in (0, 1)])

    def test_fast_landing(self):
        self.r.vm.poke("player_base", 0)
        zs, _, _ = self.jump(lambda k: KEY_DOWN if k == 3 else 0)
        # down pressed on the 5th frame: on to the last 2 steps (4 frames) of the arc
        self.assertEqual(zs, [1] * 4 + [1] * 4 + [0])

    def test_fall_off_a_roof(self):
        """On a roof (base 2) over plain rail: a fall, z 2 then 1 for 2 steps."""
        r = self.r
        r.vm.poke("player_base", 2)
        r.vm.poke("player_z", 2)
        zs = []
        for _ in range(7):
            r.vm.run_frames(1)
            zs.append(r.state()["z"])
        self.assertEqual(zs, [2, 1, 1, 1, 1, 0, 0])
        self.assertEqual(r.state()["base"], 0)


class RampTest(unittest.TestCase):
    def test_up_the_ramp_onto_the_roof_and_down(self):
        rows = model_rows(700, 0)
        ramp = next(n for n, d in enumerate(rows) if d[W.D_COLL + 1] == W.COL_RAMP_UP)  # row 0 of a ramp, lane 1
        r = Runner(speed=2)
        self.addCleanup(r.close)
        vm = r.vm
        seen = {}
        while True:
            vm.run_frames(1)
            s = r.state()
            if s["feet"] >= ramp - 1 and s["z"] == s["base"]:
                seen.setdefault(s["feet"], s["base"])
            if s["feet"] > ramp + 60:
                break
        self.assertEqual([seen[ramp], seen[ramp + 1], seen[ramp + 2]], [0, 1, 2], "a level a ramp row")
        on_train = [n for n in range(ramp + 3, ramp + 60)
                    if rows[n][W.D_COLL + 1] & 15 in (W.COL_TRAIN, W.COL_GAP) and n in seen]
        self.assertTrue(on_train)
        self.assertTrue(all(seen[n] == 2 for n in on_train), "on the roof all along the train")
        after = [n for n in range(ramp + 3, ramp + 60) if rows[n][W.D_COLL + 1] & 15 == W.COL_NONE and n in seen]
        self.assertTrue(after and all(seen[n] == 0 for n in after[3:]), "back on the ground after it")


class BridgeTest(unittest.TestCase):
    def test_cut_under_the_deck(self):
        rows = model_rows(400, 0)
        decks = [n for n, d in enumerate(rows) if d[W.D_FLAGS] & W.F_BRIDGE
                 and d[W.D_LEFT] not in (W.B["footbridge_shadow"], W.B["roadbridge_shadow"])]
        r = Runner(speed=1)
        self.addCleanup(r.close)
        vm = r.vm
        checked = 0
        for _ in range(4000):
            vm.run_to("irq_top_done")
            top, y = vm.peek16("disp_top"), vm.peek8(0xD011) & 7
            line = lambda n: 0x30 + y + 8 * (top - n)          # first line of world row n
            runner_top = vm.peek8(0xD001)
            deck_lines = {l for n in decks for l in range(line(n), line(n) + 8)} & set(range(runner_top, FOOT_Y + 1))
            if len(deck_lines) < 6 or len(deck_lines) > 14:
                continue
            vm.poke("speed_hi", 0)                             # stand still: the same picture twice
            vm.run_to("irq_top_done")
            vm.run_to("irq_top_done")
            dw, dh, xo, yo, iw, ih, px = vm.display()
            x0 = xo + vm.peek8(0xD000) - 24
            for l in range(runner_top, FOOT_Y + 1):
                row = px[(l + BUF_Y) * dw + x0:(l + BUF_Y) * dw + x0 + 24]
                found = set(row) & RUNNER_COLOURS
                if l in deck_lines:
                    self.assertFalse(found, f"runner pixels on deck line ${l:02X}")
            visible = [l for l in range(runner_top, FOOT_Y + 1) if l not in deck_lines and
                       set(px[(l + BUF_Y) * dw + x0:(l + BUF_Y) * dw + x0 + 24]) & RUNNER_COLOURS]
            self.assertTrue(visible, "the rest of the runner is drawn")
            checked += 1
            vm.poke("speed_hi", 1)
            if checked >= 3:
                break
        self.assertGreaterEqual(checked, 3, "no deck over the runner was seen")


class LoadTest(unittest.TestCase):
    def test_no_frame_lost_with_the_runner(self):
        r = Runner(speed=4)
        self.addCleanup(r.close)
        vm = r.vm
        for name in ("overruns", "stalls"):
            vm.poke(name, 0)
        vm.poke("max_load", b"\x00\x00")
        for k in range(30):                    # jumps and lane changes while scrolling fast
            r.tap(KEY_JUMP if k % 3 == 0 else KEY_LEFT if k % 3 == 1 else KEY_RIGHT)
            vm.run_frames(20)
        self.assertEqual(vm.peek8("overruns"), 0)
        self.assertEqual(vm.peek8("stalls"), 0)
        load = vm.peek16("max_load")
        print(f"\n  max frame load with the runner: line {load}")
        self.assertLess(load, 312)


if __name__ == "__main__":
    unittest.main()
