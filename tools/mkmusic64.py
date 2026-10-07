"""Compiles the SID music (music/instruments.txt, music/<tune>.txt) and the
sound effects (music/sfx.txt) into src/data/music.asm for the player in
src/sound.asm. It also holds a model of the player (Player), tick for tick,
for the tests.

Instruments (music/instruments.txt), one a line:

    lead: ad=08 sr=a9 pw=400 pws=+20 vib=10,4,3 wave=pulse:0
    kick: ad=05 sr=00 pw=800 wave=pulse:C5,pulse:G4,tri:D3

  ad, sr      the SID's envelope bytes (hex)
  pw, pws     pulse width at the note's start (hex, 200-dff) and its sweep
              per tick (signed); the sweep turns round below 200 / above dff
  vib         delay (ticks), half period (ticks), depth: the step per tick is
              the note's semitone >> depth (none: no vibrato)
  flt         cutoff (hex byte), its sweep per tick (signed), resonance (hex
              digit): the voice goes through the low-pass filter (one filter
              for all: the last such note sets it)
  wave        the wavetable, one step a tick from the note's start:
              <tri|saw|pulse|noise>:<+semitones from the note | a note, C5>;
              @N jumps back to step N, otherwise the last step holds

A tune (music/<name>.txt):

    # tune: game   # quarter: 16 (ticks)   # loop: yes|no
    pat p1: @lead E5/8 E5/16 F5/16 r/4 ...     a pattern: @instrument, notes
    seq A: p1 p2 bass+1 bass-2*3                a named run of patterns
    v1: intro > A A p3                          voices 1-3: patterns or seqs,
    v2: ...                                     +N/-N transpose, *N repeat,
    v3: ...                                     > where the loop starts

  An indented line goes on the line before. Lengths: /1 /2 /4 /8 /16,
  dotted with a '.'. All three voices must be as
  long before and after '>'. Voice 3 is shared with the effects: an effect
  takes it while it plays.

sfx.txt (the CPC's effects):  coin 1: B5:13 E6:13 n12:8 A2+n31:15 r
  name priority: one step a tick: note:volume, nNN:volume (noise, the AY's
  period NN 0-31), note+nNN:volume, r. On the SID a step with noise plays
  the noise alone; the AY's noise period becomes the noise frequency.

Pattern bytes: 0 rest, 1-82 notes (C1-A7), $80+i instrument, $a0 end,
$c0+(t-1) length t ticks (1-64). Order bytes: pattern 0-$7f, $80-$bf
transpose (byte - $a0), $fe N loop to N, $ff end.
"""

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MUSIC_DIR = os.path.join(ROOT, "music")
OUT = os.path.join(ROOT, "src", "data", "music.asm")
TUNE_FILES = ("game", "menu", "over")

PAL_CLOCK = 985248
AY_CLOCK = 1_000_000
FIRST_OCTAVE = 1
NOTES = 82                                       # C1 .. A7
SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LENGTHS = (1, 2, 4, 8, 16)
WAVES = {"tri": 0x10, "saw": 0x20, "pulse": 0x40, "noise": 0x80}
NOTE_RE = re.compile(r"^([A-G])([#b]?)([0-9])$")

P_INS, P_END, P_LEN = 0x80, 0xA0, 0xC0
O_TRANS, O_LOOP, O_END = 0xA0, 0xFE, 0xFF
WT_JUMP = 0xFF
PW_LOW, PW_HIGH = 0x200, 0xE00
CUT_MIN, CUT_MAX = 0x08, 0xF8
MAX_TICKS = 64

SFX_END = 0xFF
SFX_TONE_OFF, SFX_NOISE_ON = 0x80, 0x40


class MusicError(Exception):
    pass


def strip_comment(line):
    """'#' starts a comment at the line's start or after a space (C#5 is a note)"""
    return re.split(r"(?:^|\s)#", line, maxsplit=1)[0]


