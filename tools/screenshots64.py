"""Takes the release screenshots (docs/screenshots/*.png) from headless VICE.

    python3 tools/screenshots64.py        (after make; make screenshots)

Each picture is the whole frame the VIC-II drew (taken at the end of the
split IRQ, the HUD set), with a border around the 320 x 200 screen, pixels
doubled. Power-ups and coins are planted as the tests do (tests/test_pickups).
"""

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import c64palette  # noqa: E402
from test_pickups import COIN, D_COLL, MAGNET, TURBO, Track  # noqa: E402
from test_screens import KEY_DOWN, KEY_FIRE, KEY_UP, Flow  # noqa: E402
from vice import Vice  # noqa: E402

OUT = os.path.join(ROOT, "docs", "screenshots")
F_FOREST = 0x01
COL_SIGNAL = 2


def grab(vm, name, track=None):
    """the next whole frame -> OUT/name"""
    if track:                                    # (its checkpoints stop VICE elsewhere)
        vm.delete_checkpoint(track.cp_gen)
        vm.delete_checkpoint(track.cp_frame)
    vm.run_to("irq_split_end")
    vm.run_to("irq_split_end")
    if track:
        track.cp_gen = vm.checkpoint("gen_done")
        track.cp_frame = vm.checkpoint("frame_done")
    dw, dh, xo, yo, iw, ih, px = vm.display()
    rows = len(px) // dw
    im = Image.frombytes("P", (dw, rows), bytes(px[:rows * dw]))
    im.putpalette(c64palette.flat_palette())
    im = im.crop((xo - 32, yo - 35, xo + 352, yo + 235)).convert("RGB")
    im = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    im.save(os.path.join(OUT, name))
    print(f"screenshots {name}")


def logo():
    """the logo as the C64 draws it (rows 0-5, columns 2-37 of the menu, YSCROLL 7:
    4 lines below the screen's top) -> docs/cover/logo.png"""
    menu = Image.open(os.path.join(OUT, "01_menu.png"))
    x0, y0 = 2 * (32 + 16), 2 * (35 + 4)
    menu.crop((x0, y0, x0 + 2 * 288, y0 + 2 * 48)).save(os.path.join(ROOT, "docs", "cover", "logo.png"))
    print("screenshots logo.png")


def screens():
    f = Flow()
    vm = f.vm
    try:
        f.frames(10)
        grab(vm, "01_menu.png")
        logo()
        vm.poke("language", 1)
        vm.poke("screen_dirty", 1)
        f.frames(3)
        grab(vm, "02_menu_greek.png")
        vm.poke("language", 0)
        for _ in range(3):
            f.tap(KEY_DOWN)
        f.tap(KEY_FIRE)
        grab(vm, "03_story.png")
        f.tap(KEY_FIRE)
        f.tap(KEY_UP)
        f.tap(KEY_UP)
        f.tap(KEY_FIRE)
        grab(vm, "04_controls.png")
        f.tap(KEY_FIRE)
        f.tap(KEY_UP)
        vm.poke("skill", 2)                      # hard: the hint, then 3
        f.tap(KEY_FIRE, after=110)               # (the hint, and 3 on the track)
        grab(vm, "08_hard_countdown.png")
        vm.poke("countdown", 1)                  # to the game over, with a record
        f.frames(300)
        vm.poke("score", bytes([0x50, 0x47, 0x03]))
        vm.poke("coins", bytes([0x86, 0x01]))
        vm.poke("game_state", 2)
        vm.poke("state_timer", 2)
        f.frames(4)
        for key in (KEY_UP, KEY_UP, KEY_FIRE, KEY_DOWN, KEY_FIRE):
            f.tap(key)
        grab(vm, "09_game_over.png")
        f.tap(KEY_FIRE)
        f.tap(KEY_FIRE)
        grab(vm, "10_high_scores.png")
    finally:
        f.close()


def city_and_forest():
    vm = Vice()
    try:
        vm.run_frames(2)
        vm.poke("test_mode", 1)
        vm.poke("test_keys", 0)
        vm.poke("no_crash", 1)
        vm.poke("speed_hi", 2)
        vm.run_frames(200)
        grab(vm, "05_city.png")
        vm.poke("speed_hi", 4)
        for _ in range(400):                     # until the whole picture is forest
            vm.run_frames(10)
            top = vm.peek16("disp_top")
            ring = vm.peek(0x0400, 64 * 16)
            if all(ring[((top - r) & 63) * 16] & F_FOREST for r in range(21)):
                break
        vm.poke("speed_hi", 2)
        vm.run_frames(30)
        grab(vm, "06_forest.png")
    finally:
        vm.close()


def signal():
    """a signal on the runner's track (the middle one), a little ahead"""
    vm = Vice()
    try:
        vm.run_frames(2)
        for name, value in (("test_mode", 1), ("test_keys", 0), ("no_crash", 1), ("speed_hi", 2)):
            vm.poke(name, value)
        for _ in range(5000):
            vm.run_frames(2)
            top = vm.peek16("disp_top")
            ring = vm.peek(0x0400, 64 * 16)
            if any(ring[((top - r) & 63) * 16 + D_COLL + 1] == COL_SIGNAL for r in (8, 9)):
                break
        vm.poke("speed_hi", 0)
        grab(vm, "11_signal.png")
    finally:
        vm.close()


def power_up():
    t = Track()
    vm = t.vm
    try:
        a = t.ahead(4)
        t.plant(a, 1, TURBO)
        for k in range(6):
            for lane in range(3):
                t.plant(a + 14 + 3 * k, lane, COIN)
        t.plant(a + 9, 2, MAGNET)
        t.go()
        vm.poke("pu_magnet", b"\x00\x04")
        t.until(lambda: vm.peek16("pu_turbo") != 0)
        t.until(lambda: vm.peek8("spr_ena") & 0x38)
        t.frames(2)
        grab(vm, "07_power_up.png", track=t)
    finally:
        t.close()


def main():
    os.makedirs(OUT, exist_ok=True)
    screens()
    city_and_forest()
    signal()
    power_up()


if __name__ == "__main__":
    main()
