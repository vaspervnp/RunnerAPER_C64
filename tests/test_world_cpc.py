"""Phase 3: the world model (tools/worldgen.py) against the real CPC game.

Runs the CPC version (../APERRunner, its headless emulator ~/cpcemu) on easy
and reads its row descriptors as it generates them: the C64's world must be
the same - track, collisions, items, environment, bridges, stations,
platforms and the sides' ground - row for row. (Easy: the CPC moves no
trains there either; its moving cars are switched off, see setUpClass.
The C64 tests compare the C64 with the model.)

The CPC is the commit CPC_COMMIT of ../APERRunner (or CPC_ROOT, a built
copy). Skipped when the CPC repository, its build or the emulator are
missing.
"""

import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# The CPC version the C64's world is a port of: its repository goes on (and
# its working tree changes), so the comparison is with this commit, taken
# out with git archive (the repository is only read) and built in build/.
CPC_REPO = os.path.join(os.path.dirname(ROOT), "APERRunner")
CPC_COMMIT = "1175278"


def pinned_cpc():
    """build/cpc-<commit>, extracted and built once; None if that fails"""
    out = os.path.join(ROOT, "build", f"cpc-{CPC_COMMIT}")
    if os.path.exists(os.path.join(out, "build", "runner.dsk")):
        return out
    try:
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        archive = subprocess.run(["git", "-C", CPC_REPO, "archive", CPC_COMMIT], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", out], input=archive.stdout, check=True)
        subprocess.run(["make"], cwd=out, capture_output=True, check=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    return out


CPC_ROOT = os.environ.get("CPC_ROOT") or pinned_cpc() or CPC_REPO
CPC_TESTS = os.path.join(CPC_ROOT, "tools", "tests")
CPC_DSK = os.path.join(CPC_ROOT, "build", "runner.dsk")
CPCEMU = os.environ.get("CPCEMU", os.path.expanduser("~/cpcemu"))

sys.path.insert(0, os.path.join(ROOT, "tools"))
import assets64 as A  # noqa: E402
import worldgen as W  # noqa: E402
import mklevel64 as L  # noqa: E402

ROWS = int(os.environ.get("CPC_ROWS", "1600"))

# the CPC's tables (its tools/assets.py), by index
CPC_TRACK = (["rail_a", "rail_b", "stop_0", "stop_1", "signal_0", "signal_1"]
             + [f"wagon{t}_{p}" for t in (1, 2, 3) for p in ("end_bottom", "body_a", "body_b", "end_top", "coupler")]
             + [f"loco{t}_{p}" for t in (1, 2, 3) for p in ("nose", "body", "pantograph", "nose_top")]
             + [f"ramp_up_{i}" for i in range(3)] + [f"ramp_down_{i}" for i in range(3)])
CPC_URBAN = ["road_a", "road_b", "road_cross_0", "road_cross_1", "kiosk_0", "kiosk_1"]
CPC_FOREST = ["ground_a", "ground_b", "path", "fence", "trans_uf_0", "trans_uf_1", "trans_fu_0", "trans_fu_1"]
CPC_BRIDGES = ([f"footbridge_{i}" for i in range(3)] + ["footbridge_shadow"]
               + [f"roadbridge_{i}" for i in range(6)] + ["roadbridge_shadow"])
WORLD_RING = 0x0400
FLAGS = W.F_FOREST | W.F_STATION | W.F_PLATFORM | W.F_BRIDGE


def c64_livery(name):
    """CPC tile name -> the C64's (liveries 1-3 drawn as 1-2)."""
    for kind in ("wagon", "loco"):
        if name.startswith(kind):
            return f"{kind}{(int(name[len(kind)]) - 1) % 2 + 1}{name[len(kind) + 1:]}"
    return name


def available():
    return all(os.path.exists(p) for p in (CPC_TESTS, CPC_DSK, os.path.join(CPCEMU, "cpc.py")))


@unittest.skipUnless(available(), "CPC version or ~/cpcemu not found")
class CpcWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, CPC_TESTS)
        import harness
        cls.harness = harness
        sym = harness.load_symbols()
        try:
            cpc = harness.boot_game(menu=True)
        except AssertionError as e:          # its build is not runnable right now
            raise unittest.SkipTest(f"the CPC build at {CPC_ROOT} does not start ({e}); "
                                    "rebuild it there, or point CPC_ROOT at a built copy")
        # The C64 has no moving cars. On the CPC a moving car keeps its lane
        # busy every frame (move_cars), which changes later random draws by
        # timing: switched off here (RET at start_mover), the logic is the same.
        cpc.write_ram(sym["start_mover"], bytes([0xC9]))
        harness.start_from_menu(cpc, sym)
        cpc.write_ram(sym["no_crash"], bytes([1]))
        cpc.write_ram(sym["no_pickups"], bytes([1]))
        rows = {}
        last = -1
        while last < ROWS:
            cpc.run_frames(16)
            gen = harness.peek16(cpc, sym["gen_row"])
            ring = cpc.read_ram(WORLD_RING, 64 * 16)
            for n in range(max(0, gen - 40), gen):      # gen itself may be half made
                if n not in rows:
                    rows[n] = list(ring[(n & 63) * 16:(n & 63) * 16 + 16])
            last = gen
        cls.cpc_rows = rows
        model = W.World(0, chunks=L.load_all(c64=False))   # the CPC's chunks
        cls.model = {n: model.generate(n) for n in range(last + 1)}

    def test_same_world(self):
        mismatches = []
        for n in sorted(self.cpc_rows):
            c, m = self.cpc_rows[n], self.model[n]
            where = f"row {n}"
            got = dict(flags=c[0] & FLAGS, coll=c[6:9], items=c[9:12], plat=c[12],
                       lanes=[c64_livery(CPC_TRACK[t]) for t in c[3:6]])
            want = dict(flags=m[0] & FLAGS, coll=m[6:9], items=m[9:12], plat=m[12],
                        lanes=[A.TRACK_TILES[t] for t in m[3:6]])
            if c[0] & W.F_BRIDGE or m[0] & W.F_BRIDGE:
                got["bridge"] = CPC_BRIDGES[c[1]] if c[0] & W.F_BRIDGE else None
                want["bridge"] = A.BRIDGE_ROWS[m[1]] if m[0] & W.F_BRIDGE else None
            else:
                table = CPC_FOREST if c[0] & W.F_FOREST else CPC_URBAN
                for side in (0, 1):
                    c64 = A.SIDE_KINDS[m[1 + side]]
                    if c64.startswith(("car", "tree", "bush", "plat")):
                        continue                 # scenery and platforms: drawn differently
                    got[f"side{side}"] = table[c[1 + side] // 2]
                    want[f"side{side}"] = c64
            if got != want:
                mismatches.append(f"{where}: CPC {got} / model {want}")
        print(f"\n  {len(self.cpc_rows)} rows compared with the CPC")
        self.assertFalse(mismatches, "\n".join(mismatches[:10]))


if __name__ == "__main__":
    unittest.main()
