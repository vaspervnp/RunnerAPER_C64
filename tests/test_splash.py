"""The boot file (src/boot.asm): RUNNER, first on the disk.

  - the REVIVE8BIT screen: VIC bank 3, multicolor bitmap, the bitmap, the
    matrix and the colour RAM as tools/mksplash64.py made them;
  - 500 frames (10 s) with no key, then the game loads; SPACE stops the
    wait at once;
  - the game (APER) loads with the screen still showing, byte for byte as
    build/runner.prg, and starts: the menu.

The disk is the .d64 of make, through VICE's virtual drive (fast).
"""

import os
import struct
import unittest

from vice import BUILD, EV_CHECKPOINT, EV_STOPPED, PRG, Vice, load_labels

D64 = os.path.join(BUILD, "runner.d64")
B = load_labels(os.path.join(BUILD, "boot_labels.txt"))
with open(os.path.join(os.path.dirname(BUILD), "src", "data", "splash.bin"), "rb") as _f:
    SPLASH = _f.read()
DISK = ["-drive8type", "1541", "-8", D64, "+drive8truedrive", "-virtualdev8"]
FRAMES = 500
SPACE_ROW = 0x10


def boot_disk():
    return Vice(image=D64, play=False, extra_args=DISK, boot_timeout=60)


def frames_until_go(vm, press_at=None):
    """frames of the wait before `go`; press_at: SPACE read on that frame"""
    wait = vm.checkpoint(B["key_read"])
    go = vm.checkpoint(B["go"])
    frames = 0
    try:
        while True:
            vm._pending.clear()
            vm.cont()
            _, body = vm.wait_event((EV_CHECKPOINT,), 120)
            cid = struct.unpack("<I", body[:4])[0]
            vm.wait_event((EV_STOPPED,), 120)
            if cid == go:
                return frames
            frames += 1
            if frames == press_at:
                vm.set_register("A", 0xFF & ~SPACE_ROW)
    finally:
        vm.delete_checkpoint(wait)
        vm.delete_checkpoint(go)


class SplashTest(unittest.TestCase):
    def vm(self):
        vm = boot_disk()
        self.addCleanup(vm.close)
        return vm

    def check_splash(self, vm):
        self.assertEqual(vm.peek8(0xDD00) & 3, 0, "VIC bank 3")
        self.assertEqual(vm.peek8(0xD011) & 0x70, 0x30, "bitmap, screen on")
        self.assertEqual(vm.peek8(0xD016) & 0x10, 0x10, "multicolor")
        self.assertEqual(vm.peek8(0xD018) & 0xF8, 0x38, "matrix $cc00, bitmap $e000")
        self.assertEqual(vm.peek8(0xD021) & 15, 0, "black")
        self.assertEqual(vm.peek(0xE000, 8000, bank="ram"), SPLASH[:8000], "the bitmap")
        self.assertEqual(vm.peek(0xCC00, 1000), SPLASH[8000:9000], "the matrix")
        cram = bytes(c & 15 for c in vm.peek(0xD800, 1000))
        self.assertEqual(cram, SPLASH[9000:], "the colour RAM")

    def test_splash_ten_seconds_then_the_game(self):
        vm = self.vm()
        vm.run_to(B["key_read"], timeout=120)
        self.check_splash(vm)
        self.assertEqual(frames_until_go(vm), FRAMES - 1, "10 s (the first frame was above)")
        vm.run_to(B["loaded"], timeout=120)
        self.check_splash(vm)                    # (still showing after the load)
        with open(PRG, "rb") as f:
            game = f.read()
        start = game[0] | game[1] << 8
        self.assertEqual(vm.peek(start, len(game) - 2, bank="ram"), game[2:], "the game, byte for byte")
        vm.run_to(vm.labels["frame_done"], timeout=60)
        self.assertNotEqual(vm.peek8("game_mode"), 0, "the menu")
        self.assertEqual(vm.peek8(0xDD00) & 3, 2, "the game's VIC bank")

    def test_space(self):
        vm = self.vm()
        vm.run_to(B["key_read"], timeout=120)
        self.assertEqual(frames_until_go(vm, press_at=50), 50)
        vm.run_to(vm.labels["frame_done"], timeout=120)


if __name__ == "__main__":
    unittest.main()
