"""Compiles track chunks (levels/chunks/*.txt, the CPC's own) into src/data/chunks.asm.

The chunk format, its rules and checks are those of the CPC's tools/mklevel.py
(see the docstring there; levels/chunks is a copy). What differs is the
output: 64tass, and track tiles.

Chunk cells keep the CPC's *virtual* track tile numbers (3 liveries, 39
tiles), so the data and its random livery shift are the CPC's. The C64 has
2 liveries: livery_tiles maps (shift, virtual tile) to the C64 tile, livery
(L + shift) mod 3 drawn as livery 1 or 2.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets64 as A  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHUNK_DIR = os.path.join(ROOT, "levels", "chunks")
OUT = os.path.join(ROOT, "src", "data", "chunks.asm")

# the CPC's track tiles (tools/assets.py there): the chunks' tile numbers
CPC_TRAINS = (1, 2, 3)
WAGON_PARTS = ("end_bottom", "body_a", "body_b", "end_top", "coupler")
LOCO_PARTS = ("nose", "body", "pantograph", "nose_top")
VIRTUAL_TILES = (
    ["rail_a", "rail_b", "stop_0", "stop_1", "signal_0", "signal_1"]
    + [f"wagon{t}_{p}" for t in CPC_TRAINS for p in WAGON_PARTS]
    + [f"loco{t}_{p}" for t in CPC_TRAINS for p in LOCO_PARTS]
    + [f"ramp_up_{i}" for i in range(3)]
    + [f"ramp_down_{i}" for i in range(3)]
)
TILE = {name: i for i, name in enumerate(VIRTUAL_TILES)}
C64_TILE = {name: i for i, name in enumerate(A.TRACK_TILES)}
WAGON_TILES, LOCO_TILES = len(WAGON_PARTS), len(LOCO_PARTS)

COL_NONE, COL_STOP, COL_SIGNAL, COL_TRAIN, COL_NOSE, COL_RAMP_UP, COL_RAMP_DOWN, COL_GAP = range(8)
ITEMS = {".": 0, "c": 1}
ENVS = {"any": 0, "urban": 1, "forest": 2}

WAGON_ROWS = 12
LOCO_ROWS = 12
MIN_WAGONS = 2
MIN_COIN_RUN = 3
MAX_COIN_RUN = 10
COIN_STEP = 2
RAMP_ROOF_SHARE = 0.6
BLOCK_ROWS = 12
RAMP_KINDS = ("coins", "blocked")


def train_length(wagons):
    return LOCO_ROWS + wagons * (1 + WAGON_ROWS)


def livery_name(name, shift):
    """Virtual tile name -> the C64 tile name with the livery moved on by shift."""
    for kind in ("wagon", "loco"):
        if name.startswith(kind):
            livery = int(name[len(kind)])
            c64 = (livery - 1 + shift) % 3 % len(A.TRAIN_TYPES) + 1
            return f"{kind}{c64}{name[len(kind) + 1:]}"
    return name


def livery_tile(tile, shift):
    """Virtual tile index -> C64 tile index (shift 0-2)."""
    return C64_TILE[livery_name(VIRTUAL_TILES[tile], shift)]


class LevelError(Exception):
    pass


def parse(path):
    header, grid = {}, []
    with open(path) as f:
        for number, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("#"):
                if ":" in line:
                    key, value = line[1:].split(":", 1)
                    header[key.strip()] = value.strip()
                continue
            cells = line.split()
            if len(cells) != 3 or any(len(c) != 3 for c in cells):
                raise LevelError(f"{path}:{number}: expected 3 cells of 3 characters, got {line!r}")
            grid.append((number, cells))
    if not grid:
        raise LevelError(f"{path}: empty chunk")
    return header, list(reversed(grid))        # bottom row first


def _runs(column):
    runs, start = [], 0
    for i in range(1, len(column) + 1):
        if i == len(column) or column[i][:2] != column[start][:2]:
            runs.append((start, i - start, column[start][0], column[start][1]))
            start = i
    return runs


def resolve_lane(path, column, lane):
    """column: cells bottom to top -> [(virtual tile, collision)]"""
    out = [None] * len(column)
    for start, length, obj, t in _runs(column):
        rows = range(start, start + length)
        where = f"lane {lane + 1}, rows {start}-{start + length - 1} from the bottom"
        if obj == ".":
            for r in rows:
                out[r] = (TILE["rail_b" if (r * 7 + lane * 3) % 11 == 0 else "rail_a"], COL_NONE)
        elif obj in "TR":
            if t not in "123":
                raise LevelError(f"{path}: {where}: train cells need a livery 1-3, got {t!r}")
            tt = int(t)
            wagons, rest = divmod(length - LOCO_ROWS, 1 + WAGON_ROWS)
            if length < LOCO_ROWS or rest or wagons < MIN_WAGONS:
                valid = ", ".join(str(train_length(k)) for k in range(MIN_WAGONS, MIN_WAGONS + 3))
                raise LevelError(f"{path}: {where}: a train needs a locomotive and at least {MIN_WAGONS} wagons: "
                                 f"{length} rows, valid lengths are {valid}, ...")
            parts = []
            wagon = ([f"wagon{tt}_end_bottom"]
                     + [f"wagon{tt}_body_{'a' if k % 3 == 1 else 'b'}" for k in range(WAGON_ROWS - 2)]
                     + [f"wagon{tt}_end_top"])
            if obj == "T":
                parts += ([(f"loco{tt}_nose", COL_NOSE)]
                          + [(f"loco{tt}_{'pantograph' if k in (2, LOCO_ROWS - 4) else 'body'}", COL_TRAIN)
                             for k in range(1, LOCO_ROWS - 1)]
                          + [(f"wagon{tt}_end_top", COL_TRAIN)])
                for _ in range(wagons):
                    parts += [(f"wagon{tt}_coupler", COL_GAP)] + [(n, COL_TRAIN) for n in wagon]
            else:
                for _ in range(wagons):
                    parts += [(n, COL_TRAIN) for n in wagon] + [(f"wagon{tt}_coupler", COL_GAP)]
                parts += ([(f"wagon{tt}_end_bottom", COL_TRAIN)]
                          + [(f"loco{tt}_{'pantograph' if k in (3, LOCO_ROWS - 3) else 'body'}", COL_TRAIN)
                             for k in range(1, LOCO_ROWS - 1)]
                          + [(f"loco{tt}_nose_top", COL_TRAIN)])
            for r, (name, collision) in zip(rows, parts):
                out[r] = (TILE[name], collision)
        elif obj in "^v":
            if length != 3:
                raise LevelError(f"{path}: {where}: ramps are exactly 3 rows")
            neighbour = start + 3 if obj == "^" else start - 1
            if not (0 <= neighbour < len(column)) or column[neighbour][0] not in "TR":
                raise LevelError(f"{path}: {where}: ramp {'up must sit below' if obj == '^' else 'down must sit above'} a train")
            for k, r in enumerate(rows):
                name = f"ramp_{'up' if obj == '^' else 'down'}_{k}"
                out[r] = (TILE[name], (COL_RAMP_UP if obj == "^" else COL_RAMP_DOWN) | (k << 4))
        elif obj == "S":
            if length != 2:
                raise LevelError(f"{path}: {where}: a buffer stop is exactly 2 rows")
            out[start] = (TILE["stop_0"], COL_STOP)
            out[start + 1] = (TILE["stop_1"], COL_STOP)
        elif obj == "F":
            if length != 2:
                raise LevelError(f"{path}: {where}: a signal is exactly 2 rows")
            out[start] = (TILE["signal_1"], COL_NONE)
            out[start + 1] = (TILE["signal_0"], COL_SIGNAL)
        else:
            raise LevelError(f"{path}: {where}: unknown object {obj!r}")
    return out


def coin_runs(column, path="", grid=None, lane=0):
    rows = [r for r, has in enumerate(column) if has]
    runs = []
    for r in rows:
        if runs and r - runs[-1][2] < COIN_STEP:
            line = grid[r][0] if grid else r
            raise LevelError(f"{path}: line {line}: coins on consecutive rows in lane {lane + 1} - "
                             f"leave an empty row between two coins")
        if runs and r - runs[-1][2] == COIN_STEP:
            runs[-1][1] += 1
            runs[-1][2] = r
        else:
            runs.append([r, 1, r])
    return [(start, count) for start, count, _ in runs]


def side_by_side(columns):
    return any(columns[a][r][0] in "TR^v" and columns[a + 1][r][0] in "TR^v"
               for a in (0, 1) for r in range(len(columns[0])))


def check_ramp(path, header, columns):
    ramp_lanes = [lane for lane in range(3) if any(cell[0] == "^" for cell in columns[lane])]
    kind = header.get("ramp")
    if not ramp_lanes:
        if kind:
            raise LevelError(f"{path}: 'ramp: {kind}' without a ramp up")
        return None
    if kind not in RAMP_KINDS:
        raise LevelError(f"{path}: a chunk with a ramp up needs 'ramp: coins' or 'ramp: blocked'")
    coins = [(lane, r) for lane in range(3) for r, cell in enumerate(columns[lane]) if cell[2] == "c"]
    if kind == "coins":
        roof = [c for c in coins if columns[c[0]][c[1]][0] in "TR"]
        if len(roof) < RAMP_ROOF_SHARE * len(coins) or not coins:
            raise LevelError(f"{path}: 'ramp: coins' needs at least {RAMP_ROOF_SHARE:.0%} of the coins on "
                             f"the train roofs ({len(roof)} of {len(coins)})")
        return kind
    for lane in ramp_lanes:
        column = columns[lane]
        first = min(r for r, cell in enumerate(column) if cell[0] == "^")
        last = max(r for r, cell in enumerate(column) if cell[0] in "TR")
        for other in range(3):
            third = 3 - lane - other
            free = [r for r in range(first, last + 1)
                    if columns[other][r][0] not in "TR^v" and columns[third][r][0] not in "TRSF"]
            if other == lane or len(free) < BLOCK_ROWS:
                continue
            stops = sum(1 for r in free if columns[other][r][0] == "S") // 2
            if stops < len(free) // BLOCK_ROWS:
                raise LevelError(f"{path}: 'ramp: blocked' needs a buffer stop every {BLOCK_ROWS} rows in "
                                 f"lane {other + 1} next to the train ({stops} for {len(free)} rows)")
    return kind


def compile_chunk(path):
    header, grid = parse(path)
    name = header.get("chunk") or os.path.splitext(os.path.basename(path))[0]
    env = header.get("env", "any")
    if env not in ENVS:
        raise LevelError(f"{path}: env must be one of {', '.join(ENVS)}")
    diff = int(header.get("diff", 1))
    weight = int(header.get("weight", 1))
    if not 1 <= diff <= 5 or not 1 <= weight <= 15:
        raise LevelError(f"{path}: diff 1-5 and weight 1-15")
    columns = [[cells[lane] for _, cells in grid] for lane in range(3)]
    lanes = [resolve_lane(path, col, lane) for lane, col in enumerate(columns)]
    rows = []
    for r in range(len(grid)):
        row = []
        for lane in range(3):
            item_char = columns[lane][r][2]
            if item_char not in ITEMS:
                raise LevelError(f"{path}: line {grid[r][0]}: unknown item {item_char!r}")
            tile, collision = lanes[lane][r]
            row += [tile, collision, ITEMS[item_char]]
        for lane in range(3):
            if row[lane * 3 + 2] == ITEMS["c"] and row[lane * 3 + 1] == COL_GAP:
                raise LevelError(f"{path}: line {grid[r][0]}: a coin between two wagons (lane {lane + 1})")
        coin_lanes = sum(1 for lane in range(3) if row[lane * 3 + 2] == ITEMS["c"])
        if coin_lanes > 1:
            raise LevelError(f"{path}: line {grid[r][0]}: coins in {coin_lanes} lanes - a row has coins in one lane only")
        rows.append(row)
    for lane in range(3):
        for start, length in coin_runs([cell[2] == "c" for cell in columns[lane]], path, grid, lane):
            if not MIN_COIN_RUN <= length <= MAX_COIN_RUN:
                raise LevelError(f"{path}: line {grid[start][0]}: {length} coin(s) in lane {lane + 1} - "
                                 f"coins come in runs of {MIN_COIN_RUN} to {MAX_COIN_RUN}")
    ramp = check_ramp(path, header, columns)
    return {"name": name, "env": ENVS[env], "diff": diff, "weight": weight, "rows": rows, "ramp": ramp,
            "side_by_side": side_by_side(columns)}


def load_all():
    paths = sorted(glob.glob(os.path.join(CHUNK_DIR, "*.txt")))
    chunks = [compile_chunk(p) for p in paths]
    names = [c["name"] for c in chunks]
    if len(set(names)) != len(names):
        raise LevelError("chunk names must be unique")
    by_name = {c["name"]: c for c in chunks}
    for c in chunks:
        if c["ramp"] is None:
            continue
        suffix = "_" + c["ramp"]
        if not c["name"].endswith(suffix):
            raise LevelError(f"chunk {c['name']}: a 'ramp: {c['ramp']}' chunk is named <name>{suffix}")
        base = c["name"][:-len(suffix)]
        coins, blocked = by_name.get(base + "_coins"), by_name.get(base + "_blocked")
        if not coins or not blocked:
            raise LevelError(f"chunk {base}: ramp chunks come in pairs {base}_coins / {base}_blocked")
        if blocked["weight"] != 2 * coins["weight"] or (coins["env"], coins["diff"]) != (blocked["env"], blocked["diff"]):
            raise LevelError(f"chunk {base}: _blocked has twice the weight of _coins, same env and diff")
    return chunks


def env_byte(c):
    return c["env"] | (0x80 if c["side_by_side"] else 0) | (0x40 if c["ramp"] else 0)


def chunk_weights(chunks, difficulty, env):
    """The weight of each chunk at a difficulty in an environment (0 urban,
    1 forest): 0 if too early for it or of the other environment."""
    return [c["weight"] if difficulty >= c["diff"] and (c["env"] == 0 or c["env"] - 1 == env) else 0
            for c in chunks]


def asm_source(chunks):
    lines = ["; generated by tools/mklevel64.py from levels/chunks/ - do not edit",
             f"CHUNK_COUNT = {len(chunks)}",
             f"VTILE_WAGONS = {TILE['wagon1_end_bottom']}         ; virtual train tiles (CPC numbering)",
             f"VTILE_RAMPS = {TILE['ramp_up_0']}",
             "CHUNK_ENV = $3f",
             "CHUNK_RAMP = $40                  ; a ramp up: power-ups on the roofs too",
             "CHUNK_SIDE_BY_SIDE = $80          ; trains side by side: lane order kept or mirrored",
             "; chunk: rows, min difficulty, weight, env | ramp | side by side,",
             ";        then per row bottom to top: 3 x (virtual track tile, collision, item)",
             "chunk_lo",
             "        .byte " + ", ".join(f"<chunk_{c['name']}" for c in chunks),
             "chunk_hi",
             "        .byte " + ", ".join(f">chunk_{c['name']}" for c in chunks),
             "; virtual track tile -> C64 tile, livery moved on by 0, 1, 2 (64 each)",
             "        .align 256",
             "livery_tiles"]
    for shift in range(3):
        table = [livery_tile(t, shift) if t < len(VIRTUAL_TILES) else 0 for t in range(64)]
        for i in range(0, 64, 16):
            lines.append("        .byte " + ", ".join(str(v) for v in table[i:i + 16]))
    # the weights by difficulty (0-5) and environment (0 urban, 1 forest): the
    # CPC works them out while playing (weigh_env), here they are a table
    lines.append("; chunk weights by difficulty * 2 + environment, and their totals")
    lines.append("weights_lo")
    lines.append("        .byte " + ", ".join(f"<weights_{i}" for i in range(12)))
    lines.append("weights_hi")
    lines.append("        .byte " + ", ".join(f">weights_{i}" for i in range(12)))
    totals = []
    for diff in range(6):
        for env in range(2):
            w = chunk_weights(chunks, diff, env)
            totals.append(sum(w) & 0xFF or 1)
            lines.append(f"weights_{diff * 2 + env} .byte {', '.join(str(v) for v in w)}")
    lines.append("weights_total")
    lines.append("        .byte " + ", ".join(str(t) for t in totals))
    for c in chunks:
        lines.append(f"chunk_{c['name']}")
        lines.append(f"        .byte {len(c['rows'])}, {c['diff']}, {c['weight']}, ${env_byte(c):02x}")
        for row in c["rows"]:
            lines.append("        .byte " + ", ".join(str(v) for v in row))
    return "\n".join(lines) + "\n"


def main():
    try:
        chunks = load_all()
    except LevelError as e:
        print(f"mklevel64: {e}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(asm_source(chunks))
    size = sum(4 + 9 * len(c["rows"]) for c in chunks)
    print(f"mklevel64: {len(chunks)} chunks, {size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
