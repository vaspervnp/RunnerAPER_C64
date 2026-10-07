"""Phase 10: the frame budget over a minute of play on every skill (random
keys, no crashes). tests/stutter.py runs the long version (10 minutes x 3
skills x 3 seeds)."""

import unittest

from stutter import run_all


class StutterTest(unittest.TestCase):
    def test_a_minute_on_every_skill(self):
        for r in run_all(minutes=1, seeds=1):
            with self.subTest(skill=r["skill"]):
                print(f"\n  {r['skill']}: {r['rows']} rows, max load line {r['max_load']}")
                self.assertEqual(r["overruns"], 0)
                self.assertEqual(r["stalls"], 0)
                self.assertLess(r["max_load"], 312)
                self.assertEqual(r["game_mode"], 0, "still playing")


if __name__ == "__main__":
    unittest.main()
