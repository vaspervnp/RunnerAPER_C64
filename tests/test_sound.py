"""Phase 9: sound (src/sound.asm, tools/mkmusic64.py).

  - the tunes, tick by tick: voices 1 and 2 (frequency, gate) as a model of
    the player reads them from music/*.txt;
  - the tune follows the screen (menu, game, game over once);
  - effects on voice 3: their steps, the envelope ($D41C, read by the
    player) sounding, a lower
    priority never interrupting a higher one;
  - M / MUSIC off: voices 1-2 without gate (the stores to the SID);
    SOUND off or the pause: volume 0;
  - the player's cost per tick.
"""

import os
import shutil
import struct
import sys
import tempfile
import unittest

from vice import EV_CHECKPOINT, EV_STOPPED, OP_STORE, Vice

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import mkmusic64  # noqa: E402

TUNES, EFFECTS = mkmusic64.load_all()
TUNE = {t["name"]: i for i, t in enumerate(TUNES)}
SFX = {e["name"]: i + 1 for i, e in enumerate(EFFECTS)}
FREQ = [0] + mkmusic64.frequencies()
MODE_OVER = 5


def model(tune, channel, ticks):
    """(frequency, gate) of a channel after 1..ticks ticks from the tune's start"""
    events = tune["streams"][channel]
    out, left, i, freq, gate, stopped = [], 1, 0, 0, 0, False
    for _ in range(ticks):
        left -= 1
        if left == 0 and not stopped:
            if i == len(events):
                if tune["loop"]:
                    i = 0
                else:
                    stopped, gate, left = True, 0, 1
            if not stopped:
                note, left = events[i]
                i += 1
                if note:
                    freq, gate = FREQ[note], 1
                else:
                    gate = 0
        elif stopped:
            left = 1
        elif left == 1:
            gate = 0
        out.append((freq, gate))
    return out


class Sound:
    def __init__(self, play):
        # a real sound device: with "dummy" VICE does not clock the SID
        self.tmp = tempfile.mkdtemp()
        self.vm = Vice(play=play, extra_args=["-sounddev", "wav", "-soundarg", os.path.join(self.tmp, "out.wav")])
        self.vm.run_frames(2)
        self.vm.poke("test_mode", 1)
        self.vm.poke("test_keys", 0)
        self.vm.poke("no_crash", 1)

    def close(self):
        self.vm.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tick(self):
        """the next sound tick: stop where it starts; the state of the last one"""
        self.vm.run_to("irq_split_end")
        vm = self.vm
        return {"ticks": vm.peek8("snd_ticks"), "tune": vm.peek8("snd_tune"),
                "freq": [vm.peek8(vm.addr("sid_freq_lo") + v) | vm.peek8(vm.addr("sid_freq_hi") + v) << 8
                         for v in range(3)],
                "gate": [vm.peek8(vm.addr("sid_ctrl") + v) & 1 for v in range(3)],
                "sustain": vm.peek8(vm.addr("sid_sr") + 2) >> 4}

    def stores(self, address, ticks):
        """the values the program stores at `address` during `ticks` ticks"""
        vm = self.vm
        cp = vm.checkpoint(address, op=OP_STORE)
        end = vm.checkpoint("irq_split_end")
        values, done = [], 0
        try:
            while done < ticks:
                vm._pending.clear()
                vm.cont()
                while True:
                    _, body = vm.wait_event((EV_CHECKPOINT,))
                    cid = struct.unpack("<I", body[:4])[0]
                    if cid in (cp, end):
                        break
                vm.wait_event((EV_STOPPED,))
                if cid == end:
                    done += 1
                else:
                    values.append(vm.registers()["A"])
        finally:
            vm.delete_checkpoint(cp)
            vm.delete_checkpoint(end)
        return values


