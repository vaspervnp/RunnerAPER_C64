"""Phase 5: obstacles and collisions (the CPC's tools/tests/test_collisions.py).

Each scenario stops the scroll, clears every collision class and item in
the world ring and plants its own obstacles a few rows ahead of the runner;
rows made later are cleared too, so nothing else gets in the way. The drawn
tiles do not change: collisions only read the descriptors.
"""

import unittest

from vice import Vice

COL_NONE, COL_STOP, COL_SIGNAL, COL_TRAIN, COL_NOSE, COL_RAMP_UP, COL_RAMP_DOWN, COL_GAP = range(8)
STATE_RUN, STATE_CRASHED, STATE_GAME_OVER = range(3)
MODE_OVER = 5
KEY_LEFT, KEY_RIGHT, KEY_JUMP, KEY_DOWN = 1, 2, 4, 8
WORLD_RING = 0x0400
AHEAD = 6                       # rows below the top of the screen where planting starts
LANE_CENTRES = (100, 156, 212)


class Scenario:
    def __init__(self, speed=2, hard=False):
        self.vm = Vice()
        vm = self.vm
        vm.run_frames(2)
        vm.poke("test_mode", 1)
        vm.poke("test_keys", 0)
        vm.poke("gap_hard", 1 if hard else 0)
        self.speed = speed
        vm.poke("speed_hi", 0)
        vm.run_frames(3)
        self.plan = {}
        self.applied = set()
        self.top = vm.peek16("disp_top")
        self.base_row = self.top - AHEAD
        self.clear_until = self.top + 80
        self._apply()

    def close(self):
        self.vm.close()

    def _apply(self):
        top = self.vm.peek16("disp_top")
        for row in range(top - 60, top + 1):
            if row in self.applied or row > self.clear_until:
                continue
            cells = self.plan.get(row, [COL_NONE] * 3 + [0] * 3)
            self.vm.poke(WORLD_RING + (row & 63) * 16 + 6, bytes(cells))
            self.applied.add(row)

    def plant_lane(self, offset, lane, classes):
        """classes bottom to top, from `offset` rows above base_row"""
        for k, cls in enumerate(classes):
            row = self.base_row + offset + k
            self.plan.setdefault(row, [COL_NONE] * 3 + [0] * 3)[lane] = cls
            self.applied.discard(row)
        self._apply()

    def go(self):
        self.vm.poke("speed_hi", self.speed)

    def frame(self):
        self.vm.run_frames(1)
        self._apply()
        return self.state()

    def state(self):
        vm = self.vm
        return {"state": vm.peek8("game_state"), "lives": vm.peek8("lives"), "crashes": vm.peek8("crashes"),
                "base": vm.peek8("player_base"), "z": vm.peek8("player_z"), "lane": vm.peek8("player_lane"),
                "centre": vm.peek8("player_centre"), "front": vm.peek16("front_row"),
                "feet": vm.peek16("feet_row"), "top": vm.peek16("disp_top"), "invuln": vm.peek8("invuln")}

    def until_front(self, row, limit=400):
        for _ in range(limit):
            st = self.frame()
            if st["front"] >= row:
                return st
        raise AssertionError(f"front probe never reached row {row}")

    def run(self, frames):
        return [self.frame() for _ in range(frames)]

    def tap(self, key):
        self.vm.poke("test_keys", key)
        st = self.frame()
        self.vm.poke("test_keys", 0)
        return st

    def past(self, row, limit=600):
        states = []
        for _ in range(limit):
            states.append(self.frame())
            if states[-1]["feet"] > row and states[-1]["state"] == STATE_RUN:
                return states
        raise AssertionError(f"runner never got past row {row}")


def stop():
    return [COL_STOP, COL_STOP]


def ramp_up():
    return [COL_RAMP_UP | (k << 4) for k in range(3)]


def ramp_down():
    return [COL_RAMP_DOWN | (k << 4) for k in range(3)]


