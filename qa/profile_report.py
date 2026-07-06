#!/usr/bin/env python3
"""
Turn a MyEmulator profile (emitted by `myemu --profile <file>.json`) into a
readable report, resolving program counters to function names via a linker
`.map` file when one is available.

Usage:
  python3 qa/profile_report.py <profile.json> [--map <image.mbin.map>] [--top N]

If --map is omitted, the script looks for "<profile-stem>.mbin.map" and, failing
that, prints raw addresses. The four sections mirror what the profiler collects:
hotspots (self time by function), opcode histogram, call graph, and a memory
read/write heatmap by page.
"""

import argparse
import bisect
import json
import sys
from pathlib import Path

MEM_PAGE_SIZE = 1 << 12  # keep in sync with MEM_PAGE_SHIFT in profiler.rs


def load_map(map_path):
    """Parse a linker .map into (sorted [(address, name)], image_end).

    Lines look like "0x00000040 kernel_main"; comments start with '#'. The
    `_end` symbol (or the highest symbol) marks where the loaded image stops;
    addresses past it are runtime data (heap/stack/MMIO) that no code symbol
    should be attributed to.
    """
    entries = []
    with open(map_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            addr_str, name = parts
            try:
                addr = int(addr_str, 0)
            except ValueError:
                continue
            entries.append((addr, name))
    entries.sort()
    image_end = None
    for addr, name in entries:
        if name == "_end":
            image_end = addr
    if image_end is None and entries:
        image_end = entries[-1][0]
    return entries, image_end


# Known non-image address regions, labelled for the memory heatmap. Anything at
# or beyond the image end that isn't a recognized MMIO/stack region is "runtime
# data" rather than being force-attributed to the nearest code symbol.
IO_BASE = 0x24000000
VRAM_BASE = 0x30000000
RAM_END = 0x20000000


def region_label(addr):
    if IO_BASE <= addr <= IO_BASE + 0xFF:
        return "MMIO"
    if VRAM_BASE <= addr < VRAM_BASE + 0x300000:
        return "VRAM"
    if addr >= RAM_END - 0x10000 and addr < RAM_END:
        return "stack"
    return None


class SymbolResolver:
    """Resolve an address to the nearest symbol at or below it."""

    def __init__(self, entries, image_end=None):
        self.addrs = [a for a, _ in entries]
        self.names = [n for _, n in entries]
        self.image_end = image_end

    def resolve(self, addr):
        if not self.addrs:
            return None, None
        idx = bisect.bisect_right(self.addrs, addr) - 1
        if idx < 0:
            return None, None
        base = self.addrs[idx]
        return self.names[idx], addr - base

    def name_for_entry(self, entry):
        """Exact-or-nearest name for a function entry PC (call-graph nodes)."""
        name, offset = self.resolve(entry)
        if name is None:
            return f"0x{entry:08X}"
        if offset == 0:
            return name
        return f"{name}+0x{offset:X}"

    def label_for_data(self, addr):
        """Human label for a data address (memory heatmap).

        Uses a symbol only when the address falls inside the loaded image;
        otherwise names a known region (stack/MMIO/VRAM) or falls back to the
        raw address, so a stack page isn't mislabelled as "some_func+0x1FFF...".
        """
        region = region_label(addr)
        if region is not None:
            return f"0x{addr:08X} [{region}]"
        if self.image_end is not None and addr < self.image_end:
            name, offset = self.resolve(addr)
            if name is not None:
                return f"0x{addr:08X} [{name}+0x{offset:X}]"
        return f"0x{addr:08X}"


def fmt_pct(count, total):
    if total == 0:
        return "  0.0%"
    return f"{100.0 * count / total:5.1f}%"


def report_hotspots(data, resolver, top):
    total = data["total_instructions"]
    print(f"\n=== Hotspots (self instructions; total={total}) ===")
    print(f"{'self%':>7}  {'count':>12}  location")
    # Aggregate raw PC hits into their enclosing symbol so the flat profile reads
    # per-function rather than per-instruction-address.
    by_symbol = {}
    for hit in data["pc_hits"]:
        pc = hit["pc"]
        name, _ = resolver.resolve(pc)
        key = name if name is not None else f"0x{pc:08X}"
        by_symbol[key] = by_symbol.get(key, 0) + hit["hits"]
    ranked = sorted(by_symbol.items(), key=lambda kv: (-kv[1], kv[0]))
    for name, count in ranked[:top]:
        print(f"{fmt_pct(count, total):>7}  {count:>12}  {name}")


def report_opcodes(data):
    total = data["total_instructions"]
    print(f"\n=== Opcode histogram ===")
    print(f"{'freq%':>7}  {'count':>12}  opcode")
    for entry in data["opcode_hits"]:
        count = entry["count"]
        label = f"{entry['mnemonic']} (0x{entry['opcode']:02X})"
        print(f"{fmt_pct(count, total):>7}  {count:>12}  {label}")


def report_callgraph(data, resolver, top):
    total = data["total_instructions"]
    print(f"\n=== Call graph (functions by self time) ===")
    print(f"{'self%':>7}  {'incl%':>7}  {'calls':>8}  function")
    funcs = data["functions"]
    ranked = sorted(funcs, key=lambda f: (-f["self"], f["entry"]))
    for func in ranked[:top]:
        name = resolver.name_for_entry(func["entry"])
        print(
            f"{fmt_pct(func['self'], total):>7}  "
            f"{fmt_pct(func['inclusive'], total):>7}  "
            f"{func['calls']:>8}  {name}"
        )

    edges = data["edges"]
    if edges:
        print(f"\n--- Call edges (caller -> callee: count) ---")
        ranked_edges = sorted(edges, key=lambda e: (-e["count"], e["caller"]))
        for edge in ranked_edges[:top]:
            caller = resolver.name_for_entry(edge["caller"])
            callee = resolver.name_for_entry(edge["callee"])
            print(f"  {caller} -> {callee}: {edge['count']}")


def report_memory(data, resolver, top):
    def dump(title, pages):
        total = sum(p["count"] for p in pages)
        print(f"\n=== {title} (by {MEM_PAGE_SIZE // 1024}KB page; total={total}) ===")
        if not pages:
            print("  (none)")
            return
        print(f"{'freq%':>7}  {'count':>12}  page")
        for entry in pages[:top]:
            label = resolver.label_for_data(entry["page"])
            print(f"{fmt_pct(entry['count'], total):>7}  {entry['count']:>12}  {label}")

    dump("Memory reads", data["mem_reads"])
    dump("Memory writes", data["mem_writes"])


def main():
    parser = argparse.ArgumentParser(description="Render a MyEmulator profile.")
    parser.add_argument("profile", help="Path to the profile JSON from myemu --profile.")
    parser.add_argument("--map", dest="map_path", help="Path to the linker .map file.")
    parser.add_argument("--top", type=int, default=20, help="Rows per section (default 20).")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        print(f"Profile not found: {profile_path}", file=sys.stderr)
        return 1
    data = json.loads(profile_path.read_text(encoding="utf-8"))

    # Locate the symbol map. Explicit --map wins; otherwise guess a sibling map
    # named after the linked image (profile "kernel.json" -> "kernel.mbin.map").
    map_path = None
    if args.map_path:
        map_path = Path(args.map_path)
    else:
        for candidate in (
            profile_path.with_suffix(".mbin.map"),
            profile_path.with_suffix(".map"),
        ):
            if candidate.exists():
                map_path = candidate
                break

    entries = []
    image_end = None
    if map_path and Path(map_path).exists():
        entries, image_end = load_map(map_path)
        print(f"Using symbol map: {map_path} ({len(entries)} symbols)")
    else:
        print("No symbol map found; showing raw addresses.")
    resolver = SymbolResolver(entries, image_end)

    report_hotspots(data, resolver, args.top)
    report_opcodes(data)
    report_callgraph(data, resolver, args.top)
    report_memory(data, resolver, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
