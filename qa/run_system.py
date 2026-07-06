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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_paths import MYEMULATOR_DIR, MYKERNEL_DIR, QA_DIR, REPO_ROOT
from qa.debug_session import DebugSession, copy_artifacts, default_session_dir, run_logged

GREEN = "32"
RED = "31"
YELLOW = "33"
CYAN = "36"
VERBOSE = False

MYFIRMWARE_DIR = REPO_ROOT / "system" / "MyFirmware"

def colored(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"

def status_line(label, message, color=CYAN):
    print(colored(f"[{label}]", color), message)

def run_step(cmd, cwd, description, session: DebugSession, log_name: str, quiet_fail=False):
    if VERBOSE:
        status_line("RUN", " ".join(str(c) for c in cmd), CYAN)
    else:
        status_line("STEP", description, CYAN)

    try:
        output = run_logged(cmd, cwd, description, session, log_name)
    except subprocess.CalledProcessError as exc:
        if not quiet_fail:
            status_line("FAIL", description, RED)
            status_line("INFO", f"session: {session.session_dir}", YELLOW)
            tail = "\n".join((exc.output or "").strip().splitlines()[-20:])
            if tail:
                print(tail)
        raise

    if VERBOSE and output:
        print(output, end="")
        status_line("OK", description, GREEN)

    return output

def main():
    parser = argparse.ArgumentParser(description="Build and run MyComputer system.")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run.")
    parser.add_argument("--headless", action="store_true", help="Run emulator without display.")
    parser.add_argument("--verbose", action="store_true", help="Show full command output in the terminal.")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    repo = REPO_ROOT
    build_dir = REPO_ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    fw_source = MYFIRMWARE_DIR / "src" / "fw" / "main.mln"
    fw_stub = MYFIRMWARE_DIR / "src" / "boot" / "stub.masm"
    fw_bin = build_dir / "firmware_linked.mbin"

    kernel_source = MYKERNEL_DIR / "src" / "kernel" / "main.mln"
    kernel_stub = MYKERNEL_DIR / "src" / "boot" / "stub.masm"
    kernel_bin = build_dir / "kernel_linked.mbin"

    build_toolchain = QA_DIR / "build_toolchain.py"
    myemu = MYEMULATOR_DIR / "target" / "release" / "myemu"
    disk_img = build_dir / "disk.img"

    session_dir = default_session_dir(build_dir / "sessions", "system")
    session = DebugSession(session_dir, "system")
    report_path = session.path("registers.txt")

    status_line("INFO", f"session: {session.session_dir}", YELLOW)

    # 1. Build emulator
    try:
        run_step(
            ["make", "-C", MYEMULATOR_DIR, "all"],
            cwd=repo,
            description="build emulator",
            session=session,
            log_name="00-build-myemu.log",
            quiet_fail=True,
        )
    except subprocess.CalledProcessError:
        pass

    # 2. Build Firmware
    run_step(
        [sys.executable, build_toolchain, fw_stub, fw_source, "-o", fw_bin, "--build-dir", build_dir],
        cwd=repo,
        description="build firmware image",
        session=session,
        log_name="01-build-firmware.log",
    )

    # 3. Build Kernel
    run_step(
        [sys.executable, build_toolchain, kernel_stub, kernel_source, "-o", kernel_bin, "--build-dir", build_dir],
        cwd=repo,
        description="build kernel image",
        session=session,
        log_name="02-build-kernel.log",
    )

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    # TODO: In the future, we should write kernel_bin into disk_img so firmware can load it!
    # For now, we just pass disk.img to the emulator.
    emu_cmd = [myemu, "-i", fw_bin, "--disk", disk_img, "-o", report_path, "--log-dir", session.session_dir]
    if args.headless:
        emu_cmd.append("--headless")

    run_step(
        emu_cmd,
        cwd=repo,
        description="run emulator",
        session=session,
        log_name="03-emulator.log",
        quiet_fail=True,
    )

    status_line("DONE", "system run complete", GREEN)

if __name__ == "__main__":
    main()
