"""Compiles the tunes and sound effects (music/*.txt, the CPC's) into
src/data/music.asm for the SID player (src/sound.asm).

The text format is the CPC's (tools/mkmusic.py there):

    # tune: game   # quarter: 16   # loop: yes|no
    A: A4/8 Bb4/8 C#5/4 r/4 | ...     melody (SID voice 1)
    B: A2/4 E3/4 ...                  bass (voice 2)

    sfx.txt:  coin 1: B5:13 E6:13 n12:8 A2+n31:15 r     (voice 3)
              name priority: one step a tick: note:volume, nNN:volume
              (noise, the AY's period NN 0-31), note+nNN:volume, r

On the SID a step with noise plays the noise waveform alone (it cannot mix
noise with a tone); the AY's noise period becomes the noise frequency.

Output:
  freq_lo / freq_hi  SID frequencies (PAL, 985248 Hz) of notes 1.. (C2 = 1)
  tune_a / tune_b    per tune: its two streams (lo/hi tables)
  tune streams       (note, ticks) pairs; note 0 = rest; TUNE_LOOP / TUNE_STOP
  sfx_lo / sfx_hi / sfx_prio, then the steps: frequency (2), volume |
  SFX_TONE_OFF | SFX_NOISE_ON; SFX_END ends
"""

import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MUSIC_DIR = os.path.join(ROOT, "music")
OUT = os.path.join(ROOT, "src", "data", "music.asm")

PAL_CLOCK = 985248
AY_CLOCK = 1_000_000
FIRST_OCTAVE, LAST_OCTAVE = 2, 7
SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LENGTHS = (1, 2, 4, 8, 16)
TUNE_LOOP, TUNE_STOP = 0xFF, 0xFE
SFX_END = 0xFF
SFX_TONE_OFF, SFX_NOISE_ON = 0x80, 0x40
MAX_TICKS = 250
CHANNELS = ("A", "B")
NOTE_RE = re.compile(r"^([A-G])([#b]?)([0-9])$")


class MusicError(Exception):
    pass


def note_count():
    return (LAST_OCTAVE - FIRST_OCTAVE + 1) * 12


def note_index(name, where=""):
    """'C#5' -> 1-based index from C2."""
    m = NOTE_RE.match(name)
    if not m:
        raise MusicError(f"{where}: bad note {name!r}")
    letter, accidental, octave = m.group(1), m.group(2), int(m.group(3))
    index = (octave - FIRST_OCTAVE) * 12 + SEMITONES[letter] + {"#": 1, "b": -1, "": 0}[accidental] + 1
    if not FIRST_OCTAVE <= octave <= LAST_OCTAVE or not 1 <= index <= note_count():
        raise MusicError(f"{where}: note {name!r} out of range (C{FIRST_OCTAVE}-B{LAST_OCTAVE})")
    return index


def sid_freq(hz):
    return min(0xFFFF, round(hz * (1 << 24) / PAL_CLOCK))


def frequencies():
    """SID frequency of every note index (1..note_count())."""
    return [sid_freq(440.0 * 2 ** ((36 + i - 69) / 12)) for i in range(note_count())]


def noise_freq(period):
    """the AY's noise period (1-31) -> a SID noise frequency of the same pitch"""
    return sid_freq(AY_CLOCK / (16 * max(1, period)))


def ticks_of(length, quarter, where):
    dotted = length.endswith(".")
    value = int(length.rstrip(".")) if length.rstrip(".").isdigit() else 0
    if value not in LENGTHS:
        raise MusicError(f"{where}: length must be one of {LENGTHS}, got {length!r}")
    ticks = quarter * 4 / value * (1.5 if dotted else 1)
    if ticks != int(ticks) or not 1 <= ticks <= MAX_TICKS:
        raise MusicError(f"{where}: /{length} is not a whole number of ticks at quarter {quarter}")
    return int(ticks)


def parse_stream(text, quarter, where):
    events = []
    for token in text.split():
        if token == "|":
            continue
        name, sep, length = token.partition("/")
        if not sep:
            raise MusicError(f"{where}: expected note/length, got {token!r}")
        events.append((0 if name == "r" else note_index(name, where), ticks_of(length, quarter, where)))
    return events


def load_tune(path):
    header, streams = {}, {ch: [] for ch in CHANNELS}
    with open(path, encoding="utf-8") as f:
        lines = list(enumerate(f, 1))
    for _, line in lines:
        line = line.strip()
        if line.startswith("#") and ":" in line:
            key, value = line[1:].split(":", 1)
            header[key.strip()] = value.strip()
    quarter = int(header.get("quarter", 16))
    for number, line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        channel, sep, text = line.partition(":")
        if not sep or channel.strip() not in CHANNELS:
            raise MusicError(f"{path}:{number}: expected 'A: ...' or 'B: ...'")
        streams[channel.strip()] += parse_stream(text, quarter, f"{path}:{number}")
    name = header.get("tune")
    if not name or not name.isidentifier():
        raise MusicError(f"{path}: needs '# tune: <name>'")
    if header.get("loop", "yes") not in ("yes", "no"):
        raise MusicError(f"{path}: loop is yes or no")
    return {"name": name, "quarter": quarter, "loop": header.get("loop", "yes") == "yes", "streams": streams}


