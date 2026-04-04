#!/usr/bin/env python3
"""
Minimal viewer for MyCCLinker .obj files.
Prints header, symbols, relocations, and a short hex preview of text/data.
"""

import argparse
import struct
import sys
from pathlib import Path


MAGIC = 0x4C4E4B31  # "LNK1"
HEADER_STRUCT = struct.Struct("<LLLLL")     # magic, text_size, data_size, sym_count, reloc_count
SYMBOL_STRUCT = struct.Struct("<64sLLL")    # name[64], type, section, offset
RELOC_STRUCT = struct.Struct("<L64sL")      # offset, symbol_name[64], type

SYMBOL_TYPES = {0: "UNDEFINED", 1: "DEFINED"}
SECTION_TYPES = {0: "TEXT", 1: "DATA"}
RELOC_TYPES = {0: "ABSOLUTE", 1: "RELATIVE"}


def read_header(f):
    data = f.read(HEADER_STRUCT.size)
    if len(data) != HEADER_STRUCT.size:
        raise ValueError("File too short for header")
    return HEADER_STRUCT.unpack(data)


def read_symbols(f, count):
    symbols = []
    for _ in range(count):
        data = f.read(SYMBOL_STRUCT.size)
        if len(data) != SYMBOL_STRUCT.size:
            raise ValueError("File too short while reading symbols")
        raw_name, type_code, section_code, offset = SYMBOL_STRUCT.unpack(data)
        name = raw_name.split(b"\0", 1)[0].decode("utf-8", errors="replace")
        symbols.append(
            {
                "name": name,
                "type": SYMBOL_TYPES.get(type_code, f"UNKNOWN({type_code})"),
                "section": SECTION_TYPES.get(section_code, f"UNKNOWN({section_code})"),
                "offset": offset,
            }
        )
    return symbols


def read_relocs(f, count):
    relocs = []
    for _ in range(count):
        data = f.read(RELOC_STRUCT.size)
        if len(data) != RELOC_STRUCT.size:
            raise ValueError("File too short while reading relocations")
        offset, raw_name, type_code = RELOC_STRUCT.unpack(data)
        name = raw_name.split(b"\0", 1)[0].decode("utf-8", errors="replace")
        relocs.append(
            {
                "offset": offset,
                "symbol": name,
                "type": RELOC_TYPES.get(type_code, f"UNKNOWN({type_code})"),
            }
        )
    return relocs


def hex_preview(buf, max_bytes, width=16):
    shown = buf[:max_bytes]
    lines = []
    for i in range(0, len(shown), width):
        chunk = shown[i : i + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        lines.append(f"{i:08X}: {hex_part}")
    if len(buf) > max_bytes:
        lines.append(f"... ({len(buf) - max_bytes} more bytes)")
    return lines


def show_obj(path: Path, max_bytes: int):
    try:
        with path.open("rb") as f:
            magic, text_size, data_size, sym_count, reloc_count = read_header(f)
            if magic != MAGIC:
                raise ValueError(f"Bad magic 0x{magic:08X} (expected 0x{MAGIC:08X})")

            text = f.read(text_size)
            data = f.read(data_size)
            symbols = read_symbols(f, sym_count)
            relocs = read_relocs(f, reloc_count)
    except Exception as e:
        print(f"[{path}] ERROR: {e}")
        return

    print(f"\n== {path} ==")
    print(
        f"Header: magic OK, text={text_size} bytes, data={data_size} bytes, "
        f"symbols={len(symbols)}, relocs={len(relocs)}"
    )

    if text_size:
        print("Text preview:")
        for line in hex_preview(text, max_bytes):
            print(f"  {line}")
    else:
        print("Text: (empty)")

    if data_size:
        print("Data preview:")
        for line in hex_preview(data, max_bytes):
            print(f"  {line}")
    else:
        print("Data: (empty)")

    print("Symbols:")
    if symbols:
        for sym in symbols:
            name = sym["name"] or "<unnamed>"
            print(
                f"  - {name}: {sym['type']}, section={sym['section']}, offset=0x{sym['offset']:08X}"
            )
    else:
        print("  (none)")

    print("Relocations:")
    if relocs:
        for rel in relocs:
            print(
                f"  - offset=0x{rel['offset']:08X}, symbol='{rel['symbol']}', type={rel['type']}"
            )
    else:
        print("  (none)")


def main(argv):
    parser = argparse.ArgumentParser(description="View MyCCLinker .obj contents")
    parser.add_argument("paths", nargs="+", help="One or more .obj files to display")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=64,
        help="Max bytes to show for text/data previews (default: 64)",
    )
    args = parser.parse_args(argv)

    for p in args.paths:
        show_obj(Path(p), args.max_bytes)


if __name__ == "__main__":
    main(sys.argv[1:])
