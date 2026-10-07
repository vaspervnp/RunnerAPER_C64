"""Sound (src/sound.asm, tools/mkmusic64.py).

  - the tunes, tick by tick, for all their length and into the loop: every
    register of the three music voices (frequency, pulse width, control,
    envelope), the base note, the gate and the filter, against
    mkmusic64.Player, a model of the player;
  - the tune follows the screen (menu, game, game over once);
  - effects on voice 3: their steps, the envelope ($D41C, read by the
    player) sounding, a lower priority never interrupting a higher one,
    voice 3 back to the music after;
  - M / MUSIC off: no gate on the music's voices (the stores to the SID);
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

SONG = mkmusic64.load_all()
TUNE = {t["name"]: i for i, t in enumerate(SONG.tunes)}
SFX = {e["name"]: i + 1 for i, e in enumerate(SONG.effects)}
MODE_OVER = 5


class Sound:
    def __init__(self, play):
        # a real sound device: with "dummy" VICE does not clock the SID
        self.tmp = tempfile.mkdtemp()
        self.vm = Vice(play=play, extra_args=["-sounddev", "wav", "-soundarg", os.path.join(self.tmp, "out.wav")])
        self.vm.run_frames(2)
        self.vm.poke("test_mode", 1)
        self.vm.poke("test_keys", 0)
        self.vm.poke("no_crash", 1)
        self.base = self.vm.addr("sstate")
        self.size = self.vm.addr("SSTATE_SIZE")
        self.off = {n: self.vm.addr(n) - self.base for n in (
            "snd_ticks", "snd_tune", "flt_cut", "flt_res", "ch_note", "ch_gate", "ch_flt", "ch_pw_lo", "ch_pw_hi",
            "sid_freq_lo", "sid_freq_hi", "sid_ctrl", "sid_ad", "sid_sr", "sfx_on", "sfx_freq_lo", "sfx_freq_hi",
            "sfx_ctrl", "sfx_sr")}

    def close(self):
        self.vm.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decode(self, m):
        o = self.off

        def three(name):
            return [m[o[name] + v] for v in range(3)]

        return {"ticks": m[o["snd_ticks"]], "tune": m[o["snd_tune"]],
                "freq": [m[o["sid_freq_lo"] + v] | m[o["sid_freq_hi"] + v] << 8 for v in range(3)],
                "pw": [m[o["ch_pw_lo"] + v] | m[o["ch_pw_hi"] + v] << 8 for v in range(3)],
                "ctrl": three("sid_ctrl"), "ad": three("sid_ad"), "sr": three("sid_sr"),
                "note": three("ch_note"), "gate": three("ch_gate"), "flt": three("ch_flt"),
                "cut": m[o["flt_cut"]], "res": m[o["flt_res"]], "sfx_on": m[o["sfx_on"]],
                "sfx_freq": m[o["sfx_freq_lo"]] | m[o["sfx_freq_hi"]] << 8,
                "sfx_gate": m[o["sfx_ctrl"]] & 1, "sfx_sustain": m[o["sfx_sr"]] >> 4}

    def ticks(self, n, each=None):
        """the next n sound ticks: stop where each starts, the state the one
        before left; each(k) is called at the stops (pokes)"""
        vm = self.vm
        cp = vm.checkpoint("irq_split_end")
        out = []
        try:
            for k in range(n):
                vm._pending.clear()
                vm.cont()
                vm.wait_event((EV_CHECKPOINT,))
                vm.wait_event((EV_STOPPED,))
                out.append(self.decode(vm.peek(self.base, self.size)))
                if each:
                    each(k)
        finally:
            vm.delete_checkpoint(cp)
        return out

    def tick(self):
        return self.ticks(1)[0]

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


MUSIC_KEYS = ("freq", "pw", "ctrl", "ad", "sr", "note", "gate", "flt")


class SoundTest(unittest.TestCase):
    def sound(self, play=True):
        s = Sound(play)
        self.addCleanup(s.close)
        return s

    def restart(self, s):
        """the tune from its start on the next tick"""
        s.tick()
        s.vm.poke("snd_tune", 0xFE)

    def against_model(self, s, tune, ticks):
        model = mkmusic64.Player(SONG, TUNE[tune])
        seen = s.ticks(ticks)
        for k, st in enumerate(seen):
            want = model.tick()
            self.assertEqual(st["tune"], TUNE[tune])
            for key in MUSIC_KEYS:
                self.assertEqual(st[key], want[key], f"{tune}: tick {k + 1}: {key}")
            if any(want["flt"]):
                self.assertEqual((st["cut"], st["res"]), (want["cut"], want["res"]), f"{tune}: tick {k + 1}: filter")
        for x, y in zip(seen, seen[1:]):
            self.assertEqual((y["ticks"] - x["ticks"]) & 255, 1, "a tick every frame")
        return seen

    def test_menu_tune(self):
        s = self.sound(play=False)
        self.restart(s)
        t = SONG.tunes[TUNE["menu"]]
        self.against_model(s, "menu", sum(t["ticks"]) + t["ticks"][1] // 4)    # and into the loop

    def test_game_tune_then_game_over(self):
        s = self.sound()
        self.restart(s)
        t = SONG.tunes[TUNE["game"]]
        seen = self.against_model(s, "game", sum(t["ticks"]) + 200)
        voices = {v: {x["ctrl"][v] & 0xF0 for x in seen} for v in range(3)}
        self.assertIn(0x80, voices[2], "drums: noise on voice 3")
        self.assertTrue(any(x["flt"][1] for x in seen), "the bass through the filter")
        s.vm.poke("game_state", 2)
        s.vm.poke("state_timer", 2)
        for _ in range(4):
            s.tick()
        self.assertEqual(s.vm.peek8("game_mode"), MODE_OVER)
        self.restart(s)
        over = SONG.tunes[TUNE["over"]]
        self.against_model(s, "over", sum(over["ticks"]) + 10)
        st = s.tick()
        self.assertEqual(st["gate"], [0, 0, 0], "once, then silence")

    def test_effects(self):
        s = self.sound()
        vm = s.vm
        coin = SONG.effects[SFX["coin"] - 1]["steps"]
        vm.poke("sfx_request", SFX["coin"])
        s.tick()                                 # (stopped before the tick that takes it)
        env = 0
        for k, (freq, vol) in enumerate(coin):
            st = s.tick()
            self.assertEqual((st["sfx_freq"], st["sfx_sustain"]), (freq, vol & 15), f"coin step {k}")
            self.assertEqual((st["sfx_on"], st["sfx_gate"]), (1, 1))
            env = max(env, vm.peek8("snd_env3"))
        self.assertGreater(env, 0, "voice 3 sounds")
        st = s.tick()
        self.assertEqual(st["sfx_on"], 0, "over: voice 3 back to the music")
        # crash (3) then coin (1): the crash goes on
        crash = SONG.effects[SFX["crash"] - 1]["steps"]
        vm.poke("sfx_request", SFX["crash"])     # (stopped at the tick: it takes it now)
        s.tick()
        vm.poke("sfx_request", SFX["coin"])
        st = s.tick()
        self.assertEqual(st["sfx_freq"], crash[1][0])
        # jump (1) then powerup (2): the powerup takes over
        for _ in range(len(crash)):
            s.tick()
        vm.poke("sfx_request", SFX["jump"])
        s.tick()
        vm.poke("sfx_request", SFX["powerup"])
        st = s.tick()
        self.assertEqual(st["sfx_freq"], SONG.effects[SFX["powerup"] - 1]["steps"][0][0])

    def test_effect_has_voice_3(self):
        """while an effect plays the SID's voice 3 is the effect's, then the music's again"""
        s = self.sound()
        vm = s.vm
        s.tick()
        vm.poke("sfx_request", SFX["powerup"])
        steps = SONG.effects[SFX["powerup"] - 1]["steps"]
        self.assertEqual(s.stores(0xD40F, 3), [f >> 8 for f, _ in steps[:3]])
        s.ticks(len(steps) + 2)
        self.assertEqual(s.stores(0xD40F, 1), [vm.peek8(vm.addr("sid_freq_hi") + 2)], "the music's again")

    def test_game_asks_for_effects(self):
        s = self.sound()
        vm = s.vm
        vm.poke("test_keys", 4)                  # jump
        seen = s.ticks(5, each=lambda k: vm.poke("test_keys", 0) if k == 1 else None)
        jump = [f for f, _ in SONG.effects[SFX["jump"] - 1]["steps"]]
        self.assertTrue({x["sfx_freq"] for x in seen} & set(jump), ([x["sfx_freq"] for x in seen], jump))

    def test_music_off_and_mute(self):
        s = self.sound()
        vm = s.vm
        on = s.stores(0xD40B, 60)               # (the melody comes in after 2 bars)
        self.assertIn(1, [v & 1 for v in on], "voice 2 gated")
        vm.poke("music_on", 0)
        for reg, voice in ((0xD404, 1), (0xD40B, 2), (0xD412, 3)):
            off = s.stores(reg, 60)
            self.assertEqual({v & 1 for v in off}, {0}, f"music off: no gate on voice {voice}")
        vm.poke("sfx_request", SFX["coin"])
        self.assertIn(1, [v & 1 for v in s.stores(0xD412, 3)], "effects still play")
        vm.poke("music_on", 1)
        self.assertEqual({v & 15 for v in s.stores(0xD418, 5)}, {15})
        vm.poke("sound_on", 0)
        self.assertEqual({v & 15 for v in s.stores(0xD418, 5)}, {0})
        vm.poke("sound_on", 1)
        vm.poke("paused", 1)
        self.assertEqual({v & 15 for v in s.stores(0xD418, 5)}, {0})
        vm.poke("paused", 0)

    def test_cost(self):
        s = self.sound()
        vm = s.vm
        worst = 0
        after = vm.addr("irq_split_end") + 3
        for k in range(300):
            if k % 10 == 0:
                vm.poke("sfx_request", SFX["crash"] if k % 20 else SFX["powerup"])
            a = vm.run_to("sound_tick")
            b = vm.run_to(after)
            worst = max(worst, ((b["LIN"] - a["LIN"]) % 312) * 63 + b["CYC"] - a["CYC"])
        print(f"\n  sound_tick: at most ~{worst} cycles")
        self.assertLess(worst, 2500)            # (bar lines: three notes and patterns at once)


if __name__ == "__main__":
    unittest.main()
