"""The C64's chunks (tools/mklevel64.py c64_rows) against the CPC's own:

  - wagons 50 % longer, nothing else (stops, signals, ramps, couplers,
    ends, noses) bigger;
  - coins never in all 3 lanes of a row, often in 2;
  - coins only on plain rail or a train's roof (never a coupler);
  - a train reached by a ramp has coins along all of its roof;
  - power-ups still turn up on the roofs (the model of the generator).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import mklevel64 as L  # noqa: E402
import worldgen as W  # noqa: E402

V = L.VIRTUAL_TILES
C64 = L.load_all(c64=True)
CPC = {c["name"]: c for c in L.load_all(c64=False)}
SINGLE = ("stop_", "signal_", "ramp_", "_coupler", "_end_bottom", "_end_top", "_nose")


def column(chunk, lane):
    return [(V[row[lane * 3]], row[lane * 3 + 1] & 15, row[lane * 3 + 2]) for row in chunk["rows"]]


class ChunkTest(unittest.TestCase):
    def test_wagons_longer(self):
        lengths = []
        for chunk in C64:
            for lane in range(3):
                col = column(chunk, lane)
                for name in {n for n, _, _ in col if any(k in n for k in SINGLE)}:
                    runs = [len(list(g)) for k, g in __import__("itertools").groupby(n for n, _, _ in col) if k == name]
                    self.assertTrue(all(r == 1 for r in runs), f"{chunk['name']}: {name} doubled")
                start = None
                for r, (name, _, _) in enumerate(col):
                    if name.endswith("_end_bottom"):
                        start = r
                    elif name.endswith("_end_top") and start is not None:
                        lengths.append(r - start + 1)
                        start = None
        print(f"\n  wagons: {len(lengths)}, {sum(l == 18 for l in lengths)} of 18 rows, {min(lengths)}-{max(lengths)}")
        self.assertGreater(sum(l >= 16 for l in lengths), 0.9 * len(lengths))

    def test_coins_in_one_or_two_lanes(self):
        lanes = [0, 0, 0, 0]
        for chunk in C64:
            for row in chunk["rows"]:
                lanes[sum(row[k * 3 + 2] == 1 for k in range(3))] += 1
        print(f"\n  rows with coins in 1 / 2 / 3 lanes: {lanes[1]} / {lanes[2]} / {lanes[3]}")
        self.assertEqual(lanes[3], 0, "never all three lanes")
        self.assertGreater(lanes[2], 100, "coins side by side")

    def test_coins_on_rail_or_roof(self):
        for chunk in C64:
            for lane in range(3):
                for r, (name, coll, item) in enumerate(column(chunk, lane)):
                    if item == 1:
                        self.assertIn(coll, (L.COL_NONE, L.COL_TRAIN), f"{chunk['name']} row {r}: {name}")
                        self.assertFalse(name.startswith(("stop", "signal", "ramp")), f"{chunk['name']} row {r}")

    def test_ramp_trains_coins_all_along(self):
        for chunk in C64:
            for lane in range(3):
                col = column(chunk, lane)
                if not any(n.startswith("ramp_up") for n, _, _ in col):
                    continue
                train = [r for r, (_, coll, _) in enumerate(col) if coll in (L.COL_TRAIN, L.COL_NOSE, L.COL_GAP)]
                coins = [r for r in train if col[r][2] == 1]
                with self.subTest(chunk=chunk["name"]):
                    self.assertLessEqual(coins[0] - train[0], 2, "from the start of the roof")
                    self.assertLessEqual(train[-1] - coins[-1], 4, "to its end")
                    self.assertLessEqual(max(b - a for a, b in zip(coins, coins[1:])), 6, "no long stretch without")

    def test_power_ups_on_roofs(self):
        for skill in (0, 2):
            w = W.World(skill)
            roof = 0
            for n in range(15000):
                d = w.generate(n)
                roof += sum(1 for k in range(3) if d[W.D_ITEM + k] >= 2 and d[W.D_COLL + k] & 15 == W.COL_TRAIN)
            with self.subTest(skill=skill):
                self.assertGreater(roof, 25, "power-ups on roofs (the CPC: about 40 in 15000 rows)")


if __name__ == "__main__":
    unittest.main()
