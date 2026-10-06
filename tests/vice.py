"""Headless VICE (x64sc) driven through its binary monitor (VICE 3.x API v2).

One VICE per test module, each on its own TCP port, so modules can run in
parallel. Typical use:

    with Vice() as vm:
        vm.run_to("frame_done")
        vm.peek16("frame_counter")
"""

import os
import socket
import struct
import subprocess
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD = os.path.join(ROOT, "build")
D64 = os.path.join(BUILD, "runner.d64")
PRG = os.path.join(BUILD, "runner.prg")
LABELS = os.path.join(BUILD, "labels.txt")
X64 = os.environ.get("X64", "x64sc")

STX = 0x02
API = 0x02

CMD_MEM_GET = 0x01
CMD_MEM_SET = 0x02
CMD_CP_SET = 0x12
CMD_CP_DELETE = 0x13
CMD_REGS_GET = 0x31
CMD_BANKS = 0x82
CMD_REGS_AVAILABLE = 0x83
CMD_DISPLAY_GET = 0x84
CMD_EXIT = 0xAA
CMD_QUIT = 0xBB

EV_CHECKPOINT = 0x11
EV_JAM = 0x61
EV_STOPPED = 0x62
EV_RESUMED = 0x63
EVENT_ID = 0xFFFFFFFF

OP_LOAD, OP_STORE, OP_EXEC = 1, 2, 4


def load_labels(path=LABELS):
    """64tass --vice-labels: 'al 80d .start' -> {'start': 0x80d}."""
    labels = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 3 and parts[0] == "al":
                labels[parts[2].lstrip(".")] = int(parts[1], 16)
    return labels


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MonitorError(Exception):
    pass