def note_index(name, where=""):
    """'C#5' -> 1-based index from C1"""
    m = NOTE_RE.match(name)
    if not m:
        raise MusicError(f"{where}: bad note {name!r}")
    letter, accidental, octave = m.group(1), m.group(2), int(m.group(3))
    index = (octave - FIRST_OCTAVE) * 12 + SEMITONES[letter] + {"#": 1, "b": -1, "": 0}[accidental] + 1
    if not 1 <= index <= NOTES:
        raise MusicError(f"{where}: note {name!r} out of range (C1-A7)")
    return index


def sid_freq(hz):
    return min(0xFFFF, round(hz * (1 << 24) / PAL_CLOCK))


def frequencies():
    """the SID frequency of notes 0 (silence) .. NOTES + 1 (for the vibrato)"""
    return [0] + [sid_freq(440.0 * 2 ** ((i - 46) / 12)) for i in range(1, NOTES + 2)]


def noise_freq(period):
    """the AY's noise period (1-31) -> a SID noise frequency of the same pitch"""
    return sid_freq(AY_CLOCK / (16 * max(1, period)))


def signed(text, where):
    try:
        v = int(text)
    except ValueError:
        raise MusicError(f"{where}: expected a signed number, got {text!r}")
    if not -128 <= v <= 127:
        raise MusicError(f"{where}: {v} out of -128..127")
    return v


def hexval(text, lo, hi, where):
    try:
        v = int(text, 16)
    except ValueError:
        raise MusicError(f"{where}: expected hex, got {text!r}")
    if not lo <= v <= hi:
        raise MusicError(f"{where}: ${v:x} out of ${lo:x}-${hi:x}")
    return v


# --- instruments ---------------------------------------------------------------

def parse_instrument(name, fields, where):
    ins = {"name": name, "ad": 0, "sr": 0, "pw": 0x800, "pws": 0, "vib": None, "flt": None, "wave": None}
    for field in fields:
        key, sep, value = field.partition("=")
        if not sep:
            raise MusicError(f"{where}: expected key=value, got {field!r}")
        if key in ("ad", "sr"):
            ins[key] = hexval(value, 0, 255, where)
        elif key == "pw":
            ins["pw"] = hexval(value, PW_LOW, PW_HIGH - 1, where)
        elif key == "pws":
            ins["pws"] = signed(value, where)
        elif key == "vib":
            parts = value.split(",")
            if len(parts) != 3:
                raise MusicError(f"{where}: vib=delay,half period,depth")
            delay, half, depth = (int(p) for p in parts)
            if not (0 <= delay <= 255 and 1 <= half <= 127 and 1 <= depth <= 7):
                raise MusicError(f"{where}: vib out of range")
            ins["vib"] = (delay, half, depth)
        elif key == "flt":
            parts = value.split(",")
            if len(parts) != 3:
                raise MusicError(f"{where}: flt=cutoff,sweep,resonance")
            ins["flt"] = (hexval(parts[0], CUT_MIN, CUT_MAX, where), signed(parts[1], where),
                          hexval(parts[2], 0, 15, where))
        elif key == "wave":
            steps = []
            for step in value.split(","):
                if step.startswith("@"):
                    target = int(step[1:])
                    if not 0 <= target < len(steps):
                        raise MusicError(f"{where}: {step}: no such step")
                    steps.append((WT_JUMP, target))
                    continue
                wave, sep, note = step.partition(":")
                if wave not in WAVES or not sep:
                    raise MusicError(f"{where}: wave step {step!r}: <tri|saw|pulse|noise>:<+N|note>")
                if re.match(r"^[+-]?\d+$", note):
                    rel = int(note)
                    if not 0 <= rel <= 24:
                        raise MusicError(f"{where}: relative step 0..24, got {rel}")
                    steps.append((WAVES[wave], rel))
                else:
                    steps.append((WAVES[wave], 0x80 | note_index(note, where)))
            if steps[-1][0] == WT_JUMP and steps[-1][1] == len(steps) - 1:
                raise MusicError(f"{where}: a jump to itself")
            if steps[-1][0] != WT_JUMP:
                steps.append((WT_JUMP, len(steps) - 1))      # the last step holds
            ins["wave"] = steps
        else:
            raise MusicError(f"{where}: unknown field {key!r}")
    if not ins["wave"]:
        raise MusicError(f"{where}: needs wave=")
    return ins


