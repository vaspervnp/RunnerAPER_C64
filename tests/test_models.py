"""Phase 10: other C64s (VICE models).

  - C64C (8565 VIC-II, 8580 SID) and the first VIC-II (6569R1): the modules
    that hang on raster timing and the SID run again there (boot, scroll
    with its split and pixel checks, the runner's deck clipping, sound);
  - NTSC (the game is PAL-only): it boots and plays, nothing more.
"""

import os
import subprocess
import sys
import unittest

from vice import Vice

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ("test_boot", "test_scroll", "test_player", "test_sound")


class ModelsTest(unittest.TestCase):
    def run_on(self, model, args):
        env = dict(os.environ, VICE_ARGS=args)
        out = subprocess.run([sys.executable, os.path.join(HERE, "run_tests.py"), *MODULES],
                             env=env, cwd=HERE, capture_output=True, text=True, timeout=1200)
        last = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
        print(f"\n  {model}: {last}")
        self.assertEqual(out.returncode, 0, out.stdout[-3000:] + out.stderr[-2000:])

    def test_c64c(self):
        self.run_on("c64c", "-model c64c")

    def test_6569r1(self):
        """the first VIC-II (-model c64old wants KERNAL rev. 2: only the chip here)"""
        self.run_on("6569r1", "-VICIImodel 6569r1")

    def test_ntsc_runs(self):
        os.environ["VICE_ARGS"] = "-model ntsc"
        try:
            vm = Vice()
        finally:
            del os.environ["VICE_ARGS"]
        try:
            vm.run_frames(2)
            vm.poke("speed_hi", 2)
            vm.poke("no_crash", 1)
            before, top = vm.peek16("frame_counter"), vm.peek16("disp_top")
            vm.run_frames(300)
            print(f"\n  ntsc: {vm.peek16('frame_counter') - before} frames, "
                  f"{vm.peek8('overruns')} overruns, {vm.peek16('disp_top') - top} rows")
            self.assertEqual(vm.peek8("game_mode"), 0)
            self.assertGreater(vm.peek16("disp_top") - top, 50, "the world moves")
        finally:
            vm.close()


if __name__ == "__main__":
    unittest.main()