class SoundTest(unittest.TestCase):
    def sound(self, play=True):
        s = Sound(play)
        self.addCleanup(s.close)
        return s

    def follow(self, s, tune, ticks):
        st = s.tick()
        self.assertEqual(st["tune"], TUNE[tune])
        start = None
        seen = []
        for _ in range(ticks):
            st = s.tick()
            seen.append(st)
        # the tune started on the tick where the model's first note matches: find it
        a, b = TUNES[TUNE[tune]], TUNES[TUNE[tune]]
        for offset in range(0, 600):
            ma = model(a, "A", offset + len(seen))[offset:]
            mb = model(b, "B", offset + len(seen))[offset:]
            if all((x["freq"][0], x["gate"][0]) == ma[k] and (x["freq"][1], x["gate"][1]) == mb[k]
                   for k, x in enumerate(seen)):
                start = offset
                break
        self.assertIsNotNone(start, f"{tune}: the voices do not follow the tune")
        for x, y in zip(seen, seen[1:]):
            self.assertEqual((y["ticks"] - x["ticks"]) & 255, 1, "a tick every frame")
        return start

    def test_menu_tune(self):
        s = self.sound(play=False)
        self.follow(s, "menu", 400)

    def test_game_tune_then_game_over(self):
        s = self.sound()
        self.follow(s, "game", 400)
        s.vm.poke("game_state", 2)
        s.vm.poke("state_timer", 2)
        for _ in range(4):
            s.tick()
        self.assertEqual(s.vm.peek8("game_mode"), MODE_OVER)
        over = TUNES[TUNE["over"]]
        length = sum(d for _, d in over["streams"]["A"])
        st = None
        for _ in range(length + 10):
            st = s.tick()
        self.assertEqual(st["tune"], TUNE["over"])
        self.assertEqual(st["gate"][:2], [0, 0], "once, then silence")

    def test_effects(self):
        s = self.sound()
        vm = s.vm
        coin = EFFECTS[SFX["coin"] - 1]["steps"]
        vm.poke("sfx_request", SFX["coin"])
        s.tick()                                 # (stopped before the tick that takes it)
        env = 0
        for k, (freq, vol) in enumerate(coin):
            st = s.tick()
            self.assertEqual((st["freq"][2], st["sustain"]), (freq, vol & 15), f"coin step {k}")
            self.assertEqual(st["gate"][2], 1)
            env = max(env, vm.peek8("snd_env3"))
        self.assertGreater(env, 0, "voice 3 sounds")
        for _ in range(2):
            st = s.tick()
        self.assertEqual(st["gate"][2], 0, "over")
        # crash (3) then coin (1): the crash goes on
        crash = EFFECTS[SFX["crash"] - 1]["steps"]
        vm.poke("sfx_request", SFX["crash"])     # (stopped at the tick: it takes it now)
        s.tick()
        vm.poke("sfx_request", SFX["coin"])
        st = s.tick()
        self.assertEqual(st["freq"][2], crash[1][0])
        # jump (1) then powerup (2): the powerup takes over
        for _ in range(len(crash)):
            s.tick()
        vm.poke("sfx_request", SFX["jump"])
        s.tick()
        vm.poke("sfx_request", SFX["powerup"])
        st = s.tick()
        self.assertEqual(st["freq"][2], EFFECTS[SFX["powerup"] - 1]["steps"][0][0])

    def test_game_asks_for_effects(self):
        s = self.sound()
        vm = s.vm
        vm.poke("test_keys", 4)                  # jump
        seen = []
        for k in range(5):
            seen.append(s.tick()["freq"][2])
            if k == 1:
                vm.poke("test_keys", 0)
        jump = [f for f, _ in EFFECTS[SFX["jump"] - 1]["steps"]]
        self.assertTrue(set(seen) & set(jump), (seen, jump))

    def test_music_off_and_mute(self):
        s = self.sound()
        vm = s.vm
        on = s.stores(0xD404, 60)
        self.assertIn(1, [v & 1 for v in on], "voice 1 gated")
        vm.poke("music_on", 0)
        off = s.stores(0xD404, 60)
        self.assertEqual({v & 1 for v in off}, {0}, "music off: no gate on voice 1")
        vm.poke("sfx_request", SFX["coin"])
        self.assertIn(1, [v & 1 for v in s.stores(0xD412, 3)], "effects still play")
        vm.poke("music_on", 1)
        self.assertEqual(set(s.stores(0xD418, 5)), {15})
        vm.poke("sound_on", 0)
        self.assertEqual(set(s.stores(0xD418, 5)), {0})
        vm.poke("sound_on", 1)
        vm.poke("paused", 1)
        self.assertEqual(set(s.stores(0xD418, 5)), {0})
        vm.poke("paused", 0)

    def test_cost(self):
        s = self.sound()
        vm = s.vm
        worst = 0
        after = vm.addr("irq_split_end") + 3
        for k in range(120):
            if k % 10 == 0:
                vm.poke("sfx_request", SFX["crash"] if k % 20 else SFX["powerup"])
            a = vm.run_to("sound_tick")
            b = vm.run_to(after)
            worst = max(worst, ((b["LIN"] - a["LIN"]) % 312) * 63 + b["CYC"] - a["CYC"])
        print(f"\n  sound_tick: at most ~{worst} cycles")
        self.assertLess(worst, 1500)


if __name__ == "__main__":
    unittest.main()