def load_instruments(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            line = strip_comment(line).strip()
            if not line:
                continue
            name, sep, rest = line.partition(":")
            name = name.strip()
            if not sep or not name.isidentifier():
                raise MusicError(f"{path}:{number}: expected '<name>: fields'")
            if name in out:
                raise MusicError(f"{path}:{number}: {name} twice")
            out[name] = parse_instrument(name, rest.split(), f"{path}:{number}")
    if len(out) > 32:
        raise MusicError(f"{path}: at most 32 instruments")
    return out


# --- tunes ---------------------------------------------------------------------

def ticks_of(length, quarter, where):
    dotted = length.endswith(".")
    base = length.rstrip(".")
    value = int(base) if base.isdigit() else 0
    if value not in LENGTHS:
        raise MusicError(f"{where}: length must be one of {LENGTHS}, got {length!r}")
    ticks = quarter * 4 / value * (1.5 if dotted else 1)
    if ticks != int(ticks):
        raise MusicError(f"{where}: /{length} is not a whole number of ticks at quarter {quarter}")
    return int(ticks)


def parse_pattern(text, quarter, instruments, where):
    """-> [('ins', name) | (note 0..82, ticks)], its length in ticks"""
    events, total = [], 0
    for token in text.split():
        if token == "|":
            continue
        if token.startswith("@"):
            if token[1:] not in instruments:
                raise MusicError(f"{where}: no instrument {token[1:]!r}")
            events.append(("ins", token[1:]))
            continue
        name, sep, length = token.partition("/")
        if not sep:
            raise MusicError(f"{where}: expected note/length, got {token!r}")
        ticks = ticks_of(length, quarter, where)
        note = 0 if name == "r" else note_index(name, where)
        while ticks > MAX_TICKS:
            if note:
                raise MusicError(f"{where}: {token}: a note is at most {MAX_TICKS} ticks")
            events.append((0, MAX_TICKS))
            ticks -= MAX_TICKS
        if note and ticks < 2:
            raise MusicError(f"{where}: {token}: a note is at least 2 ticks")
        events.append((note, ticks))
        total += ticks_of(length, quarter, where)
    if not any(e[0] != "ins" for e in events):
        raise MusicError(f"{where}: an empty pattern")
    return events, total


ORDER_RE = re.compile(r"^([A-Za-z_]\w*)([+-]\d+)?(?:\*(\d+))?$")


def load_tune(path, instruments):
    header, pats, seqs, voices = {}, {}, {}, {}
    with open(path, encoding="utf-8") as f:
        lines = list(enumerate(f, 1))
    for _, line in lines:
        line = line.strip()
        if line.startswith("#") and ":" in line:
            key, value = line[1:].split(":", 1)
            header[key.strip()] = value.strip()
    name = header.get("tune")
    if not name or not name.isidentifier():
        raise MusicError(f"{path}: needs '# tune: <name>'")
    quarter = int(header.get("quarter", 16))
    if header.get("loop", "yes") not in ("yes", "no"):
        raise MusicError(f"{path}: loop is yes or no")
    loop = header.get("loop", "yes") == "yes"
    joined = []                                  # an indented line goes on the one before
    for number, raw in lines:
        line = strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if line[0] in " \t" and joined:
            joined[-1] = (joined[-1][0], joined[-1][1] + " " + line.strip())
        else:
            joined.append((number, line.strip()))
    for number, line in joined:
        where = f"{path}:{number}"
        head, sep, body = line.partition(":")
        words = head.split()
        if not sep:
            raise MusicError(f"{where}: expected 'pat <name>:', 'seq <name>:' or 'v1:'..'v3:'")
        if len(words) == 2 and words[0] == "pat":
            pats[words[1]] = parse_pattern(body, quarter, instruments, where)
        elif len(words) == 2 and words[0] == "seq":
            seqs[words[1]] = (body.split(), where)
        elif len(words) == 1 and words[0] in ("v1", "v2", "v3"):
            voices[words[0]] = (body.split(), where)
        else:
            raise MusicError(f"{where}: expected 'pat <name>:', 'seq <name>:' or 'v1:'..'v3:'")
    if set(voices) != {"v1", "v2", "v3"}:
        raise MusicError(f"{path}: needs v1, v2 and v3")

    def expand(tokens, where, depth=0):
        out = []
        for token in tokens:
            if token == ">":
                out.append(">")
                continue
            m = ORDER_RE.match(token)
            if not m:
                raise MusicError(f"{where}: bad order entry {token!r}")
            ref, trans, times = m.group(1), int(m.group(2) or 0), int(m.group(3) or 1)
            for _ in range(times):
                if ref in pats:
                    out.append((ref, trans))
                elif ref in seqs and depth < 4:
                    inner = expand(*seqs[ref], depth + 1)
                    if ">" in inner:
                        raise MusicError(f"{where}: '>' inside seq {ref}")
                    out += [(p, t + trans) for p, t in inner]
                else:
                    raise MusicError(f"{where}: no pattern or seq {ref!r}")
        return out

    orders = {}
    for v, (tokens, where) in sorted(voices.items()):
        entries = expand(tokens, where)
        if entries.count(">") > 1 or (not loop and ">" in entries):
            raise MusicError(f"{where}: one '>', and only in a tune that loops")
        if loop and ">" not in entries:
            entries.insert(0, ">")
        orders[v] = entries
    # every voice as long, before and after the loop point
    lengths = {}
    for v, entries in orders.items():
        split = entries.index(">") if ">" in entries else len(entries)
        before = sum(pats[p][1] for p, _ in entries[:split])
        after = sum(pats[p][1] for p, _ in entries[split + 1:])
        lengths[v] = (before, after)
        for p, t in entries[:split] + entries[split + 1:]:
            if not -32 <= t <= 31:
                raise MusicError(f"{path}: {v}: transpose {t} out of -32..31")
            for e in pats[p][0]:
                if e[0] == "ins" or not e[0]:
                    continue
                if not 1 <= e[0] + t <= NOTES:
                    raise MusicError(f"{path}: {v}: {p}{t:+d}: a note out of range")
    if len(set(lengths.values())) != 1:
        raise MusicError(f"{path}: the voices differ in length (before, after the loop): {lengths}")
    return {"name": name, "quarter": quarter, "loop": loop, "pats": pats, "orders": orders,
            "ticks": lengths["v1"]}


def check_ranges(tunes, instruments):
    """relative wavetable steps on transposed notes stay in range"""
    for t in tunes:
        for v, entries in t["orders"].items():
            for e in entries:
                if e == ">":
                    continue
                p, trans = e
                ins = None
                for ev in t["pats"][p][0]:
                    if ev[0] == "ins":
                        ins = instruments[ev[1]]
                        continue
                    if not ev[0] or ins is None:
                        continue
                    top = max([n for w, n in ins["wave"] if w != WT_JUMP and n < 0x80] or [0])
                    if ev[0] + trans + top > NOTES:
                        raise MusicError(f"{t['name']}: {v}: {p}: {ins['name']} goes above A7")


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
            freq = frequencies()[note_index(part, where)]
            flags &= ~SFX_TONE_OFF
    if noise is not None:                        # the SID: noise alone
        freq = noise_freq(noise)
    return (freq, int(volume) | flags)


# --- compiling -----------------------------------------------------------------

class Song:
    """everything compiled: the bytes the player reads"""

    def __init__(self, instruments, tunes, effects):
        self.tunes, self.effects = tunes, effects
        self.ins_names = list(instruments)
        self.ins = [instruments[n] for n in self.ins_names]
        self.freq = frequencies()
        # wavetable
        self.wt, self.ins_wt = [], []
        for ins in self.ins:
            base = len(self.wt)
            self.ins_wt.append(base)
            for w, n in ins["wave"]:
                self.wt.append((w, base + n) if w == WT_JUMP else (w, n))
        if len(self.wt) > 256:
            raise MusicError("the wavetable is over 256 steps")
        # patterns
        self.patterns, self.pat_names = [], []
        self.orders = []                         # [tune][voice] -> bytes
        for t in tunes:
            index = {}
            for name, (events, _) in t["pats"].items():
                index[name] = len(self.patterns)
                self.patterns.append(self.pattern_bytes(events))
                self.pat_names.append(f"{t['name']}_{name}")
            self.orders.append([self.order_bytes(t["orders"][v], index, t["loop"]) for v in ("v1", "v2", "v3")])
        if len(self.patterns) > 128:
            raise MusicError("at most 128 patterns")

    def pattern_bytes(self, events):
        out, length = [], None
        for e in events:
            if e[0] == "ins":
                out.append(P_INS + self.ins_names.index(e[1]))
                continue
            note, ticks = e
            if ticks != length:
                out.append(P_LEN + ticks - 1)
                length = ticks
            out.append(note)
        out.append(P_END)
        if len(out) > 255:
            raise MusicError("a pattern is over 255 bytes")
        return out

    def order_bytes(self, entries, index, loop):
        out, trans, loop_at = [], None, 0
        for e in entries:
            if e == ">":
                loop_at = len(out)
                trans = None                     # (the loop comes back with any transpose)
                continue
            p, t = e
            if t != trans:
                out.append(O_TRANS + t)
                trans = t
            out.append(index[p])
        out += [O_LOOP, loop_at] if loop else [O_END]
        return out


def load_all(music_dir=MUSIC_DIR):
    instruments = load_instruments(os.path.join(music_dir, "instruments.txt"))
    tunes = [load_tune(os.path.join(music_dir, f"{n}.txt"), instruments) for n in TUNE_FILES]
    check_ranges(tunes, instruments)
    effects = load_sfx(os.path.join(music_dir, "sfx.txt"))
    return Song(instruments, tunes, effects)


def asm_source(song):
    def table(label, values, fmt="${:02x}"):
        rows = [f"{label}"]
        for i in range(0, len(values), 16):
            rows.append("        .byte " + ", ".join(fmt.format(v) for v in values[i:i + 16]))
        return rows

    lines = ["; generated by tools/mkmusic64.py from music/*.txt - do not edit",
             f"TUNES = {len(song.tunes)}", f"SFX_END = ${SFX_END:02x}",
             f"SFX_TONE_OFF = ${SFX_TONE_OFF:02x}", f"SFX_NOISE_ON = ${SFX_NOISE_ON:02x}",
             f"P_INS = ${P_INS:02x}", f"P_END = ${P_END:02x}", f"P_LEN = ${P_LEN:02x}",
             f"O_TRANS = ${O_TRANS:02x}", f"O_LOOP = ${O_LOOP:02x}", f"O_END = ${O_END:02x}",
             f"WT_JUMP = ${WT_JUMP:02x}", f"CUT_MIN = ${CUT_MIN:02x}", f"CUT_MAX = ${CUT_MAX:02x}"]
    lines += [f"TUNE_{t['name'].upper()} = {i}" for i, t in enumerate(song.tunes)]
    lines += [f"SFX_{e['name'].upper()} = {i + 1}" for i, e in enumerate(song.effects)]     # 0: none
    lines += table("freq_lo", [v & 255 for v in song.freq])
    lines += table("freq_hi", [v >> 8 for v in song.freq])
    ins = song.ins
    lines += table("ins_ad", [i["ad"] for i in ins])
    lines += table("ins_sr", [i["sr"] for i in ins])
    lines += table("ins_wt", song.ins_wt)
    lines += table("ins_pw_lo", [i["pw"] & 255 for i in ins])
    lines += table("ins_pw_hi", [i["pw"] >> 8 for i in ins])
    lines += table("ins_pws", [i["pws"] & 255 for i in ins])
    lines += table("ins_vdel", [i["vib"][0] if i["vib"] else 0 for i in ins])
    lines += table("ins_vspd", [i["vib"][1] if i["vib"] else 0 for i in ins])
    lines += table("ins_vhalf", [(i["vib"][1] + 1) // 2 if i["vib"] else 0 for i in ins])
    lines += table("ins_vdepth", [i["vib"][2] if i["vib"] else 0 for i in ins])
    lines += table("ins_fcut", [i["flt"][0] if i["flt"] else 0 for i in ins])
    lines += table("ins_fspd", [i["flt"][1] & 255 if i["flt"] else 0 for i in ins])
    lines += table("ins_fres", [i["flt"][2] << 4 if i["flt"] else 0 for i in ins])
    lines += table("wt_wave", [w for w, _ in song.wt])
    lines += table("wt_note", [n for _, n in song.wt])
    names = [f"pat_{n}" for n in song.pat_names]
    lines.append("pat_lo  .byte " + ", ".join(f"<{n}" for n in names))
    lines.append("pat_hi  .byte " + ", ".join(f">{n}" for n in names))
    for n, data in zip(names, song.patterns):
        lines += table(n, data)
    onames = [f"ord_{t['name']}_{v}" for t in song.tunes for v in (1, 2, 3)]
    lines.append("tune_ord_lo .byte " + ", ".join(f"<{n}" for n in onames))
    lines.append("tune_ord_hi .byte " + ", ".join(f">{n}" for n in onames))
    for n, data in zip(onames, (o for per in song.orders for o in per)):
        lines += table(n, data)
    names = [f"sfx_steps_{e['name']}" for e in song.effects]
    lines.append("sfx_lo .byte " + ", ".join(f"<{n}" for n in names))
    lines.append("sfx_hi .byte " + ", ".join(f">{n}" for n in names))
    lines.append("sfx_prio .byte " + ", ".join(str(e["prio"]) for e in song.effects))
    for e in song.effects:
        lines.append(f"sfx_steps_{e['name']}")
        for freq, vol in e["steps"]:
            lines.append(f"        .byte ${freq & 255:02x}, ${freq >> 8:02x}, ${vol:02x}")
        lines.append(f"        .byte 0, 0, ${SFX_END:02x}")
    return "\n".join(lines) + "\n"


def data_size(song):
    return (2 * len(song.freq) + 13 * len(song.ins) + 2 * len(song.wt) + 2 * len(song.patterns)
            + sum(map(len, song.patterns)) + 6 * len(song.tunes) + sum(len(o) for per in song.orders for o in per))


# --- the player, as src/sound.asm does it (tests) ----------------------------------

class Player:
    """sound.asm's music, tick for tick: the voices' registers (freq, pw, ctrl,
    ad, sr), the filter, the base note and the gate of each channel"""

    def __init__(self, song, tune):
        self.s = song
        self.tune = tune
        self.ch = [dict(order=song.orders[tune][v], pos=0, pat=None, pp=0, trans=0, ticks=1, dur=0, ins=0,
                        note=0, gate=0, wt=0, pw=0, pws=0, vdel=0, vcnt=0, vdir=0, vacc=0, vamt=0, flt=0,
                        stop=False, live=False, freq=0, ctrl=0, ad=0, sr=0) for v in range(3)]
        self.cut, self.cut_spd, self.res = 0, 0, 0

    def next_pattern(self, c):
        order = c["order"]
        y = c["pos"]
        while True:
            b = order[y]
            y += 1
            if b == O_END:
                return False
            if b == O_LOOP:
                y = order[y]
                continue
            if b >= 0x80:
                c["trans"] = b - O_TRANS
                continue
            c["pos"] = y
            c["pat"], c["pp"] = self.s.patterns[b], 0
            return True

    def channel(self, c):
        if c["stop"]:
            c["ctrl"] &= 0xFE
            return
        c["ticks"] -= 1
        if c["ticks"] == 0:
            while True:
                if c["pat"] is None or c["pat"][c["pp"]] == P_END:
                    if not self.next_pattern(c):
                        c["stop"], c["ticks"], c["gate"] = True, 1, 0
                        c["ctrl"] &= 0xFE
                        return
                    continue
                b = c["pat"][c["pp"]]
                c["pp"] += 1
                if b >= P_LEN:
                    c["dur"] = b - P_LEN + 1
                elif b >= P_INS:
                    c["ins"] = b - P_INS
                else:
                    break
            c["ticks"] = c["dur"]
            if b == 0:
                c["gate"] = 0
            else:
                self.start_note(c, b)
        elif c["ticks"] == 1:                    # hard restart
            c["gate"], c["ad"], c["sr"] = 0, 0, 0
        self.effects(c)

    def start_note(self, c, b):
        s, i = self.s, c["ins"]
        ins = s.ins[i]
        n = (b + c["trans"]) & 255
        c["note"] = n
        c["ad"], c["sr"] = ins["ad"], ins["sr"]
        c["wt"] = s.ins_wt[i]
        c["pw"], c["pws"] = ins["pw"], ins["pws"] & 255
        vib = ins["vib"]
        c["vdel"] = vib[0] if vib else 0
        c["vcnt"] = (vib[1] + 1) // 2 if vib else 0
        c["vacc"], c["vdir"] = 0, 0
        if vib:
            c["vamt"] = ((s.freq[n + 1] - s.freq[n]) & 0xFFFF) >> vib[2]
        flt = ins["flt"]
        if flt:
            self.cut, self.cut_spd, self.res = flt[0], flt[1] & 255, flt[2] << 4
        c["flt"] = 1 if flt else 0
        c["gate"], c["live"] = 1, True

    def effects(self, c):
        if not c["live"]:
            return
        s = self.s
        ins = s.ins[c["ins"]]
        if ins["vib"]:                           # vibrato
            if c["vdel"]:
                c["vdel"] -= 1
            else:
                if c["vdir"] == 0:
                    c["vacc"] = (c["vacc"] + c["vamt"]) & 0xFFFF
                else:
                    c["vacc"] = (c["vacc"] - c["vamt"]) & 0xFFFF
                c["vcnt"] -= 1
                if c["vcnt"] == 0:
                    c["vcnt"] = ins["vib"][1]
                    c["vdir"] ^= 1
        y = c["wt"]                              # wavetable
        w, n = s.wt[y]
        if w == WT_JUMP:
            y = n
            w, n = s.wt[y]
        c["ctrl"] = w | c["gate"]
        c["wt"] = (y + 1) & 255
        note = (n & 0x7F) if n & 0x80 else (n + c["note"]) & 255
        c["freq"] = (s.freq[note] + c["vacc"]) & 0xFFFF
        if c["pws"]:                             # pulse sweep
            step = c["pws"] - 256 if c["pws"] & 0x80 else c["pws"]
            c["pw"] = (c["pw"] + step) & 0xFFFF
            if ((c["pw"] >> 8) - 2) & 255 >= 12:
                c["pws"] = (-c["pws"]) & 255

    def tick(self):
        for c in self.ch:
            self.channel(c)
        if self.cut_spd:
            step = self.cut_spd - 256 if self.cut_spd & 0x80 else self.cut_spd
            self.cut = max(CUT_MIN, min(CUT_MAX, self.cut + step))
        return self.state()

    def state(self):
        return {"freq": [c["freq"] for c in self.ch], "ctrl": [c["ctrl"] for c in self.ch],
                "pw": [c["pw"] & 0xFFFF for c in self.ch], "ad": [c["ad"] for c in self.ch],
                "sr": [c["sr"] for c in self.ch], "note": [c["note"] for c in self.ch],
                "gate": [c["gate"] for c in self.ch], "flt": [c["flt"] for c in self.ch],
                "cut": self.cut, "res": self.res}


def main():
    try:
        song = load_all()
    except MusicError as e:
        print(f"mkmusic64: {e}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(asm_source(song))
    secs = ", ".join(f"{t['name']} {sum(t['ticks']) / 50:.0f} s" for t in song.tunes)
    print(f"mkmusic64: {len(song.tunes)} tunes ({secs}), {len(song.ins)} instruments, "
          f"{len(song.patterns)} patterns, {len(song.effects)} effects, {data_size(song)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
