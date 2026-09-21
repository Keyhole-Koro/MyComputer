#!/usr/bin/env python3
"""Build a MyFileSystem (MFS) disk image on the host (MYOS-015).

Mirrors the on-disk format in system/MyOS/src/fs/fs.mln:

    block 0        superblock: magic 'MFS1', version 1, max_files 2048
    block 1        entry table: 2048 x 32-byte entries
                   (name[16], first_block, size, flags, parent -- big endian;
                    flags bit 0 = directory, parent = parent entry index + 1, 0 = root)
    block 2        allocation bitmap, one bit per block, LSB-first per byte
    block 3..      data blocks: 4-byte next-block pointer (0 = end) + payload

Blocks are 64 KiB; the image is 1 GiB. The kernel image is embedded at block
KERNEL_BLOCK (what MyFirmware loads) and those blocks are marked used so the
filesystem never allocates over it.

Usage:
    python3 tools/mkfs.py out.img --kernel build/kernel_linked.mbin \
        --file bin/hello=build/user/hello.mbin --file readme.txt=docs/readme.txt
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

BLOCK_SIZE = 65536
BLOCK_COUNT = 16384
DISK_SIZE = BLOCK_SIZE * BLOCK_COUNT
PAYLOAD = BLOCK_SIZE - 4
MAGIC = 0x4D465331
VERSION = 1
ENTRY_SIZE = 32
MAX_FILES = 2048
NAME_MAX = 16
FLAG_DIR = 1
SB_BLOCK, ENTRY_BLOCK, BITMAP_BLOCK, DATA_START = 0, 1, 2, 3
KERNEL_BLOCK = 16000  # must match system/MyFirmware and qa/runners/run_system.py


class Image:
    def __init__(self) -> None:
        self.blocks: dict[int, bytearray] = {}
        self.bitmap = bytearray(BLOCK_COUNT // 8)
        # (name, first_block, size, flags, parent_code); parent_code is the
        # parent entry's index + 1, 0 for the root. A directory (flags & 1)
        # owns one empty block, so "in use" stays first_block != 0.
        self.entries: list[tuple[str, int, int, int, int]] = []
        for b in range(DATA_START):
            self.mark(b)

    def find(self, parent_code: int, name: str) -> int | None:
        for idx, (n, _, _, _, p) in enumerate(self.entries):
            if p == parent_code and n == name:
                return idx
        return None

    def directory(self, path: str) -> int:
        """The parent code of directory `path` (created on the way), 0 for the root."""
        code = 0
        for part in [p for p in path.split("/") if p]:
            idx = self.find(code, part)
            if idx is None:
                idx = self.add_entry(part, b"", FLAG_DIR, code)
            elif not self.entries[idx][3] & FLAG_DIR:
                raise SystemExit(f"mkfs: not a directory: {part} in {path}")
            code = idx + 1
        return code

    def add_entry(self, name: str, data: bytes, flags: int, parent_code: int) -> int:
        if len(name.encode()) >= NAME_MAX:
            raise SystemExit(f"mkfs: name too long (max {NAME_MAX - 1}): {name}")
        if len(self.entries) >= MAX_FILES:
            raise SystemExit("mkfs: entry table full")
        if self.find(parent_code, name) is not None:
            raise SystemExit(f"mkfs: duplicate entry: {name}")
        chunks = [data[i : i + PAYLOAD] for i in range(0, len(data), PAYLOAD)] or [b""]
        blocks = [self.alloc() for _ in chunks]
        for i, (block, chunk) in enumerate(zip(blocks, chunks)):
            nxt = blocks[i + 1] if i + 1 < len(blocks) else 0
            buf = bytearray(BLOCK_SIZE)
            struct.pack_into(">I", buf, 0, nxt)
            buf[4 : 4 + len(chunk)] = chunk
            self.blocks[block] = buf
        self.entries.append((name, blocks[0], len(data), flags, parent_code))
        return len(self.entries) - 1

    def mark(self, block: int) -> None:
        self.bitmap[block >> 3] |= 1 << (block & 7)

    def alloc(self) -> int:
        for b in range(DATA_START, BLOCK_COUNT):
            if not (self.bitmap[b >> 3] >> (b & 7)) & 1:
                self.mark(b)
                return b
        raise SystemExit("mkfs: disk full")

    def add_file(self, path: str, data: bytes) -> None:
        """A file at `path` ("apps/counter"); directories on the way are created."""
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise SystemExit(f"mkfs: empty path: {path!r}")
        code = self.directory("/".join(parts[:-1]))
        self.add_entry(parts[-1], data, 0, code)

    def embed_kernel(self, data: bytes) -> None:
        # Raw image at a fixed block, outside the filesystem's data area.
        n = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
        for i in range(n):
            self.mark(KERNEL_BLOCK + i)
            self.blocks[KERNEL_BLOCK + i] = bytearray(data[i * BLOCK_SIZE : (i + 1) * BLOCK_SIZE].ljust(BLOCK_SIZE, b"\0"))

    def write(self, path: Path) -> None:
        sb = bytearray(BLOCK_SIZE)
        struct.pack_into(">III", sb, 0, MAGIC, VERSION, MAX_FILES)
        table = bytearray(BLOCK_SIZE)
        for idx, (name, first, size, flags, parent_code) in enumerate(self.entries):
            off = idx * ENTRY_SIZE
            table[off : off + NAME_MAX] = name.encode().ljust(NAME_MAX, b"\0")
            struct.pack_into(">IIII", table, off + NAME_MAX, first, size, flags, parent_code)
        bitmap = bytearray(BLOCK_SIZE)
        bitmap[: len(self.bitmap)] = self.bitmap
        with open(path, "wb") as f:
            f.truncate(DISK_SIZE)
            for block, buf in [(SB_BLOCK, sb), (ENTRY_BLOCK, table), (BITMAP_BLOCK, bitmap)] + sorted(self.blocks.items()):
                f.seek(block * BLOCK_SIZE)
                f.write(buf)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("--kernel", help="kernel image to embed at block %d" % KERNEL_BLOCK)
    parser.add_argument("--file", action="append", default=[], metavar="NAME=PATH", help="add a file (repeatable)")
    parser.add_argument("--text", action="append", default=[], metavar="NAME=STRING", help="add a small text file")
    parser.add_argument("--dir", action="append", default=[], metavar="PATH", help="add an (empty) directory")
    args = parser.parse_args()

    img = Image()
    if args.kernel:
        img.embed_kernel(Path(args.kernel).read_bytes())
    for path in args.dir:
        img.directory(path)
    for spec in args.file:
        name, _, src = spec.partition("=")
        img.add_file(name, Path(src).read_bytes())
    for spec in args.text:
        name, _, text = spec.partition("=")
        img.add_file(name, text.encode())
    img.write(Path(args.out))
    print(f"mkfs: {args.out}: {len(img.entries)} file(s)" + (f", kernel at block {KERNEL_BLOCK}" if args.kernel else ""))


if __name__ == "__main__":
    main()