class Vice:
    """A running x64sc with the game autostarted, stopped in the monitor
    between calls (every command stops the emulation; `cont` resumes it)."""

    def __init__(self, image=PRG, extra_args=(), boot_timeout=30.0, play=True):
        """play: past the menu at once, a game running (restart: no countdown)."""
        self.labels = load_labels()
        self.port = free_port()
        args = [X64, "-console", "-default", "-warp", "-silent", "-sounddev", "dummy",
                "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{self.port}",
                "-autostartprgmode", "1", *extra_args, "-autostart", image]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sock = None
        self._req = 0
        self._pending = []          # events read while waiting for a response
        deadline = time.time() + boot_timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=boot_timeout)
                break
            except OSError:
                if time.time() > deadline or self.proc.poll() is not None:
                    self.close()
                    raise MonitorError("could not connect to the VICE binary monitor")
                time.sleep(0.05)
        self._banks = None
        self._regs = None
        if play:
            self.run_to("frame_done")
            self.poke("restart", 1)

    # -- context manager --------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.sock is not None:
            try:
                self._send(CMD_QUIT, b"")
            except OSError:
                pass
            self.sock.close()
            self.sock = None
        if self.proc.poll() is None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    # -- protocol ---------------------------------------------------------
    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise MonitorError("VICE closed the connection")
            buf += chunk
        return buf

    def _read_message(self):
        head = self._recv_exact(12)
        stx, api, length, rtype, err, req = struct.unpack("<BBIBBI", head)
        if stx != STX:
            raise MonitorError(f"bad response start {stx:#x}")
        body = self._recv_exact(length)
        return rtype, err, req, body

    def _send(self, cmd, body):
        self._req = (self._req + 1) & 0x7FFFFFFF
        self.sock.sendall(struct.pack("<BBIIB", STX, API, len(body), self._req, cmd) + body)
        return self._req

    def command(self, cmd, body=b""):
        """Sends a command, returns the body of its response (events that
        arrive meanwhile are kept for wait_event)."""
        req = self._send(cmd, body)
        while True:
            rtype, err, rid, rbody = self._read_message()
            if rid == req:
                if err:
                    raise MonitorError(f"command {cmd:#x} failed with error {err:#x}")
                return rtype, rbody
            self._pending.append((rtype, rbody))

    def wait_event(self, kinds, timeout=60.0):
        """Waits for an event of one of the given types (from the queue first)."""
        for i, (rtype, body) in enumerate(self._pending):
            if rtype in kinds:
                del self._pending[i]
                return rtype, body
        self.sock.settimeout(timeout)
        try:
            while True:
                rtype, err, rid, body = self._read_message()
                if rtype in kinds:
                    return rtype, body
                if rtype == EV_JAM:
                    raise MonitorError("CPU JAM at $%04X" % struct.unpack("<H", body[:2])[0])
        finally:
            self.sock.settimeout(None)

    # -- addresses --------------------------------------------------------
    def addr(self, a):
        return self.labels[a] if isinstance(a, str) else a

    def bank(self, name):
        if self._banks is None:
            _, body = self.command(CMD_BANKS)
            count = struct.unpack("<H", body[:2])[0]
            self._banks, pos = {}, 2
            for _ in range(count):
                size = body[pos]
                bid, nlen = struct.unpack("<HB", body[pos + 1:pos + 4])
                self._banks[body[pos + 4:pos + 4 + nlen].decode()] = bid
                pos += 1 + size
        return self._banks[name]

    # -- memory -----------------------------------------------------------
    def peek(self, a, n=1, bank="cpu"):
        """Reads n bytes as the CPU sees them (bank 'cpu') or raw ('ram')."""
        start = self.addr(a)
        out = b""
        while n > 0:
            count = min(n, 0x10000 - start, 0x8000)
            body = struct.pack("<BHHBH", 0, start, start + count - 1, 0, self.bank(bank))
            _, rbody = self.command(CMD_MEM_GET, body)
            length = struct.unpack("<H", rbody[:2])[0] or 0x10000
            out += rbody[2:2 + length]
            start, n = start + count, n - count
        return out

    def peek8(self, a):
        return self.peek(a)[0]

    def peek16(self, a):
        return struct.unpack("<H", self.peek(a, 2))[0]

    def poke(self, a, data, bank="cpu"):
        if isinstance(data, int):
            data = bytes([data])
        start = self.addr(a)
        body = struct.pack("<BHHBH", 0, start, start + len(data) - 1, 0, self.bank(bank)) + bytes(data)
        self.command(CMD_MEM_SET, body)

    # -- registers --------------------------------------------------------
    def registers(self):
        """{'PC': .., 'A': .., 'LIN': raster line, 'CYC': raster cycle, ...}"""
        if self._regs is None:
            _, body = self.command(CMD_REGS_AVAILABLE, b"\x00")
            count = struct.unpack("<H", body[:2])[0]
            self._regs, pos = {}, 2
            for _ in range(count):
                size = body[pos]
                rid, bits, nlen = body[pos + 1], body[pos + 2], body[pos + 3]
                self._regs[rid] = body[pos + 4:pos + 4 + nlen].decode()
                pos += 1 + size
        _, body = self.command(CMD_REGS_GET, b"\x00")
        count = struct.unpack("<H", body[:2])[0]
        regs, pos = {}, 2
        for _ in range(count):
            size = body[pos]
            rid, value = struct.unpack("<BH", body[pos + 1:pos + 4])
            regs[self._regs.get(rid, rid)] = value
            pos += 1 + size
        return regs

    # -- execution --------------------------------------------------------
    def checkpoint(self, a, op=OP_EXEC, stop=True, end=None):
        start = self.addr(a)
        end = start if end is None else self.addr(end)
        body = struct.pack("<HHBBBB", start, end, int(stop), 1, op, 0)
        _, rbody = self.command(CMD_CP_SET, body)
        return struct.unpack("<I", rbody[:4])[0]

    def delete_checkpoint(self, cp):
        self.command(CMD_CP_DELETE, struct.pack("<I", cp))

    def cont(self):
        self.command(CMD_EXIT)

    def run_to(self, a, times=1, timeout=60.0):
        """Resumes until the code at `a` has been reached `times` times."""
        cp = self.checkpoint(a)
        try:
            for _ in range(times):
                self._pending.clear()       # stale 'stopped' from entering the monitor
                self.cont()
                while True:                 # a hit = checkpoint event for our checkpoint
                    _, body = self.wait_event((EV_CHECKPOINT,), timeout)
                    if struct.unpack("<I", body[:4])[0] == cp:
                        break
                self.wait_event((EV_STOPPED,), timeout)
        finally:
            self.delete_checkpoint(cp)
        return self.registers()

    def run_frames(self, n=1):
        """Runs n passes of the main loop (stops at frame_done)."""
        return self.run_to("frame_done", n)

    # -- display ----------------------------------------------------------
    def display(self):
        """(width, height, bytes): the whole emulated picture, 8-bit palette indices."""
        _, body = self.command(CMD_DISPLAY_GET, b"\x01\x00")
        info_len = struct.unpack("<I", body[:4])[0]
        dw, dh, xo, yo, iw, ih, bpp = struct.unpack("<HHHHHHB", body[4:17])
        buf_len = struct.unpack("<I", body[4 + info_len:8 + info_len])[0]
        pixels = body[8 + info_len:8 + info_len + buf_len]
        return dw, dh, xo, yo, iw, ih, pixels
