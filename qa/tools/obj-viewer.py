#!/usr/bin/env python3
"""
Minimal viewer for MyCCLinker .obj files.
Prints header, symbols, relocations, and a short hex preview of text/data.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYLINKER_DIR  # noqa: E402

# The format's constants and record layouts live with the linker, repeated
# from its inc/ObjectFormat.h.
_spec = importlib.util.spec_from_file_location("objformat", MYLINKER_DIR / "tools" / "objformat.py")
objformat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(objformat)


def read_header(f):
    data = f.read(objformat.FILE_HEADER.size)
    if len(data) != objformat.FILE_HEADER.size:
        raise ValueError("File too short for header")
    return objformat.FILE_HEADER.unpack(data)


def read_symbols(f, count):
    symbols = []
    for _ in range(count):
        data = f.read(objformat.SYMBOL_ENTRY.size)
        if len(data) != objformat.SYMBOL_ENTRY.size:
            raise ValueError("File too short while reading symbols")
        raw_name, type_code, section_code, offset = objformat.SYMBOL_ENTRY.unpack(data)
        symbols.append(
            {
                "name": objformat.cstring(raw_name),
                "type": objformat.SYMBOL_TYPE_NAMES.get(type_code, f"UNKNOWN({type_code})"),
                "section": objformat.SECTION_NAMES.get(section_code, f"UNKNOWN({section_code})"),
                "offset": offset,
            }
        )
    return symbols


def read_relocs(f, count):
    relocs = []
    for _ in range(count):
        data = f.read(objformat.RELOC_ENTRY.size)
        if len(data) != objformat.RELOC_ENTRY.size:
            raise ValueError("File too short while reading relocations")
        offset, raw_name, type_code, _section = objformat.RELOC_ENTRY.unpack(data)
        relocs.append(
            {
                "offset": offset,
                "symbol": objformat.cstring(raw_name),
                "type": objformat.RELOC_TYPE_NAMES.get(type_code, f"UNKNOWN({type_code})"),
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
            magic, text_size, data_size, sym_count, reloc_count, collect_count, collect_size = read_header(f)
            if magic != objformat.LINKER_MAGIC:
                raise ValueError(f"Bad magic 0x{magic:08X} (expected 0x{objformat.LINKER_MAGIC:08X})")

            text = f.read(text_size)
            data = f.read(data_size)
            blob = f.read(collect_size)
            symbols = read_symbols(f, sym_count)
            relocs = read_relocs(f, reloc_count)
            collects = []
            entry = objformat.COLLECT_ENTRY
            for _ in range(collect_count):
                raw = f.read(entry.size)
                if len(raw) != entry.size:
                    raise ValueError("File too short for collected-section table")
                name, offset, size = entry.unpack(raw)
                collects.append((objformat.cstring(name), offset, size))
            debug = objformat.read_debug_trailer(f.read(), 0)
    except Exception as e:
        print(f"[{path}] ERROR: {e}")
        return

    print(f"\n== {path} ==")
    print(
        f"Header: magic OK, text={text_size} bytes, data={data_size} bytes, "
        f"symbols={len(symbols)}, relocs={len(relocs)}, collected chunks={len(collects)}"
    )
    for name, offset, size in collects:
        print(f"  .section {name}: blob+0x{offset:X}, {size} bytes")

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

    if debug:
        funcs, rows = debug
        print("Debug functions:")
        for offset, name, file in funcs:
            print(f"  - offset=0x{offset:08X}, {name} ({file})")
        print("Debug rows:")
        for offset, file, line, cost in rows:
            print(f"  - offset=0x{offset:08X}, {file}:{line}" + (f", cost={cost}" if cost else ""))


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
