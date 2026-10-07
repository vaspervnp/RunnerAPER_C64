"""A small LZ packer for the boot file (src/boot.asm: unpack).

A byte-aligned stream of tokens:
    $00-$3f  n+1 literal bytes follow (1-64)
    $40-$7f  a near match: length (token & $3f) + 2 (2-65), then the
             distance back from the output - 1 (1 byte: 1-256)
    $80-$fe  a far match: length (token & $7f) + 3 (3-129), then the
             distance (2 bytes, little endian)
    $ff      the end
Parsed for the fewest bytes (dynamic programming over the longest near and
far match at each position).

    python3 tools/lz64.py in out     (prints the sizes)
"""

import sys

NEAR_MAX, NEAR_MIN, NEAR_DIST = 0x3F + 2, 2, 256
FAR_MAX, FAR_MIN = 0x7E + 3, 3
MAX_LIT = 64
FAR_CANDIDATES = 512
END = 0xFF


def match_len(data, i, j, lim):
    k = 0
    while k < lim and data[j + k] == data[i + k]:
        k += 1
    return k


def longest_matches(data):
    """for each position: (length, distance) of the longest near and far match"""
    n = len(data)
    near, far = [(0, 0)] * n, [(0, 0)] * n
    heads2, heads3 = {}, {}
    for i in range(n):
        if i + NEAR_MIN <= n:
            best = (0, 0)
            for j in reversed(heads2.get(data[i:i + 2], ())):
                if i - j > NEAR_DIST:
                    break
                k = match_len(data, i, j, min(NEAR_MAX, n - i))
                if k > best[0]:
                    best = (k, i - j)
            near[i] = best
            heads2.setdefault(data[i:i + 2], []).append(i)
        if i + FAR_MIN <= n:
            best = (0, 0)
            cands = heads3.setdefault(data[i:i + 3], [])
            for j in reversed(cands[-FAR_CANDIDATES:]):
                k = match_len(data, i, j, min(FAR_MAX, n - i))
                if k > best[0]:
                    best = (k, i - j)
                    if k == FAR_MAX:
                        break
            far[i] = best
            cands.append(i)
    return near, far


def pack(data):
    data = bytes(data)
    n = len(data)
    near, far = longest_matches(data)
    cost = [0] + [None] * n                      # fewest bytes for data[:i]
    how = [None] * (n + 1)

    def step(i, k, c, what):
        if cost[i + k] is None or c < cost[i + k]:
            cost[i + k], how[i + k] = c, what
    for i in range(n):
        for k in range(1, min(MAX_LIT, n - i) + 1):
            step(i, k, cost[i] + 1 + k, ("lit", i, k))
        length, dist = near[i]
        for k in range(NEAR_MIN, length + 1):
            step(i, k, cost[i] + 2, ("near", i, k, dist))
        length, dist = far[i]
        for k in range(FAR_MIN, length + 1):
            step(i, k, cost[i] + 3, ("far", i, k, dist))
    steps, i = [], n
    while i:
        steps.append(how[i])
        i = how[i][1]
    out = bytearray()
    for s in reversed(steps):
        if s[0] == "lit":
            _, i, k = s
            out.append(k - 1)
            out += data[i:i + k]
        elif s[0] == "near":
            _, i, k, dist = s
            out += bytes([0x40 + k - NEAR_MIN, dist - 1])
        else:
            _, i, k, dist = s
            out += bytes([0x80 + k - FAR_MIN, dist & 255, dist >> 8])
    out.append(END)
    return bytes(out)


def unpack(packed):
    out, p = bytearray(), 0
    while True:
        t = packed[p]
        p += 1
        if t == END:
            return bytes(out)
        if t < 0x40:
            out += packed[p:p + t + 1]
            p += t + 1
            continue
        if t < 0x80:
            length, dist = t - 0x40 + NEAR_MIN, packed[p] + 1
            p += 1
        else:
            length, dist = t - 0x80 + FAR_MIN, packed[p] | packed[p + 1] << 8
            p += 2
        for _ in range(length):
            out.append(out[-dist])


def pack_checked(data):
    packed = pack(data)
    if unpack(packed) != bytes(data):
        raise SystemExit("lz64: the packed data does not unpack back")
    return packed


def main():
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    packed = pack_checked(data)
    with open(sys.argv[2], "wb") as f:
        f.write(packed)
    print(f"lz64: {sys.argv[1]} {len(data)} -> {len(packed)} bytes ({100 * len(packed) / len(data):.0f} %)")


if __name__ == "__main__":
    main()
