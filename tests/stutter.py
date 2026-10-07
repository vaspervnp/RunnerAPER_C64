"""Long runs for the frame budget: a game per skill and seed, played by
random keys (a key every 16 frames, obstacles never crash: the world never
stops), then the frames lost (overruns), the stalls of the hidden screen and
the heaviest frame (the raster line where the main loop ended).

    python3 tests/stutter.py [minutes] [seeds]      (default 10 minutes, 3 seeds)

Every run is a VICE of its own, all of them at once. tests/test_stutter.py
runs a short version with the other tests.
"""

import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vice import Vice  # noqa: E402

KEYS = (0, 0, 1, 2, 4, 4, 8)            # none, left, right, jump, down
STEP = 16
SKILLS = ("easy", "medium", "hard")


def run(skill, seed, frames):
    vm = Vice()
    try:
        vm.run_frames(1)
        vm.poke("skill", skill)
        vm.poke("restart", 1)
        vm.run_frames(1)
        hi = vm.peek8(vm.addr("skill_speeds") + skill)
        lo = vm.peek8(vm.addr("skill_speeds_lo") + skill)
        vm.poke("speed_hi", hi)
        vm.poke("speed_lo", lo)
        vm.poke("rng", (0xACE1 + seed * 0x1234 & 0xFFFF or 1).to_bytes(2, "little"))
        for name, value in (("test_mode", 1), ("test_keys", 0), ("no_crash", 1), ("overruns", 0), ("stalls", 0)):
            vm.poke(name, value)
        vm.poke("max_load", b"\x00\x00")
        rnd = random.Random(seed * 3 + skill)
        for _ in range(frames // STEP):
            vm.poke("test_keys", rnd.choice(KEYS))
            vm.run_frames(1)
            vm.poke("test_keys", 0)
            vm.run_frames(STEP - 1)
        return {"skill": SKILLS[skill], "seed": seed, "frames": frames,
                "overruns": vm.peek8("overruns"), "stalls": vm.peek8("stalls"),
                "max_load": vm.peek16("max_load"), "rows": vm.peek16("distance"),
                "game_mode": vm.peek8("game_mode")}
    finally:
        vm.close()


def run_all(minutes, seeds, workers=None):
    frames = int(minutes * 60 * 50)
    jobs = [(skill, seed) for skill in range(3) for seed in range(seeds)]
    with ThreadPoolExecutor(max_workers=workers or len(jobs)) as pool:
        return list(pool.map(lambda j: run(j[0], j[1], frames), jobs))


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    results = run_all(minutes, seeds)
    bad = 0
    for r in results:
        ok = r["overruns"] == 0 and r["stalls"] == 0 and r["max_load"] < 312 and r["game_mode"] == 0
        bad += not ok
        print(f"{r['skill']:6s} seed {r['seed']}: {r['frames']} frames, {r['rows']} rows, "
              f"overruns {r['overruns']}, stalls {r['stalls']}, max load line {r['max_load']}"
              f"{'' if ok else '  <-- FAIL'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
