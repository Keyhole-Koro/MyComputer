#!/usr/bin/env python3
"""Rasterize a TrueType/OpenType font into MyOS's MyLang font module.

Usage:
    python3 tools/gen_font.py
    python3 tools/gen_font.py --font path.ttf --out system/MyOS/src/ui/font_sans.mln
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FIRST_CODEPOINT = 0x20
LAST_CODEPOINT = 0x7E
GLYPH_COUNT = LAST_CODEPOINT - FIRST_CODEPOINT + 1
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "system/MyOS/src/ui/font_sans.mln"


@dataclass(frozen=True)
class FaceSpec:
    name: str
    weight: int | None
    pixel_size: int

    @property
    def is_bold(self) -> bool:
        return (self.weight or 400) >= 500


@dataclass(frozen=True)
class Glyph:
    advance: int
    bearing_x: int
    bearing_y: int
    width: int
    height: int
    coverage: bytes


@dataclass
class FontData:
    """Flattened arrays written into the generated MyLang module."""

    line_heights: list[int] = field(default_factory=list)
    ascents: list[int] = field(default_factory=list)
    pixel_sizes: list[int] = field(default_factory=list)
    bold_faces: list[int] = field(default_factory=list)
    advances: list[int] = field(default_factory=list)
    bearing_x: list[int] = field(default_factory=list)
    bearing_y: list[int] = field(default_factory=list)
    widths: list[int] = field(default_factory=list)
    heights: list[int] = field(default_factory=list)
    offsets: list[int] = field(default_factory=list)
    coverage: bytearray = field(default_factory=bytearray)

    def append_face(self, spec: FaceSpec, font: ImageFont.FreeTypeFont) -> None:
        ascent, descent = font.getmetrics()
        self.line_heights.append(ascent + descent)
        self.ascents.append(ascent)
        self.pixel_sizes.append(spec.pixel_size)
        self.bold_faces.append(1 if spec.is_bold else 0)
        for codepoint in range(FIRST_CODEPOINT, LAST_CODEPOINT + 1):
            self.append_glyph(rasterize_glyph(font, chr(codepoint)))

    def append_glyph(self, glyph: Glyph) -> None:
        self.advances.append(glyph.advance)
        self.bearing_x.append(glyph.bearing_x)
        self.bearing_y.append(glyph.bearing_y)
        self.widths.append(glyph.width)
        self.heights.append(glyph.height)
        self.offsets.append(len(self.coverage))
        self.coverage.extend(glyph.coverage)


FACES = (
    FaceSpec("regular_1x", 400, 14),
    FaceSpec("regular_2x", 400, 28),
    FaceSpec("bold_1x", 600, 16),
    FaceSpec("bold_2x", 600, 32),
)

CANDIDATE_FONTS = (
    Path("/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    Path("/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)


def find_font() -> Path:
    for candidate in CANDIDATE_FONTS:
        if candidate.exists():
            return candidate
    sys.exit("no candidate font found; pass --font <path.ttf>")


def load_face(path: Path, spec: FaceSpec) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, spec.pixel_size)
    if spec.weight is None:
        return font
    try:
        axes = font.get_variation_axes()
    except OSError:
        axes = []
    if axes:
        minimum, maximum = axes[0]["minimum"], axes[0]["maximum"]
        font.set_variation_by_axes([max(minimum, min(maximum, spec.weight))])
    return font


def rasterize_glyph(font: ImageFont.FreeTypeFont, character: str) -> Glyph:
    """Return tight A8 coverage and metrics relative to the pen position."""
    advance = int(round(font.getlength(character)))
    left, top, right, bottom = font.getbbox(character)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return Glyph(advance, 0, 0, 0, 0, b"")

    padding = 4
    image = Image.new("L", (right + padding * 2, bottom + padding * 2), 0)
    ImageDraw.Draw(image).text((padding, padding), character, font=font, fill=255)
    coverage = image.crop((
        left + padding, top + padding, right + padding, bottom + padding,
    )).tobytes()
    return Glyph(advance, left, top, width, height, coverage)


def collect_font_data(font_path: Path) -> FontData:
    data = FontData()
    for spec in FACES:
        data.append_face(spec, load_face(font_path, spec))
    return data


def int_array(name: str, values: list[int]) -> str:
    body = ", ".join(str(value) for value in values)
    return f"i32 {name}[{len(values)}] = {{{body}}};\n"


def byte_array(name: str, values: bytes) -> str:
    lines = []
    for offset in range(0, len(values), 24):
        chunk = values[offset:offset + 24]
        lines.append("    " + ", ".join(f"0x{value:02X}" for value in chunk))
    body = ",\n".join(lines) if lines else "    0x00"
    return f"char {name}[{max(len(values), 1)}] = {{\n{body}\n}};\n"


def module_source(font_path: Path, data: FontData) -> str:
    face_names = ", ".join(f"{index}={spec.name}" for index, spec in enumerate(FACES))
    output = [
        "package font_sans;\n\n",
        "// GENERATED by tools/gen_font.py -- do not edit by hand.\n",
        f"// Source font: {font_path.name}\n",
        f"// Faces: {face_names}\n",
        "//\n",
        "// Anti-aliased proportional font for the desktop UI. Each glyph is an 8-bit\n",
        "// coverage (A8) bitmap over its tight bounding box; graphics.mln hands the\n",
        "// box to DMA2D_CMD_MASK_A8 so drawing a character is one accelerator\n",
        "// command. Metrics are in pixels at the face's own size (no UI scaling here:\n",
        "// the 2x faces exist so a 2048x1536 display gets real 2x glyphs instead of\n",
        "// blown-up 1x ones).\n\n",
        f"i32 FACE_COUNT = {len(FACES)};\n",
        f"i32 GLYPH_COUNT = {GLYPH_COUNT};\n\n",
        int_array("face_line_h", data.line_heights),
        int_array("face_ascent", data.ascents),
        int_array("face_px", data.pixel_sizes),
        int_array("face_bold", data.bold_faces),
        "\n// Per glyph, indexed face * GLYPH_COUNT + (ch - 0x20).\n",
        int_array("g_adv", data.advances),
        int_array("g_bx", data.bearing_x),
        int_array("g_by", data.bearing_y),
        int_array("g_w", data.widths),
        int_array("g_h", data.heights),
        int_array("g_off", data.offsets),
        "\n",
        byte_array("g_data", bytes(data.coverage)),
        """
