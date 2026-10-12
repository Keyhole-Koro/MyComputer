#!/usr/bin/env python3
"""Regenerate the media embedded in readme.md.

Two jobs, both run by `make readme`:

* Snippets: a block in readme.md between
      <!-- snippet: path/to/file.mln start="..." end="..." -->
      <!-- /snippet -->
  is replaced with the lines of that file from the first line containing
  `start` through the next line equal to `end` (whole file when neither is
  given), so the code shown always matches code the build compiles.
  `--check` only reports stale blocks, for QA.

* Screenshots: boots the built system headless, drives the desktop through
  the MyOS automation API (the same path as apps_e2e_test.py) and saves
  docs/images/*.png at half the framebuffer resolution.
"""
import argparse
import re
import struct
import sys
import tempfile
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.project_paths import REPO_ROOT  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "system" / "MyOS" / "tests"))
from mydomtester import MyOS, expect  # noqa: E402

README = REPO_ROOT / "readme.md"
IMAGES = REPO_ROOT / "docs" / "images"

SNIPPET_RE = re.compile(
    r"(?P<open><!-- snippet: (?P<args>.*?) -->\n).*?(?P<close><!-- /snippet -->)", re.S)
ARG_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


# --- snippets ---------------------------------------------------------------

def snippet_text(args: str) -> str:
    path, _, rest = args.partition(" ")
    opts = {key: value.replace('\\"', '"') for key, value in ARG_RE.findall(rest)}
    lines = (REPO_ROOT / path).read_text(encoding="utf-8").splitlines()
    begin, end = 0, len(lines)
    if "start" in opts:
        begin = next((i for i, line in enumerate(lines) if opts["start"] in line), None)
        if begin is None:
            raise SystemExit(f"readme snippet: {opts['start']!r} not found in {path}")
    if "end" in opts:
        end = next((i + 1 for i in range(begin, len(lines)) if lines[i].rstrip() == opts["end"]), None)
        if end is None:
            raise SystemExit(f"readme snippet: no line {opts['end']!r} after the start in {path}")
    body = "\n".join(lines[begin:end]).rstrip()
    return f"```{opts.get('lang', 'rust')}\n// {path}\n{body}\n```\n"


def render_snippets(text: str) -> str:
    return SNIPPET_RE.sub(lambda m: m["open"] + snippet_text(m["args"]) + m["close"], text)


# --- screenshots ------------------------------------------------------------

def read_ppm(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    fields, pos = [], 0
    while len(fields) < 4:  # magic, width, height, maxval
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos)
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    if fields[0] != b"P6" or fields[3] != b"255":
        raise SystemExit(f"{path}: expected an 8-bit P6 PPM")
    width, height = int(fields[1]), int(fields[2])
    return width, height, data[pos + 1:pos + 1 + width * height * 3]


def half_size(width: int, height: int, rgb: bytes) -> tuple[int, int, bytes]:
    """2x2 box filter; the UI renders at 2x, so this is its logical size."""
    out_w, out_h = width // 2, height // 2
    stride = width * 3
    out = bytearray(out_w * out_h * 3)
    for y in range(out_h):
        top = rgb[2 * y * stride:(2 * y + 1) * stride]
        bottom = rgb[(2 * y + 1) * stride:(2 * y + 2) * stride]
        row = y * out_w * 3
        for c in range(3):
            # Sum each channel over the four source pixels in bulk.
            t0, t1 = top[c::6][:out_w], top[c + 3::6][:out_w]
            b0, b1 = bottom[c::6][:out_w], bottom[c + 3::6][:out_w]
            out[row + c:row + out_w * 3:3] = bytes(
                (a + b + d + e + 2) >> 2 for a, b, d, e in zip(t0, t1, b0, b1))
    return out_w, out_h, bytes(out)


def write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    stride = width * 3
    raw = bytearray()
    prev = bytes(stride)
    for y in range(height):
        row = rgb[y * stride:(y + 1) * stride]
        # Up filter: flat UI areas become zero runs that deflate well.
        raw.append(2)
        raw += bytes((a - b) & 0xFF for a, b in zip(row, prev))
        prev = row

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                     + chunk(b"IEND", b""))


def save_shot(os: MyOS, name: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ppm = Path(tmp) / "frame.ppm"
        os.screenshot(ppm)
        out = IMAGES / name
        write_png(out, *half_size(*read_ppm(ppm)))
    print(f"wrote {out.relative_to(REPO_ROOT)}")


def wait_text_contains(locator, needle: str, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        node = locator.snapshot()
        if needle in (node.value or node.text):
            return
    raise SystemExit(f"readme screenshots: {needle!r} never appeared")


def drag(os: MyOS, x0: int, y0: int, x1: int, y1: int) -> None:
    """Press at (x0, y0), move to (x1, y1) and release; wait for the redraw.

    The emulator only runs the guest while serving a request, so the wait
    polls snapshots instead of sleeping."""
    before = os.snapshot().revision
    steps = 8
    os._pointer_sequence(
        [{"type": "move", "x": x0, "y": y0}, {"type": "down", "button": "left"}]
        + [{"type": "move", "x": x0 + (x1 - x0) * i // steps, "y": y0 + (y1 - y0) * i // steps}
           for i in range(1, steps + 1)]
        + [{"type": "up", "button": "left"}])
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and os.snapshot().revision == before:
        pass


def take_screenshots() -> None:
    firmware = REPO_ROOT / "build" / "firmware_linked.mbin"
    disk = REPO_ROOT / "build" / "disk.img"
    if not firmware.exists() or not disk.exists():
        raise SystemExit("build firmware and disk first (make build)")
    IMAGES.mkdir(parents=True, exist_ok=True)
    with MyOS.launch(firmware, disk=disk,
                     artifacts=REPO_ROOT / "qa" / "outputs" / "readme-media") as os:
        term_in = os.get_by_test_id("terminal-input")
        term_out = os.get_by_test_id("terminal-output")
        expect(term_in).to_be_visible()
        # Slide the terminal down and right so the Counter window behind it
        # shows; coordinates are framebuffer pixels (the UI renders at 2x).
        terminal = os.get_by_role("window", name="Terminal").snapshot().bounds
        grab_x, grab_y = terminal.x + terminal.width - 120, terminal.y + 30
        drag(os, grab_x, grab_y, grab_x + 460, grab_y + 380)
        for _ in range(3):
            os.get_by_role("button", name="Click me").click()
        wait_text_contains(os.get_by_test_id("counter"), "clicks: 3")
        term_in.click()
        for command, needle in (("hello", "exited with 7"), ("ls", "readme.txt")):
            os._type(command)
            os._press("enter")
            wait_text_contains(term_out, needle)
        save_shot(os, "desktop.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if readme snippets are stale")
    parser.add_argument("--no-screenshots", action="store_true", help="only refresh snippets")
    args = parser.parse_args()

    text = README.read_text(encoding="utf-8")
    rendered = render_snippets(text)
    if args.check:
        if rendered != text:
            print("FAIL: readme.md snippets are stale; run `make readme`")
            return 1
        print("PASS: readme.md snippets match their sources")
        return 0
    if rendered != text:
        README.write_text(rendered, encoding="utf-8")
        print("updated readme.md snippets")
    if not args.no_screenshots:
        take_screenshots()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
