"""What a world row should look like on the C64 screen, from its descriptor
and the converted graphics (tools/png2c64.py), and the model's rows."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import assets64 as A  # noqa: E402
import png2c64 as P  # noqa: E402
import worldgen as W  # noqa: E402

_cs, _sheets = P.convert_chars()
COIN_RAIL = P.coin_code(_sheets, "coin_rail")
COIN_ROOF = P.coin_code(_sheets, "coin_roof")


def _chars(sheet, index):
    name = A.CHAR_SHEETS[sheet]["frames"][index][0]
    return list(_sheets[sheet][name]["chars"][0])


def row_chars(desc):
    """40 character codes of a descriptor."""
    if desc[W.D_FLAGS] & W.F_BRIDGE:
        return _chars("bridges", desc[W.D_LEFT])
    out = _chars("side_l", desc[W.D_LEFT])
    for lane in range(3):
        tile = _chars("track", desc[W.D_LANES + lane])
        if desc[W.D_ITEM + lane] == W.ITEM_COIN:
            tile[A.COIN_COL] = COIN_ROOF if desc[W.D_COLL + lane] & 15 == W.COL_TRAIN else COIN_RAIL
        out += tile
    return out + _chars("side_r", desc[W.D_RIGHT])


_model = {}


def model_rows(rows, skill=0):
    """Descriptors of world rows 0 .. rows-1 (cached per skill)."""
    have = _model.get(skill)
    if have is None or len(have[1]) < rows:
        world = W.World(skill)
        _model[skill] = (world, [world.generate(n) for n in range(rows)])
    return _model[skill][1]