class CollisionTest(unittest.TestCase):
    def scenario(self, **kw):
        sc = Scenario(**kw)
        self.addCleanup(sc.close)
        return sc

    def test_stop_crashes_and_the_world_waits(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, stop())
        sc.go()
        sc.until_front(sc.base_row)
        states = sc.run(6)
        self.assertEqual((states[-1]["state"], states[-1]["lives"], states[-1]["crashes"]), (STATE_CRASHED, 2, 1))
        top = states[-1]["top"]
        self.assertTrue(all(s["top"] == top for s in sc.run(40)), "the world stops while crashed")
        states = sc.run(60)
        self.assertEqual(states[-1]["state"], STATE_RUN)
        self.assertGreater(states[-1]["invuln"], 0)

    def test_jump_clears_a_stop(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, stop())
        sc.go()
        sc.until_front(sc.base_row - 1)
        sc.tap(KEY_JUMP)
        states = sc.past(sc.base_row + 1)
        self.assertTrue(all(s["crashes"] == 0 for s in states))
        self.assertTrue(any(s["z"] == 1 for s in states))

    def test_ramp_lifts_onto_the_roof_and_back_down(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, ramp_up() + [COL_TRAIN] * 8 + ramp_down())
        sc.go()
        states = sc.past(sc.base_row + 14)
        bases = [s["base"] for s in states]
        self.assertTrue(all(s["crashes"] == 0 for s in states), bases)
        steps = [b for i, b in enumerate(bases) if i == 0 or b != bases[i - 1]]
        self.assertEqual(steps, [0, 1, 2, 1, 0])

    def test_train_end_without_ramp_drops_to_the_ground(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, ramp_up() + [COL_TRAIN] * 6)
        sc.go()
        states = sc.past(sc.base_row + 12)
        bases = [s["base"] for s in states]
        self.assertTrue(all(s["crashes"] == 0 for s in states))
        self.assertTrue(2 in bases and bases[-1] == 0)
        after = [s["z"] for s in states[bases.index(2):]]
        self.assertIn(1, after[after.index(2):], "a short fall is shown")

    def test_train_without_ramp_crashes(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, [COL_NOSE] + [COL_TRAIN] * 6)
        sc.go()
        sc.until_front(sc.base_row)
        self.assertEqual(sc.run(4)[-1]["crashes"], 1)

    def test_ground_jump_cannot_land_on_a_train(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, [COL_TRAIN] * 10)
        sc.go()
        sc.until_front(sc.base_row - 1)
        sc.tap(KEY_JUMP)
        self.assertTrue(any(s["crashes"] == 1 for s in sc.run(40)))

    def test_signal_is_red(self):
        """The C64's signals stay red: only a jump from a roof (z 3) clears one."""
        sc = self.scenario()
        sc.plant_lane(0, 1, [COL_NONE, COL_SIGNAL])
        sc.go()
        sc.until_front(sc.base_row + 1)
        self.assertEqual(sc.run(6)[-1]["crashes"], 1)

    def test_roof_jump_clears_the_signal(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, ramp_up() + [COL_TRAIN] * 8)
        sc.plant_lane(13, 1, [COL_NONE, COL_SIGNAL])      # just past the train
        sc.go()
        for _ in range(600):
            st = sc.frame()
            if st["base"] == 2 and st["front"] >= sc.base_row + 9:
                break
        sc.tap(KEY_JUMP)
        states = sc.past(sc.base_row + 15)
        self.assertTrue(all(s["crashes"] == 0 for s in states), [(s["z"], s["front"]) for s in states])

    def test_lane_change_into_a_train_crashes(self):
        sc = self.scenario()
        sc.plant_lane(0, 2, [COL_TRAIN] * 20)
        sc.go()
        sc.until_front(sc.base_row + 5)
        sc.tap(KEY_RIGHT)
        states = sc.run(10)
        self.assertEqual(states[-1]["crashes"], 1)
        for st in states + sc.run(120):              # thrown back to the lane it came from
            if st["crashes"]:
                self.assertEqual((st["lane"], st["centre"]), (1, LANE_CENTRES[1]))
        sc.tap(KEY_LEFT)                              # lane changes work as before
        sc.run(10)
        self.assertEqual((sc.state()["lane"], sc.state()["centre"]), (0, LANE_CENTRES[0]))

    def test_roof_hop_between_parallel_trains(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, ramp_up() + [COL_TRAIN] * 16)
        sc.plant_lane(3, 2, [COL_TRAIN] * 16)
        sc.go()
        for _ in range(600):
            st = sc.frame()
            if st["base"] == 2 and st["feet"] >= sc.base_row + 6:
                break
        sc.tap(KEY_RIGHT)
        states = sc.run(12)
        self.assertEqual((states[-1]["lane"], states[-1]["base"], states[-1]["crashes"]), (2, 2, 0))

    def test_protected_after_a_crash(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, stop())
        sc.plant_lane(3, 1, stop())                   # right behind the first one
        sc.go()
        states = sc.past(sc.base_row + 6, limit=800)
        self.assertEqual(states[-1]["crashes"], 1)

    def test_blinking_while_protected(self):
        sc = self.scenario()
        sc.plant_lane(0, 1, stop())
        sc.go()
        sc.until_front(sc.base_row)
        sc.run(90)                                    # crash over, protected now
        shown = []
        for _ in range(24):
            sc.frame()
            shown.append(sc.vm.peek8("spr_ena") & 3)
        self.assertEqual(sc.state()["state"], STATE_RUN)
        self.assertIn(0, shown)
        self.assertIn(3, shown)

    def test_helmet_takes_a_crash(self):
        sc = self.scenario()
        sc.vm.poke("helmet", 1)
        sc.plant_lane(0, 1, stop())
        sc.go()
        states = sc.past(sc.base_row + 2)
        self.assertTrue(all(s["crashes"] == 0 and s["state"] == STATE_RUN for s in states))
        self.assertEqual(sc.vm.peek8("helmet"), 0)

    def test_game_over_then_the_score_screen(self):
        sc = self.scenario()
        sc.vm.poke("lives", 1)
        sc.plant_lane(0, 1, stop())
        sc.go()
        sc.until_front(sc.base_row)
        states = sc.run(100)
        self.assertTrue(any(s["state"] == STATE_GAME_OVER for s in states))
        sc.run(180)
        self.assertEqual(sc.vm.peek8("game_mode"), MODE_OVER, "the game over screen")

    def wagons(self, hard, jump):
        """Up a ramp onto two wagons joined by a coupler (row 3 + 12)."""
        sc = self.scenario(hard=hard)
        sc.plant_lane(0, 1, ramp_up() + [COL_TRAIN] * 12 + [COL_GAP] + [COL_TRAIN] * 12)
        sc.go()
        if jump:                                      # jump from the roof just before the gap
            for _ in range(600):
                st = sc.frame()
                if st["base"] == 2 and st["feet"] >= sc.base_row + 3 + 12 - 2:
                    break
            sc.tap(KEY_JUMP)
        return sc.past(sc.base_row + 3 + 20, limit=900)

    def test_gap_between_wagons_is_a_roof_except_on_hard(self):
        states = self.wagons(hard=False, jump=False)
        self.assertEqual((states[-1]["crashes"], states[-1]["base"]), (0, 2))
        states = self.wagons(hard=True, jump=False)
        self.assertEqual(states[-1]["crashes"], 1, "walked into the gap")

    def test_hard_jump_over_the_gap(self):
        states = self.wagons(hard=True, jump=True)
        self.assertEqual((states[-1]["crashes"], states[-1]["base"]), (0, 2))


if __name__ == "__main__":
    unittest.main()
