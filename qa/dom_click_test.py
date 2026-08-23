#!/usr/bin/env python3
"""Headless DOM-based click test for the MyKernel counter UI (MYOS-004).

Replaces the real-window/XTEST approach in gui_click_test.py: no X server,
no window geometry, no pixel cropping. Drives myemu --control-stdio and
asserts against the DOM/accessibility tree instead of screenshots.

Assumes system/MyKernel + firmware have already been built by
qa/run_system.py --no-run into build/firmware_linked.mbin and
build/disk.img (with the kernel embedded -- see run_system.py for how the
disk image is laid out).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.project_paths import REPO_ROOT
from qa.mydomtester import launch, expect


def main() -> int:
    build_dir = REPO_ROOT / "build"
    firmware = build_dir / "firmware_linked.mbin"
    disk = build_dir / "disk.img"
    if not firmware.exists() or not disk.exists():
        print(f"FAIL: missing {firmware} or {disk}; run qa/run_system.py first")
        return 1

    page = launch(firmware, disk=disk)
    try:
        button = page.get_by_role("button", name="CLICK ME")
        expect(button).to_be_visible()

        button.click()
        expect(page.get_by_text("clicks: 1")).to_be_visible()

        button.click()
        button.click()
        expect(page.get_by_text("clicks: 3")).to_be_visible()

        print("PASS: clicks: 0 -> 1 -> 3 via headless DOM automation")
        return 0
    except AssertionError as e:
        print(f"FAIL: {e}")
        return 1
    finally:
        page.close()


if __name__ == "__main__":
    sys.exit(main())