def parse_step(step, where):
    if step == "r":
        return (0, 0)                            # frequency, volume|flags
    body, sep, volume = step.rpartition(":")
    if not sep or not volume.isdigit() or not 0 <= int(volume) <= 15:
        raise MusicError(f"{where}: step {step!r}: expected <sound>:<volume 0-15>")
    flags, freq, noise = SFX_TONE_OFF, 0, None
    for part in body.split("+"):
        if part.startswith("n") and part[1:].isdigit():
            noise = int(part[1:])
            if not 0 <= noise <= 31:
                raise MusicError(f"{where}: noise period 0-31, got {noise}")
            flags |= SFX_NOISE_ON
        else:
            freq = frequencies()[note_index(part, where) - 1]
            flags &= ~SFX_TONE_OFF
    if noise is not None:                        # the SID: noise alone
        freq = noise_freq(noise)
    return (freq, int(volume) | flags)


def load_sfx(path):
    effects = []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, sep, steps = line.partition(":")
            parts = head.split()
            if not sep or len(parts) != 2 or not parts[0].isidentifier() or not parts[1].isdigit():
                raise MusicError(f"{path}:{number}: expected '<name> <priority>: steps'")
            effects.append({"name": parts[0], "prio": int(parts[1]),
                            "steps": [parse_step(s, f"{path}:{number}") for s in steps.split()]})
    return effects


def load_all(music_dir=MUSIC_DIR):
    tunes = [load_tune(p) for p in sorted(glob.glob(os.path.join(music_dir, "*.txt")))
             if os.path.basename(p) != "sfx.txt"]
    return tunes, load_sfx(os.path.join(music_dir, "sfx.txt"))


def asm_source(tunes, effects):
    lines = ["; generated by tools/mkmusic64.py from music/*.txt - do not edit",
             f"TUNE_LOOP = ${TUNE_LOOP:02x}", f"TUNE_STOP = ${TUNE_STOP:02x}", f"SFX_END = ${SFX_END:02x}",
             f"SFX_TONE_OFF = ${SFX_TONE_OFF:02x}", f"SFX_NOISE_ON = ${SFX_NOISE_ON:02x}",
             f"TUNES = {len(tunes)}"]
    lines += [f"TUNE_{t['name'].upper()} = {i}" for i, t in enumerate(tunes)]
    lines += [f"SFX_{e['name'].upper()} = {i + 1}" for i, e in enumerate(effects)]     # 0: none
    f = [0] + frequencies()                      # note 0: rest
    lines.append("freq_lo .byte " + ", ".join(f"${v & 255:02x}" for v in f))
    lines.append("freq_hi .byte " + ", ".join(f"${v >> 8:02x}" for v in f))
    for ch in CHANNELS:
        names = [f"tune_{t['name']}_{ch.lower()}" for t in tunes]
        lines.append(f"tune_{ch.lower()}_lo .byte " + ", ".join(f"<{n}" for n in names))
        lines.append(f"tune_{ch.lower()}_hi .byte " + ", ".join(f">{n}" for n in names))
    for t in tunes:
        end = TUNE_LOOP if t["loop"] else TUNE_STOP
        for ch in CHANNELS:
            ev = t["streams"][ch]
            lines.append(f"tune_{t['name']}_{ch.lower()}")
            for i in range(0, len(ev), 8):
                lines.append("        .byte " + ", ".join(f"{n}, {d}" for n, d in ev[i:i + 8]))
            lines.append(f"        .byte ${end:02x}")
    names = [f"sfx_steps_{e['name']}" for e in effects]
    lines.append("sfx_lo .byte " + ", ".join(f"<{n}" for n in names))
    lines.append("sfx_hi .byte " + ", ".join(f">{n}" for n in names))
    lines.append("sfx_prio .byte " + ", ".join(str(e["prio"]) for e in effects))
    for e in effects:
        lines.append(f"sfx_steps_{e['name']}")
        for freq, vol in e["steps"]:
            lines.append(f"        .byte ${freq & 255:02x}, ${freq >> 8:02x}, ${vol:02x}")
        lines.append(f"        .byte 0, 0, ${SFX_END:02x}")
    return "\n".join(lines) + "\n"


def main():
    try:
        tunes, effects = load_all()
    except MusicError as e:
        print(f"mkmusic64: {e}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(asm_source(tunes, effects))
    events = sum(len(s) for t in tunes for s in t["streams"].values())
    print(f"mkmusic64: {len(tunes)} tunes, {events} notes, {len(effects)} effects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
