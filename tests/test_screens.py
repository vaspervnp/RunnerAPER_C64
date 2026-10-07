"""Phase 8: screens and game flow (src/screens.asm, src/disk.asm).

  - boot: the menu (logo, options, cursor), its charset and colours;
  - menu: cursor, difficulty, the screens behind it and back, the language;
  - START: the countdown (3, 2, 1, GO! on the track, the world still; on
    hard the wagons hint first), then the game at the skill's speed;
  - H pauses (PAUSE over the HUD's route), RUN/STOP back to the menu;
  - game over with a record: the name (up/down/fire), the table, back;
  - the table saved as SCORES on a copy of the .d64, and read back by a new
    run from that disk.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from vice import Vice

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import mktext64  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
D64 = os.path.join(ROOT, "build", "runner.d64")
SCREEN_A, SCREEN_B = 0x4000, 0x4400
HUD_ROUTE = SCREEN_A + 22 * 40
MODE_PLAY, MODE_MENU, MODE_CONTROLS, MODE_SCORES, MODE_OVER, MODE_STORY = 0, 2, 3, 4, 5, 6
KEY_LEFT, KEY_RIGHT, KEY_JUMP, KEY_DOWN, KEY_PAUSE, KEY_ESC, KEY_UP, KEY_FIRE = (1 << i for i in range(8))
MENU_ROW, MENU_X, CURSOR_X = 7, 14, 12
LABEL_ROW, COUNT_ROW = 8, 11
TEXTS = mktext64.load_all()


class Flow:
    def __init__(self, image=None, extra_args=()):
        kw = {"image": image} if image else {}
        self.vm = Vice(play=False, extra_args=extra_args, **kw)
        self.vm.run_frames(2)
        self.vm.poke("test_mode", 1)
        self.vm.poke("test_keys", 0)

    def close(self):
        self.vm.close()

    def frames(self, n=1):
        self.vm.run_frames(n)

    def tap(self, key, after=2):
        self.vm.poke("test_keys", key)
        self.vm.run_frames(1)
        self.vm.poke("test_keys", 0)
        self.vm.run_frames(after)

    def mode(self):
        return self.vm.peek8("game_mode")

    def row(self, r):
        screen = SCREEN_A if self.vm.peek8("cur_buf") == 0 else SCREEN_B
        return list(self.vm.peek(screen + r * 40, 40))

    def text(self, name, lang=None):
        lang = lang or ("el" if self.vm.peek8("language") else "en")
        return TEXTS[lang][name]

    def shows(self, r, codes):
        row = self.row(r)
        return any(row[x:x + len(codes)] == codes for x in range(41 - len(codes)))


class FlowSteps:
    def assertShows(self, f, r, name):
        self.assertTrue(f.shows(r, f.text(name)), f"{name} not on row {r}: {f.row(r)}")

    def start(self, f, skill=0):
        f.vm.poke("skill", skill)
        f.tap(KEY_FIRE, after=0)                    # START
        self.assertEqual(f.mode(), MODE_PLAY)

    def game_over_with(self, f, score):
        vm = f.vm
        self.start(f)
        vm.poke("countdown", 1)
        f.frames(5)
        vm.poke("score", bytes(score))
        vm.poke("game_state", 2)                    # game over, its wait almost done
        vm.poke("state_timer", 2)
        f.frames(4)
        self.assertEqual(f.mode(), MODE_OVER)

    def enter_name(self, f):
        f.tap(KEY_UP)                               # C
        f.tap(KEY_UP)
        f.tap(KEY_FIRE)
        f.tap(KEY_DOWN)                             # Z
        f.tap(KEY_FIRE)
        f.tap(KEY_FIRE)                             # A



class FlowTest(FlowSteps, unittest.TestCase):
    def flow(self, **kw):
        f = Flow(**kw)
        self.addCleanup(f.close)
        return f

    def test_menu(self):
        f = self.flow()
        vm = f.vm
        self.assertEqual(f.mode(), MODE_MENU)
        logo = vm.peek("logo_chars", 36)
        self.assertEqual(f.row(0)[2:38], list(logo))
        for i, name in enumerate(["menu_start", "menu_controls", "menu_scores", "menu_story",
                                  "menu_skill_0", "menu_music_on", "menu_sound_on"]):
            self.assertEqual(f.row(MENU_ROW + i)[MENU_X:MENU_X + len(f.text(name))], f.text(name), name)
        right = vm.addr("FONT_RIGHT")
        self.assertEqual(f.row(MENU_ROW)[CURSOR_X], right)
        vm.run_to("irq_top_done")
        self.assertEqual(vm.peek8(0xD018) & 0x0E, 0x08, "the menu charset at $6000")
        self.assertEqual(vm.peek8(0xD021) & 15, 0, "black")
        # cursor, difficulty
        for _ in range(4):
            f.tap(KEY_DOWN)
        self.assertEqual(f.row(MENU_ROW + 4)[CURSOR_X], right)
        self.assertNotEqual(f.row(MENU_ROW)[CURSOR_X], right)
        f.tap(KEY_FIRE)
        self.assertEqual(vm.peek8("skill"), 1)
        self.assertShows(f, MENU_ROW + 4, "menu_skill_1")
        f.tap(KEY_DOWN)
        f.tap(KEY_FIRE)
        self.assertEqual(vm.peek8("music_on"), 0)
        self.assertShows(f, MENU_ROW + 5, "menu_music_off")
        # the language (L reads the keyboard: tests set it)
        vm.poke("language", 1)
        vm.poke("screen_dirty", 1)
        f.frames(2)
        self.assertShows(f, MENU_ROW, "menu_start")
        self.assertTrue(f.shows(MENU_ROW, f.text("menu_start", "el")))
        vm.poke("language", 0)
        vm.poke("screen_dirty", 1)
        f.frames(2)

    def test_screens_and_back(self):
        f = self.flow()
        for sel, mode, title, line in ((1, MODE_CONTROLS, "controls_title", (3, "controls_left")),
                                       (2, MODE_SCORES, "scores_title", None),
                                       (3, MODE_STORY, "story_title", (3, "story_1"))):
            for _ in range(sel):
                f.tap(KEY_DOWN)
            f.tap(KEY_FIRE)
            self.assertEqual(f.mode(), mode)
            self.assertShows(f, 1, title)
            if line:
                self.assertShows(f, *line)
            if mode == MODE_SCORES:
                n = f.vm.addr("FONT_N0")
                a = f.vm.addr("FONT_A")
                want = [n + 1, f.vm.addr("FONT_DOT"), 0, a + 0, a + 15, a + 4, 0, n, n + 2, n, n, n, n]
                self.assertTrue(f.shows(3, want), "1. APE 020000")
            f.tap(KEY_FIRE)
            self.assertEqual(f.mode(), MODE_MENU)
            for _ in range(sel):
                f.tap(KEY_UP)

    def test_countdown_then_the_game(self):
        f = self.flow()
        vm = f.vm
        self.start(f)
        top = vm.peek16("disp_top")
        seen = set()
        for _ in range(160):
            f.frames(1)
            for name in ("pu_3", "pu_2", "pu_1"):
                if f.shows(COUNT_ROW, f.text(name)):
                    seen.add(name)
            if vm.peek8("countdown") == 0:
                break
            self.assertEqual(vm.peek16("disp_top"), top, "the world waits")
        self.assertEqual(seen, {"pu_3", "pu_2", "pu_1"})
        self.assertShows(f, COUNT_ROW, "pu_go")
        f.frames(20)
        self.assertGreater(vm.peek16("disp_top"), top, "then it runs")
        self.assertEqual((vm.peek8("speed_hi"), vm.peek8("speed_lo")), (1, 0x80), "easy: 1.5")

    def test_hard_shows_the_wagons_hint(self):
        f = self.flow()
        self.start(f, skill=2)
        f.frames(3)
        self.assertShows(f, LABEL_ROW, "pu_wagons")
        self.assertEqual(f.vm.peek8("gap_hard"), 1)
        self.assertEqual((f.vm.peek8("speed_hi"), f.vm.peek8("speed_lo")), (2, 0x80), "hard: 2.5")

    def test_pause_and_run_stop(self):
        f = self.flow()
        vm = f.vm
        self.start(f)
        vm.poke("countdown", 1)
        f.frames(10)
        f.tap(KEY_PAUSE)
        self.assertEqual(vm.peek8("paused"), 1)
        top = vm.peek16("disp_top")
        f.frames(30)
        self.assertEqual(vm.peek16("disp_top"), top)
        pause = f.text("pause")
        route = list(vm.peek(HUD_ROUTE, 40))
        self.assertTrue(any(route[x:x + len(pause)] == pause for x in range(40)))
        f.tap(KEY_PAUSE)
        f.frames(20)
        self.assertGreater(vm.peek16("disp_top"), top)
        route_chars = vm.peek("hud_chars", 26)[21:26]
        self.assertTrue(all(c in route_chars for c in vm.peek(HUD_ROUTE + 1, 38)), "the route back")
        f.tap(KEY_ESC)
        self.assertEqual(f.mode(), MODE_MENU)
        self.assertShows(f, MENU_ROW, "menu_start")

    def test_game_over_record_and_the_table(self):
        f = self.flow()
        vm = f.vm
        self.game_over_with(f, [0x56, 0x34, 0x12])  # 123456
        self.assertShows(f, 1, "over_title")
        self.assertShows(f, 11, "over_record")
        self.assertEqual(vm.peek8("over_rank"), 0)
        self.enter_name(f)
        table = vm.peek("hiscore_table", 48)
        self.assertEqual(list(table[:6]), [0x56, 0x34, 0x12, 2, 25, 0])
        self.assertEqual(list(table[6:12]), [0x00, 0x00, 0x02, 0, 15, 4], "APE one place down")
        self.assertEqual(list(vm.peek("best", 3)), [0x56, 0x34, 0x12])
        self.assertShows(f, 19, "over_continue")
        f.tap(KEY_FIRE)
        self.assertEqual(f.mode(), MODE_SCORES)
        a = vm.addr("FONT_A")
        self.assertTrue(f.shows(3, [a + 2, a + 25, a + 0]), "CZA first")
        f.tap(KEY_FIRE)
        self.assertEqual(f.mode(), MODE_MENU)

    def test_game_over_without_a_record(self):
        f = self.flow()
        self.game_over_with(f, [0x00, 0x05, 0x00])  # 500
        self.assertEqual(f.vm.peek8("over_rank"), 8)
        self.assertShows(f, 19, "over_continue")
        f.tap(KEY_FIRE)
        self.assertEqual(f.mode(), MODE_SCORES)


class DiskTest(FlowSteps, unittest.TestCase):
    def test_scores_saved_and_loaded(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        d64 = os.path.join(tmp, "runner.d64")
        shutil.copy(D64, d64)
        disk = ["-8", d64, "+drive8truedrive", "-virtualdev8"]
        f = Flow(image=d64, extra_args=disk)
        try:
            self.game_over_with(f, [0x99, 0x99, 0x00])     # 9999
            self.assertEqual(f.vm.peek8("over_rank"), 4)
            self.enter_name(f)
            f.frames(5)
            self.assertEqual(f.mode(), MODE_OVER, "back from the drive")
            self.assertEqual(f.vm.peek8("overruns") < 255, True)
        finally:
            f.close()
        listing = subprocess.run(["c1541", d64, "-list"], capture_output=True, text=True).stdout.lower()
        self.assertIn('"scores"', listing)
        g = Flow(image=d64, extra_args=disk)
        try:
            table = g.vm.peek("hiscore_table", 48)
            self.assertEqual(list(table[24:30]), [0x99, 0x99, 0x00, 2, 25, 0], "read back from the disk")
            self.assertEqual(g.mode(), MODE_MENU)
        finally:
            g.close()


if __name__ == "__main__":
    unittest.main()
