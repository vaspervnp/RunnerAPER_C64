"""Reference model of the world generator (src/world.asm), a line by line port
of the CPC's generate_row (APERRunner src/world.asm, src/chunk_pick.asm).

Every decision that draws a random number is the CPC's, in the same order,
so a seed gives the same world. What the C64 leaves out: moving trains (all
trains stand) and moving cars; what it draws differently: scenery (cars,
trees, bushes) becomes side tiles instead of overlays (side_tile below).

    World(skill).generate(n)   rows 0, 1, 2, ... in order; returns the descriptor
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets64 as A  # noqa: E402
import mklevel64 as L  # noqa: E402

# descriptor
ROW_SIZE = 16
RING_ROWS = 64
D_FLAGS, D_LEFT, D_RIGHT, D_LANES, D_COLL, D_ITEM, D_PLAT = 0, 1, 2, 3, 6, 9, 12
F_FOREST, F_STATION, F_PLATFORM, F_BRIDGE = 0x01, 0x02, 0x10, 0x80

COL_NONE, COL_STOP, COL_SIGNAL, COL_TRAIN, COL_NOSE, COL_RAMP_UP, COL_RAMP_DOWN, COL_GAP = range(8)
ITEM_COIN, ITEM_MAGNET, ITEM_TURBO, ITEM_SLOW, ITEM_SPRING, ITEM_HELMET, ITEM_TICKET = range(1, 8)
PU_KINDS = (ITEM_MAGNET, ITEM_SLOW, ITEM_SPRING, ITEM_HELMET, ITEM_TICKET)

SEGMENT_MIN = 96
BRIDGE_GAP_MIN = 80
SCENERY_MARGIN = 6
SPACER_START = 24
SPACER_STEPS = (96, 40, 24)
SPACER_FEWEST = (8, 0, 0)
ROUTE_SEG = 320
ROUTE_STATIONS = 7
PU_GAP_MIN = 50
PU_GAP_RANGE = 70
PU_CLEAR = 8
PU_TURBO_ODDS = 77
CAR_QUIET_ROWS = 12
SCENERY_W_MAX = 20
EASY_WINDOW = 34                    # the CPC's picture: a screen there
PLAT_ROWS = 22

COIN_W, POWERUP_W, CAR_W = 4, 6, 4
TREE_INFO = ((8, 3), (12, 3), (4, 3), (4, 1), (4, 1))      # pine, oak, cypress, bush, rock (bytes, rows)
LANE_ORDERS = ((0, 1, 2), (2, 1, 0), (1, 0, 2), (0, 2, 1), (1, 2, 0), (2, 0, 1))

# the CPC's platform rows (assets.PLATFORM_SEQ), by D_PLAT, as C64 side tiles
_PLAT = {"end_lo": "plat_end", "end_hi": "plat_end", "plain": "plat_plain", "bench": "plat_bench",
         "sign": "plat_sign", "roof": "plat_roof", "roof_lo": "plat_roof"}
PLATFORM_SEQ = [None, "end_hi", "plain", "bench", "plain", "plain", "bench", "plain",
                "roof", "sign", "roof", "roof", "sign", "roof", "roof_lo",
                "plain", "bench", "plain", "end_lo", None, None, None, None]
PLATFORM_TILE = [None if k is None else A.SIDE_KINDS.index(_PLAT[k]) for k in PLATFORM_SEQ]

S = {name: i for i, name in enumerate(A.SIDE_KINDS)}
B = {name: i for i, name in enumerate(A.BRIDGE_ROWS)}
FOOTBRIDGE = [B[n] for n in A.FOOTBRIDGE_ROWS]
ROADBRIDGE = [B[n] for n in A.ROADBRIDGE_ROWS]
RAIL_A = A.TRACK_TILES.index("rail_a")


class World:
    def __init__(self, skill=0, chunks=None, seed=0xACE1):
        self.skill = skill
        self.chunks = chunks if chunks is not None else L.load_all()
        self.ring = [[0] * ROW_SIZE for _ in range(RING_ROWS)]
        self.rng = seed
        self.overlays = []                   # [top row, width]
        self.scenery_width = 0
        self.plat_left = 0
        self.gen_row = 0
        self.pu_gap = PU_GAP_MIN
        self.spacer_len = SPACER_START
        self.spacer_left = SPACER_START
        self.spacer_tick = 0
        self.spacer_step()
        self.difficulty = 0
        self.env = 0
        self.seg_left = SEGMENT_MIN
        self.trans_left = 0
        self.chunk_left = 0
        self.chunk = None
        self.chunk_row_index = 0
        self.bridge_left = 0
        self.bridge_rows = []
        self.bridge_countdown = BRIDGE_GAP_MIN // 2
        self.cross_countdown = 24
        self.cross_phase = 0
        self.kiosk_countdown = [30, 50]
        self.kiosk_phase = [0, 0]
        self.path_left = [0, 0]
        self.fence_left = [0, 0]
        self.route_left = ROUTE_SEG
        self.route_station = 0
        self.car_busy = [0] * 6
        self.tree_busy = [0] * 2
        self.car_recent = [0] * 6
        # chunk_pick state (survives games on the CPC; set by every pick)
        self.pick_cache = [None, None]       # per env: (difficulty, weights, total)
        self.chunk_lanes = [0, 1, 2]
        self.chunk_src = [0, 1, 2]
        self.livery = 0
        self.roofs_reachable = False
        self.ez_obj = [0, 0, 0]
        self.ez_starts = [[0, 0] for _ in range(3)]
        self.pu_roof = 0
        # C64: what the sides show (scenery as tiles), per side
        self.side_objects = [[], []]         # tile indices still to come, bottom first
        self.cars_shown = [[], []]

    # --- random ------------------------------------------------------------
    def random(self):
        """xorshift16 (7, 9, 8) as the CPC's Z80 code: returns the new high byte."""
        h, l = self.rng >> 8, self.rng & 0xFF
        h ^= ((h & 1) << 7) | (l >> 1)
        l ^= ((l & 1) << 7) | (h >> 1)
        h ^= l
        self.rng = (h << 8) | l
        return h

    def random_below(self, c):
        return self.random() % c

    def desc(self, row):
        return self.ring[row & (RING_ROWS - 1)]

    # --- generate_row ---------------------------------------------------------
    def generate(self, n):
        self.gen_row = n
        d = self.desc(n)
        d[:] = [0] * ROW_SIZE
        self.d = d
        self.objects_started = [None, None]

        hl, de = n, n >> 1
        a = hl >> 8
        for _ in range(self.skill):
            hl += de
            if hl > 0xFFFF:
                a = None
                break
            a = hl >> 8
        if a is None:
            self.difficulty = 5
        else:
            a = (a + 1) & 0xFF
            self.difficulty = a if a < 6 else 5

        self.spacer_tick = (self.spacer_tick - 1) & 0xFF
        if self.spacer_tick == 0:
            self.spacer_step()

        for counters in (self.car_busy, self.tree_busy, self.car_recent):
            for i, v in enumerate(counters):
                if v:
                    counters[i] = v - 1
        self.route_left = (self.route_left - 1) & 0xFFFF
        if self.route_left == 0:
            d[D_FLAGS] |= F_STATION
            self.plat_left = PLAT_ROWS
            self.route_station = self.route_station + 1 if self.route_station + 1 < ROUTE_STATIONS - 1 else 0
            self.route_left = ROUTE_SEG
        if self.pu_gap:
            self.pu_gap -= 1
        if self.plat_left:
            d[D_PLAT] = self.plat_left
            self.plat_left -= 1
            d[D_FLAGS] |= F_PLATFORM
            self.car_busy = [1] * 6
            self.tree_busy = [1] * 2

        self.base = [0, 0]
        if self.trans_left:
            self.transition_sides()
        else:
            self.seg_left = (self.seg_left - 1) & 0xFFFF
            if self.seg_left == 0:
                self.trans_left = 2
                self.seg_left = (self.random() & 63) + SEGMENT_MIN
            if self.env == 0:
                self.urban_sides()
            else:
                self.forest_sides()

        if self.bridge_countdown:
            self.bridge_countdown -= 1
        if self.bridge_left:
            self.bridge_row()
        elif self.chunk_left:
            self.chunk_row()
        elif self.spacer_left:
            self.spacer_row()
        elif self.bridge_countdown == 0:
            self.start_bridge()
        else:
            self.pick_chunk()
            a = self.spacer_len
            if self.pu_gap == 0 and a < PU_CLEAR * 2 + 1:
                a = PU_CLEAR * 2 + 1
            self.spacer_left = a
            self.chunk_row()

        self.side_tiles()
        # render_row: overlays whose top row this is are done
        for ov in [o for o in self.overlays if o[0] <= n]:
            self.overlays.remove(ov)
            self.scenery_width = (self.scenery_width - ov[1]) & 0xFF
        return list(d)

    def spacer_step(self):
        self.spacer_tick = SPACER_STEPS[self.skill]
        if SPACER_FEWEST[self.skill] < self.spacer_len:
            self.spacer_len -= 1

    # --- overlays -------------------------------------------------------------
    def add_overlay(self, width, rows):
        if len(self.overlays) >= 16:
            return False
        self.overlays.append([self.gen_row + rows - 1, width])
        self.scenery_width = (self.scenery_width + width) & 0xFF
        return True

    def add_scenery(self, width, rows):
        if self.scenery_width + width > SCENERY_W_MAX:
            return False
        return self.add_overlay(width, rows)

    def scenery_allowed(self, c):
        if self.trans_left or self.bridge_left:
            return False
        for v in (self.seg_left, self.bridge_countdown):
            if v >> 8 == 0:
                a = (v & 0xFF) - SCENERY_MARGIN
                if a < 0 or a < c:
                    return False
        return True

    # --- sides -----------------------------------------------------------------
    def transition_sides(self):
        self.d[D_FLAGS] |= F_FOREST
        kind = "trans_uf" if self.env == 0 else "trans_fu"
        tile = S[f"{kind}_{0 if self.trans_left == 2 else 1}"]
        self.base = [tile, tile]
        self.trans_left -= 1
        if self.trans_left == 0:
            self.env ^= 1

    def urban_sides(self):
        road = S["road_a"] if self.gen_row & 1 == 0 else S["road_b"]
        self.base = [road, road]
        crossing = bool(self.cross_phase)
        if not crossing:
            self.cross_countdown = (self.cross_countdown - 1) & 0xFF
            if self.cross_countdown == 0:
                self.cross_countdown = (self.random() & 63) + 40
                self.cross_phase = 2
                crossing = True
        if crossing:
            a = self.cross_phase
            self.cross_phase -= 1
            tile = S["road_cross_0"] if a == 2 else S["road_cross_1"]
            self.base = [tile, tile]
        else:
            self.kiosk(0)
            self.kiosk(1)
        self.spawn_car(0)
        self.spawn_car(1)

    def kiosk(self, b):
        if not self.kiosk_phase[b]:
            self.kiosk_countdown[b] = (self.kiosk_countdown[b] - 1) & 0xFF
            if self.kiosk_countdown[b]:
                return
            self.kiosk_countdown[b] = 40
            if self.car_busy[b * 3]:
                return
            self.car_busy[b * 3] = 3
            self.kiosk_countdown[b] = (self.random() & 127) + 60
            self.kiosk_phase[b] = 2
        a = self.kiosk_phase[b]
        self.kiosk_phase[b] -= 1
        self.base[b] = S["kiosk_0"] if a == 2 else S["kiosk_1"]

    def spawn_car(self, b):
        if self.random() & 7:
            return
        if not self.scenery_allowed(4):
            return
        lane = self.random_below(3)
        idx = b * 3 + lane
        if self.car_busy[idx]:
            return
        a = self.random() & 7
        rows = 4 if a in (0, 1) else 2       # bus, trolley; else a car
        self.car_busy[idx] = (self.random() & 3) + rows + 1
        self.car_recent[idx] = CAR_QUIET_ROWS
        if self.add_scenery(CAR_W, rows):
            self.objects_started[b] = ("car", rows)

    def forest_sides(self):
        self.d[D_FLAGS] |= F_FOREST
        self.forest_side(0)
        self.forest_side(1)
        self.spawn_tree(0)
        self.spawn_tree(1)

    def forest_side(self, b):
        if self.path_left[b]:
            self.path_left[b] -= 1
            self.base[b] = S["path"]
            return
        if self.fence_left[b]:
            self.fence_left[b] -= 1
            self.base[b] = S["fence"]
            return
        if self.random() & 31 == 0:
            c = (self.random() & 3) + 3
            if self.random() & 1:
                self.path_left[b] = c
            else:
                self.fence_left[b] = c
        self.base[b] = S["ground_a"] if self.random() & 2 == 0 else S["ground_b"]

    def spawn_tree(self, b):
        if self.tree_busy[b]:
            return
        if self.random() & 3:
            return
        if not self.scenery_allowed(3):
            return
        k = self.random_below(5)
        width, rows = TREE_INFO[k]
        self.tree_busy[b] = rows + 1
        self.random_below(15 - width)        # its column on the CPC
        if self.add_scenery(width, rows):
            self.objects_started[b] = ("tree", rows)

    def side_tiles(self):
        """C64: the side tiles of the row - a platform, else scenery started
        here or still going (a tree, a car), else the ground or the road."""
        d = self.d
        for b in (0, 1):
            started = self.objects_started[b]
            if started and not self.side_objects[b]:
                kind, rows = started
                if kind == "tree":
                    seq = ["tree_0", "tree_1", "tree_2"] if rows == 3 else ["bush"]
                else:
                    seq = ["car_0", "car_1"] * (rows // 2)
                self.side_objects[b] = [S[t] for t in seq]
            tile = self.base[b]
            if self.side_objects[b]:
                tile = self.side_objects[b].pop(0)
            plat = PLATFORM_TILE[d[D_PLAT]] if d[D_PLAT] < len(PLATFORM_TILE) else None
            if plat is not None:
                tile = plat
            if b == 0 and d[D_FLAGS] & F_BRIDGE:
                continue                     # D_LEFT holds the bridge row
            d[D_LEFT + b] = tile

    # --- bridges ---------------------------------------------------------------
    def start_bridge(self):
        self.bridge_countdown = (self.random() & 127) + BRIDGE_GAP_MIN
        rows = FOOTBRIDGE
        if self.env == 0 and self.random() & 1:
            rows = ROADBRIDGE
        self.bridge_rows = list(rows)
        self.bridge_left = len(rows)
        self.bridge_row()

    def bridge_row(self):
        d = self.d
        d[D_LEFT] = self.bridge_rows[len(self.bridge_rows) - self.bridge_left]
        d[D_FLAGS] |= F_BRIDGE
        d[D_LANES:D_LANES + 3] = [RAIL_A] * 3
        self.bridge_left -= 1

    # --- chunks ----------------------------------------------------------------
    def weigh_env(self, env):
        weights = []
        for c in self.chunks:
            ok = self.difficulty >= c["diff"] and (c["env"] == 0 or c["env"] - 1 == env)
            weights.append(c["weight"] if ok else 0)
        total = sum(weights) & 0xFF or 1
        self.pick_cache[env] = (self.difficulty, weights, total)

    def pick_chunk(self):
        if self.gen_row < SPACER_START + 1:
            self.pick_cache = [None, None]
            self.ez_obj = [0, 0, 0]
            old = (self.gen_row - 1000) & 0xFFFF
            self.ez_starts = [[old, old] for _ in range(3)]
        cache = self.pick_cache[self.env]
        if cache is None or cache[0] != self.difficulty:     # (the CPC's prewarm keeps it current)
            self.weigh_env(self.env)
        _, weights, total = self.pick_cache[self.env]
        a = self.random_below(total)
        chosen = 0
        for i, w in enumerate(weights):
            if a < w:
                chosen = i
                break
            a -= w
        c = self.chunks[chosen]
        self.chunk = c
        self.chunk_row_index = 0
        self.chunk_left = len(c["rows"])
        self.roofs_reachable = bool(c["ramp"])
        k = self.random_below(2 if c["side_by_side"] else 6)
        self.chunk_lanes = list(LANE_ORDERS[k])
        for i, lane in enumerate(self.chunk_lanes):
            self.chunk_src[lane] = i
        self.livery = self.random_below(3)

    def chunk_cells(self, index):
        return self.chunk["rows"][index]

    def chunk_row(self):
        d = self.d
        cells = self.chunk_cells(self.chunk_row_index)
        for k in range(3):
            lane = self.chunk_lanes[k]
            tile, coll, item = cells[k * 3:k * 3 + 3]
            if self.skill == 0 and self.easy_cell(lane, coll):
                d[D_LANES + lane] = RAIL_A
                d[D_COLL + lane] = COL_NONE
                d[D_ITEM + lane] = 0
                continue
            d[D_LANES + lane] = L.livery_tile(tile, self.livery)
            d[D_COLL + lane] = coll
            d[D_ITEM + lane] = item
            if item:
                self.spawn_item(item)
        self.chunk_row_index += 1
        self.place_powerup()
        self.chunk_left -= 1

    def easy_cell(self, lane, coll):
        """True: the cell becomes rail (a third stop/signal within EASY_WINDOW rows)."""
        c = coll & 15
        if c == 0 or (c >= COL_RAMP_UP and c != COL_GAP):
            self.ez_obj[lane] = 0
            return False
        if self.ez_obj[lane] & 1:
            return bool(self.ez_obj[lane] & 2)
        self.ez_obj[lane] = 1
        newer, older = self.ez_starts[lane]
        if c < COL_TRAIN and (self.gen_row - older) & 0xFFFF < EASY_WINDOW:
            self.ez_obj[lane] = 3
            return True
        self.ez_starts[lane] = [self.gen_row, newer]
        return False

    def spacer_row(self):
        self.spacer_left -= 1
        b = self.spacer_left
        self.d[D_LANES:D_LANES + 3] = [RAIL_A] * 3
        if self.pu_gap or b < PU_CLEAR:
            return
        lane = self.random_below(3)
        self.pu_roof = 0
        if not self.clear_behind(lane):
            return
        self.put_powerup(lane)

    # --- power-ups ---------------------------------------------------------------
    def obstacle(self, coll):
        a = coll & 15
        if self.pu_roof == 0:
            if a == 0:
                return False
            if a == COL_GAP:
                return True
            return a < COL_RAMP_UP
        if a == COL_TRAIN:
            return False
        return a < COL_RAMP_UP

    def clear_behind(self, lane):
        for k in range(1, PU_CLEAR + 1):
            if self.obstacle(self.desc(self.gen_row - k)[D_COLL + lane]):
                return False
        return True

    def place_powerup(self):
        if self.pu_gap:
            return
        a = (self.chunk_left - 1) & 0xFF
        if a == 0:
            return
        if self.spacer_len + a < PU_CLEAR:
            return
        check = min(a, PU_CLEAR)
        lane = self.random_below(3)
        nxt = self.chunk_row_index           # the chunk's next row
        for _ in range(3):
            d = self.d
            ok = d[D_ITEM + lane] == 0
            if ok:
                c = d[D_COLL + lane] & 15
                if c == 0:
                    self.pu_roof = 0
                elif c == COL_TRAIN and self.roofs_reachable:
                    self.pu_roof = c
                else:
                    ok = False
            if ok and not self.clear_behind(lane):
                ok = False
            if ok:
                src = self.chunk_src[lane]
                row = self.chunk_cells(nxt)
                if row[src * 3 + 2]:
                    ok = False
                elif self.pu_roof and row[src * 3 + 1] & 15 != COL_TRAIN:
                    ok = False
                else:
                    for i in range(check):
                        if self.obstacle(self.chunk_cells(nxt + i)[src * 3 + 1]):
                            ok = False
                            break
            if ok:
                self.put_powerup(lane)
                return
            lane = lane + 1 if lane < 2 else 0

    def put_powerup(self, lane):
        if self.random() < PU_TURBO_ODDS:
            item = ITEM_TURBO
        else:
            while True:
                r = self.random() & 7
                if r < 5:
                    break
            item = PU_KINDS[r]
        self.d[D_ITEM + lane] = item
        self.spawn_item(item)
        self.pu_gap = self.random_below(PU_GAP_RANGE + 1) + PU_GAP_MIN

    def spawn_item(self, item):
        if item == ITEM_COIN:
            self.add_overlay(COIN_W, 1)
        else:
            self.add_overlay(POWERUP_W, 2)


def generate(rows, skill=0, seed=0xACE1):
    """[descriptor] for world rows 0 .. rows-1."""
    w = World(skill, seed=seed)
    return [w.generate(n) for n in range(rows)]


if __name__ == "__main__":
    import collections
    rows = generate(4000, int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print("bridges", sum(1 for d in rows if d[D_FLAGS] & F_BRIDGE),
          "forest", sum(1 for d in rows if d[D_FLAGS] & F_FOREST),
          "stations", sum(1 for d in rows if d[D_FLAGS] & F_STATION))
    print("items", collections.Counter(i for d in rows for i in d[D_ITEM:D_ITEM + 3]))
    print("sides", collections.Counter(A.SIDE_KINDS[d[D_LEFT]] for d in rows if not d[D_FLAGS] & F_BRIDGE))
