#!/usr/bin/env python3
"""
Build and run the full MyComputer system:
  1. Build MyFirmware -> firmware_linked.mbin
  2. Build MyKernel -> kernel_linked.mbin
  3. Run emulator with firmware in ROM and a disk image.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYEMULATOR_DIR, MYOS_DIR, QA_DIR, REPO_ROOT
from qa.runners.runner_common import GREEN, MYEMU, RED, YELLOW, StepRunner, status_line
from qa.tools.debug_session import DebugSession, default_session_dir

MYFIRMWARE_DIR = REPO_ROOT / "system" / "MyFirmware"

def main():
    parser = argparse.ArgumentParser(description="Build and run MyComputer system.")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run.")
    parser.add_argument("--headless", action="store_true", help="Run emulator without display.")
    parser.add_argument("--verbose", action="store_true", help="Show full command output in the terminal.")
    parser.add_argument(
        "--screenshot", metavar="PATH",
        help="Run headless until the first idle (the desktop has painted), save the frame "
             "as PNG/PPM at PATH, and exit.",
    )
    args = parser.parse_args()

    build_dir = REPO_ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    fw_source = MYFIRMWARE_DIR / "src" / "fw" / "main.unsafe.mln"
    fw_stub = MYFIRMWARE_DIR / "src" / "boot" / "stub.masm"
    fw_jump = MYFIRMWARE_DIR / "src" / "fw" / "jump.masm"
    fw_bin = build_dir / "firmware_linked.mbin"

    # The entry point is MyOS's: see system/MyOS/src/boot/main.unsafe.mln.
    kernel_source = MYOS_DIR / "src" / "boot" / "main.unsafe.mln"
    kernel_stub = MYOS_DIR / "src" / "boot" / "stub.masm"
    kernel_bin = build_dir / "kernel_linked.mbin"

    build_toolchain = QA_DIR / "runners" / "build_toolchain.py"
    disk_img = build_dir / "disk.img"

    session_dir = default_session_dir(build_dir / "sessions", "system")
    session = DebugSession(session_dir, "system")
    steps = StepRunner(session, args.verbose)
    report_path = session.path("registers.txt")

    status_line("INFO", f"session: {session.session_dir}", YELLOW)

    # 1. Build emulator
    steps.run(
        ["make", "-C", MYEMULATOR_DIR, "all"],
        description="build emulator",
        log_name="00-build-myemu.log",
    )

    # 2. Build Firmware
    steps.run(
        cmd=[
            sys.executable, build_toolchain,
            fw_stub, fw_source, fw_jump,
            "-o", fw_bin,
            "--build-dir", build_dir
        ],
        description="build firmware image",
        log_name="01-build-firmware.log",
    )

    # 3. Build Kernel
    steps.run(
        [sys.executable, build_toolchain, kernel_stub, kernel_source, "-o", kernel_bin, "--build-dir", build_dir, "--base", "0x00100000"],
        description="build kernel image",
        log_name="02-build-kernel.log",
    )

    # 4. Build the user-space programs (system/MyOS/user/apps -> build/user).
    steps.run(
        [sys.executable, QA_DIR / "runners" / "build_user_apps.py", "--quiet"],
        description="build user programs",
        log_name="03-build-user.log",
    )

    # 5. Make the disk image: an MFS filesystem holding the user programs and
    # a few sample files, with the kernel embedded at block 16000 for the
    # firmware to load. Built even under --no-run: a caller that wants a
    # launchable image without running it here (e.g. MyDOMTester driving
    # myemu --control-stdio itself) needs disk.img to exist.
    # Console programs go to /bin, desktop apps to /apps (the shell lists
    # the executables in /apps at boot; the spawn path searches both).
    # The firmware loads KERNEL_BLOCKS blocks of the kernel image (see
    # system/MyFirmware/src/fw/main.unsafe.mln); a bigger image boots half-loaded.
    KERNEL_BLOCKS = 16
    kernel_size = kernel_bin.stat().st_size
    if kernel_size > KERNEL_BLOCKS * 65536:
        status_line("FAIL", f"kernel image is {kernel_size} bytes, more than the firmware loads ({KERNEL_BLOCKS} x 64 KB)", RED)
        sys.exit(1)
    mkfs_cmd = [sys.executable, REPO_ROOT / "tools" / "mkfs.py", disk_img, "--kernel", kernel_bin,
                "--dir", "bin", "--dir", "apps"]
    gui_apps = {p.name[: -len(".dom.mln")] for p in (MYOS_DIR / "src" / "apps").glob("*.dom.mln")}
    for mbin in sorted((build_dir / "user").glob("*.mbin")):
        folder = "apps" if mbin.stem in gui_apps else "bin"
        mkfs_cmd += ["--file", f"{folder}/{mbin.stem}={mbin}"]
    mkfs_cmd += [
        "--text", "readme.txt=Welcome to MyOS.\n\nThis file lives on the MFS disk image.\n"
                  "Open it from Files, edit it in the editor, and run the user\n"
                  "programs (hello, echo, count) from the Terminal.\n",
        "--text", "todo.txt=- write more apps\n- add a network stack\n",
    ]
    steps.run(mkfs_cmd, description="make disk image (mkfs)", log_name="04-mkfs.log")

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    # 4. Run emulator.
    # --timer-interval is a real-time tick period in microseconds. 1000 us = 1 ms
    # = a ~1 kHz scheduler tick, which keeps the UI poll/redraw smooth. (It used
    # to be an instruction count; the timer is now wall-clock driven so the CPU
    # can idle on WFI without stalling the timer.)
    #
    # A period this short used to starve the guest: the handler outlasted it, so
    # the next tick was already due the moment it returned and nothing but
    # interrupts ever ran -- the first frame never finished drawing. The timer
    # now also requires a minimum number of retired instructions between ticks
    # (MIN_INSTRS_PER_TICK in runtime/MyEmulator/src/machine/timer.rs), so a tick
    # is delayed rather than allowed to crowd the guest out, and the period is
    # once again just an upper bound on the tick rate.
    emu_cmd = [str(MYEMU), "-i", str(fw_bin), "--disk", str(disk_img), "-o", str(report_path), "--log-dir", str(session.session_dir), "--timer-interval", "1000"]
    if args.headless or args.screenshot:
        emu_cmd.append("--headless")
    if args.screenshot:
        # --step makes the emulator stop at the first WFI, which is right
        # after the compositor painted the desktop and went idle; the
        # screenshot is then written from the presented frame.
        emu_cmd += ["--step", "200000000", "--screenshot", str(Path(args.screenshot).resolve())]

    steps.run(
        emu_cmd,
        description="run emulator",
        log_name="05-run-emulator.log",
        echo_output=True,
    )

    if args.screenshot:
        status_line("DONE", f"screenshot written to {args.screenshot}", GREEN)
    else:
        status_line("DONE", "system run complete", GREEN)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
