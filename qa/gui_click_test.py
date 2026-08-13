#!/usr/bin/env python3
"""GUI click test for the MyComputer system.

Launches myemu with the display, then uses XTEST to click the CLICK ME button:
one slow click, then two rapid (~5 ms press-to-release) clicks. Captures the
emulator framebuffer before/after to verify the "clicks: N" label. With the
old frame-rate mouse sampling the rapid clicks would be lost; with the event
FIFO all three must register (final label: clicks: 3).

Pointer positioning is closed-loop: after each warp we ask the X server where
the pointer is relative to the emulator window (query_pointer), so WM frames,
WSLg scaling, or origin quirks cannot make the click miss. minifb reports raw
window-relative pixels to the guest, so the target is the button's framebuffer
rect regardless of any visual stretching of the window.
"""

import subprocess
import sys
import time
from pathlib import Path

from PIL import Image
from Xlib import X, display
from Xlib.ext import xtest

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parents[1] / "build" / "gui-test"
OUT.mkdir(parents=True, exist_ok=True)

FB_W, FB_H = 1024, 768
# Button rect in framebuffer coords: x=120..270, y=130..190 (see build_ui).
BTN_X, BTN_Y = 195, 160
# Label "clicks: N" is drawn at (320, 150); crop in framebuffer coords.
LABEL_CROP = (300, 135, 520, 175)


def find_window(root, needle):
    def walk(w):
        try:
            name = w.get_wm_name()
        except Exception:
            name = None
        if name and needle in name:
            return w
        try:
            children = w.query_tree().children
        except Exception:
            return None
        for c in children:
            r = walk(c)
            if r is not None:
                return r
        return None

    return walk(root)


def grab(win, path):
    geo = win.get_geometry()
    raw = win.get_image(0, 0, geo.width, geo.height, X.ZPixmap, 0xFFFFFFFF)
    img = Image.frombytes("RGB", (geo.width, geo.height), raw.data, "raw", "BGRX")
    if (geo.width, geo.height) != (FB_W, FB_H):
        img = img.resize((FB_W, FB_H), Image.NEAREST)
    img.save(OUT / (path + ".png"))
    img.crop(LABEL_CROP).resize(
        ((LABEL_CROP[2] - LABEL_CROP[0]) * 3, (LABEL_CROP[3] - LABEL_CROP[1]) * 3),
        Image.NEAREST,
    ).save(OUT / (path + "-label.png"))


def pointer_rel(win):
    p = win.query_pointer()
    return p.win_x, p.win_y


def move_to_rel(disp, win, tx, ty, tries=8):
    # Warp, then correct using the server-reported window-relative position.
    px, py = pointer_rel(win)
    for _ in range(tries):
        if (px, py) == (tx, ty):
            return True
        pr = disp.screen().root.query_pointer()
        xtest.fake_input(
            disp, X.MotionNotify, x=pr.root_x + (tx - px), y=pr.root_y + (ty - py)
        )
        disp.sync()
        time.sleep(0.02)
        px, py = pointer_rel(win)
    print(f"WARN: pointer settled at rel ({px}, {py}), wanted ({tx}, {ty})")
    return False


def button(disp, press):
    ev = X.ButtonPress if press else X.ButtonRelease
    xtest.fake_input(disp, ev, 1)
    disp.sync()


def main():
    emu = subprocess.Popen(
        [
            str(REPO / "runtime/MyEmulator/target/release/myemu"),
            "-i", str(REPO / "build/firmware_linked.mbin"),
            "--disk", str(REPO / "build/disk.img"),
        ],
        stdin=subprocess.DEVNULL,
        stdout=open(OUT / "gui_emu.log", "w"),
        stderr=subprocess.STDOUT,
    )
    try:
        disp = display.Display()
        root = disp.screen().root

        win = None
        for _ in range(150):
            win = find_window(root, "MyEmulator")
            if win is not None:
                break
            time.sleep(0.2)
        if win is None:
            print("FAIL: emulator window not found")
            return 1
        # Give the kernel time to boot and render the first UI frame.
        time.sleep(4.0)

        geo = win.get_geometry()
        print(f"window size: {geo.width}x{geo.height}")

        # Approach the button, then settle exactly on it (closed loop).
        move_to_rel(disp, win, BTN_X - 40, BTN_Y - 20)
        time.sleep(0.1)
        move_to_rel(disp, win, BTN_X, BTN_Y)
        time.sleep(0.4)
        grab(win, "shot0-before")

        # 1) One deliberate slow click (50 ms hold, longer than one frame).
        button(disp, True)
        time.sleep(0.05)
        button(disp, False)
        time.sleep(0.6)
        grab(win, "shot1-after-slow-click")

        # 2) Two rapid clicks: ~5 ms press-to-release, both inside one frame.
        for _ in range(2):
            button(disp, True)
            time.sleep(0.005)
            button(disp, False)
            time.sleep(0.03)
        # Nudge the pointer so the UI repaints even if nothing else changed.
        time.sleep(0.2)
        move_to_rel(disp, win, BTN_X + 4, BTN_Y + 3)
        time.sleep(0.8)
        grab(win, "shot2-after-rapid-clicks")

        print("done: expect clicks: 1 after slow, clicks: 3 after rapid")
        return 0
    finally:
        emu.terminate()
        try:
            emu.wait(timeout=5)
        except subprocess.TimeoutExpired:
            emu.kill()


if __name__ == "__main__":
    sys.exit(main())