export i32 face_count() { return FACE_COUNT; }

// Pick a face: bold != 0 selects the bold weight, scale >= 2 the 2x size.
export i32 face_for(i32 bold, i32 scale) {
    i32 f = 0;
    if (scale >= 2) { f = 1; }
    if (bold != 0) { f = f + 2; }
    return f;
}

export i32 line_height(i32 face) { return face_line_h[face]; }
export i32 ascent(i32 face) { return face_ascent[face]; }
export i32 pixel_size(i32 face) { return face_px[face]; }

// Characters outside 0x20..0x7E draw as '?'.
i32 glyph_index(i32 face, i32 ch) {
    if (ch < ' ' || ch > '~') { ch = '?'; }
    return face * GLYPH_COUNT + (ch - ' ');
}

export i32 advance(i32 face, i32 ch) { return g_adv[glyph_index(face, ch)]; }
export i32 bearing_x(i32 face, i32 ch) { return g_bx[glyph_index(face, ch)]; }
export i32 bearing_y(i32 face, i32 ch) { return g_by[glyph_index(face, ch)]; }
export i32 width(i32 face, i32 ch) { return g_w[glyph_index(face, ch)]; }
export i32 height(i32 face, i32 ch) { return g_h[glyph_index(face, ch)]; }

// Address of the glyph's coverage bytes (row-major, stride == width).
export i32 data(i32 face, i32 ch) {
    return (i32)(&g_data[0]) + g_off[glyph_index(face, ch)];
}
""",
    ]
    return "".join(output)


def emit(output_path: Path, font_path: Path) -> None:
    data = collect_font_data(font_path)
    output_path.write_text(module_source(font_path, data), encoding="utf-8")
    print(f"wrote {output_path} ({len(data.coverage)} coverage bytes, {len(FACES)} faces)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--font", type=Path, help="TTF/OTF to rasterize")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    emit(args.out, args.font or find_font())


if __name__ == "__main__":
    main()
