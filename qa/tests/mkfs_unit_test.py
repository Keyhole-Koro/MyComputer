#!/usr/bin/env python3
"""tools/mkfs.py: the MFS disk image the firmware and kernel boot from.

Run with `python3 -m unittest discover -s qa/tests -p '*_unit_test.py'`.
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import mkfs  # noqa: E402


def used(img: mkfs.Image, block: int) -> bool:
    return bool((img.bitmap[block >> 3] >> (block & 7)) & 1)


class KernelSizeTest(unittest.TestCase):
    def test_boundary(self):
        limit = mkfs.KERNEL_BLOCKS * mkfs.BLOCK_SIZE
        self.assertEqual(limit, 64 * 64 * 1024)
        self.assertIsNone(mkfs.kernel_size_error(0))
        self.assertIsNone(mkfs.kernel_size_error(limit))
        self.assertIn("more than the firmware loads", mkfs.kernel_size_error(limit + 1))

    def test_embed_refuses_a_kernel_too_big(self):
        with self.assertRaises(SystemExit):
            mkfs.Image().embed_kernel(bytes(mkfs.KERNEL_BLOCKS * mkfs.BLOCK_SIZE + 1))

    def test_embed_marks_the_kernel_blocks(self):
        img = mkfs.Image()
        img.embed_kernel(b"K" * (mkfs.BLOCK_SIZE + 1))
        for block in range(mkfs.DATA_START):
            self.assertTrue(used(img, block), block)
        self.assertTrue(used(img, mkfs.KERNEL_BLOCK))
        self.assertTrue(used(img, mkfs.KERNEL_BLOCK + 1))
        self.assertFalse(used(img, mkfs.KERNEL_BLOCK + 2))
        self.assertFalse(used(img, mkfs.DATA_START))
        last = img.blocks[mkfs.KERNEL_BLOCK + 1]
        self.assertEqual(len(last), mkfs.BLOCK_SIZE)
        self.assertEqual(last[:2], b"K\0")


class EntryTest(unittest.TestCase):
    def test_name_length_limit(self):
        img = mkfs.Image()
        img.add_file("a" * (mkfs.NAME_MAX - 1), b"")
        with self.assertRaises(SystemExit):
            img.add_file("b" * mkfs.NAME_MAX, b"")
        # The limit counts bytes, not characters.
        with self.assertRaises(SystemExit):
            img.add_file("あ" * 6, b"")

    def test_duplicate_entry(self):
        img = mkfs.Image()
        img.add_file("bin/hello", b"x")
        with self.assertRaises(SystemExit):
            img.add_file("bin/hello", b"y")
        # The same name under another directory is a different entry.
        img.add_file("hello", b"z")

    def test_empty_path(self):
        with self.assertRaises(SystemExit):
            mkfs.Image().add_file("//", b"")

    def test_nested_directories(self):
        img = mkfs.Image()
        img.add_file("apps/demo/run", b"data")
        img.add_file("apps/other", b"")
        names = [(name, flags, parent) for name, _, _, flags, parent in img.entries]
        self.assertEqual(names, [
            ("apps", mkfs.FLAG_DIR, 0),
            ("demo", mkfs.FLAG_DIR, 1),
            ("run", 0, 2),
            ("other", 0, 1),
        ])
        # A directory owns one empty block, so its first block is never 0.
        self.assertTrue(all(first != 0 for _, first, _, _, _ in img.entries))
        self.assertEqual(img.directory("apps/demo"), 2)
        self.assertEqual(img.directory(""), 0)

    def test_file_in_the_way_of_a_directory(self):
        img = mkfs.Image()
        img.add_file("apps", b"")
        with self.assertRaises(SystemExit) as raised:
            img.add_file("apps/run", b"")
        self.assertIn("not a directory", str(raised.exception))

    def test_multi_block_chain(self):
        img = mkfs.Image()
        data = bytes(range(256)) * ((mkfs.PAYLOAD + 300) // 256 + 1)
        data = data[: mkfs.PAYLOAD + 300]
        img.add_file("big", data)
        _, first, size, flags, _ = img.entries[0]
        self.assertEqual((first, size, flags), (mkfs.DATA_START, len(data), 0))
        head = img.blocks[first]
        (second,) = struct.unpack_from(">I", head, 0)
        self.assertEqual(second, mkfs.DATA_START + 1)
        self.assertEqual(bytes(head[4:]), data[: mkfs.PAYLOAD])
        tail = img.blocks[second]
        self.assertEqual(struct.unpack_from(">I", tail, 0), (0,))
        self.assertEqual(bytes(tail[4 : 4 + 300]), data[mkfs.PAYLOAD :])
        self.assertTrue(used(img, second))

    def test_exactly_one_payload_takes_one_block(self):
        img = mkfs.Image()
        img.add_file("full", bytes(mkfs.PAYLOAD))
        img.add_file("next", b"")
        self.assertEqual([first for _, first, _, _, _ in img.entries],
                         [mkfs.DATA_START, mkfs.DATA_START + 1])


class WriteTest(unittest.TestCase):
    def test_round_trip(self):
        img = mkfs.Image()
        img.embed_kernel(b"\x7fKERNEL")
        img.add_file("bin/hello", b"hello, world\n")
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "disk.img"
            img.write(path)
            self.assertEqual(path.stat().st_size, mkfs.DISK_SIZE)
            with open(path, "rb") as f:
                def block(n: int) -> bytes:
                    f.seek(n * mkfs.BLOCK_SIZE)
                    return f.read(mkfs.BLOCK_SIZE)

                sb = block(mkfs.SB_BLOCK)
                self.assertEqual(sb[:4], b"MFS1")
                self.assertEqual(struct.unpack_from(">III", sb, 0),
                                 (mkfs.MAGIC, mkfs.VERSION, mkfs.MAX_FILES))

                table = block(mkfs.ENTRY_BLOCK)
                entries = []
                for idx in range(3):
                    off = idx * mkfs.ENTRY_SIZE
                    name = table[off : off + mkfs.NAME_MAX].rstrip(b"\0").decode()
                    entries.append((name, *struct.unpack_from(">IIII", table, off + mkfs.NAME_MAX)))
                self.assertEqual(entries, [
                    ("bin", mkfs.DATA_START, 0, mkfs.FLAG_DIR, 0),
                    ("hello", mkfs.DATA_START + 1, 13, 0, 1),
                    ("", 0, 0, 0, 0),
                ])

                bitmap = block(mkfs.BITMAP_BLOCK)
                self.assertEqual(bitmap[0], 0b00011111)  # 3 reserved + 2 data blocks
                self.assertEqual((bitmap[mkfs.KERNEL_BLOCK >> 3] >> (mkfs.KERNEL_BLOCK & 7)) & 1, 1)

                data = block(mkfs.DATA_START + 1)
                self.assertEqual(struct.unpack_from(">I", data, 0), (0,))
                self.assertEqual(data[4:17], b"hello, world\n")

                self.assertEqual(block(mkfs.KERNEL_BLOCK)[:8], b"\x7fKERNEL\0")


if __name__ == "__main__":
    unittest.main()
