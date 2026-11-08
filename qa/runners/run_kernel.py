#!/usr/bin/env python3
"""
Build and run the sample kernel from MyKernel using the toolchain:
  .mln -> .masm (mlc) -> .mbin/.mobj (myas) -> linked .mbin (mllinker) -> run (myemu)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYKERNEL_DIR, MYOS_DIR, QA_DIR
from qa.runners.runner_common import (
    CYAN,
    GREEN,
    MYEMU,
    YELLOW,
    StepRunner,
    build_emulator,
    emulator_debug_args,
    print_serial_output,
    status_line,
)
from qa.tools.debug_session import DebugSession, copy_artifacts, default_session_dir


def main():
    parser = argparse.ArgumentParser(description="Build and run MyKernel sample.")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run.")
    parser.add_argument("--headless", action="store_true", help="Run emulator without display.")
    parser.add_argument("--verbose", action="store_true", help="Show full command output in the terminal.")
    parser.add_argument("--log-dir", help="Debug session directory (default: system/MyKernel/build/sessions/<timestamp>-kernel).")
    parser.add_argument("--trace", action="store_true", help="Pass --trace to emulator.")
    parser.add_argument("--break", dest="break_addr", help="Pass --break to emulator.")
    parser.add_argument("--step", help="Pass --step to emulator.")
    parser.add_argument("--mem", nargs=2, metavar=("ADDR", "LEN"), help="Pass --mem to emulator.")
    parser.add_argument(
        "--timer-interval",
        dest="timer_interval",
        help="Pass --timer-interval to emulator: the wall-clock tick period in microseconds. Below ~50000 the tick handler starves the guest; see run_system.py.",
    )
    parser.add_argument(
        "--profile",
        nargs="?",
        const="profile.json",
        help="Collect an instruction-level profile into the session directory. "
        "The kernel UI loop never halts, so pair with --step <n> to bound the run.",
    )
    parser.add_argument(
        "--source",
        help="Path to the MyLang entry source to build and run. Defaults to system/MyOS/src/boot/main.unsafe.mln",
    )
    parser.add_argument(
        "--stub",
        help="Path to the stub.masm file. Defaults to system/MyOS/src/boot/stub.masm",
    )
    args = parser.parse_args()

    kernel_dir = MYKERNEL_DIR
    build_dir = kernel_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    # System bring-up lives in MyOS: it starts the DOM, filesystem, compositor
    # and apps, and only hands the kernel its own init calls along the way.
    kernel_source = Path(args.source).resolve() if args.source else MYOS_DIR / "src" / "boot" / "main.unsafe.mln"
    kernel_stub = Path(args.stub).resolve() if args.stub else MYOS_DIR / "src" / "boot" / "stub.masm"
    linked_bin = build_dir / f"{kernel_source.stem}_linked.mbin"
    build_toolchain = QA_DIR / "runners" / "build_toolchain.py"

    if args.log_dir:
        session_dir = Path(args.log_dir).resolve()
    else:
        session_dir = default_session_dir(build_dir / "sessions", kernel_source.stem)
    session = DebugSession(session_dir, kernel_source.stem)
    steps = StepRunner(session, args.verbose, summarize_failures=False)
    report_path = session.path("registers.txt")

    status_line("INFO", f"session: {session.session_dir}", YELLOW)

    # Rebuild emulator so we always run the latest source.
    build_emulator(steps, description="build emulator", log_name="00-build-myemu.log")

    # Build kernel using toolchain script (stub must be first for entry point)
    steps.run(
        [
            sys.executable,
            build_toolchain,
            kernel_stub,
            kernel_source,
            "-o",
            linked_bin,
            "--build-dir",
            build_dir,
        ],
        description="build kernel image",
        log_name="01-build-kernel.log",
    )

    status_line("INFO", f"linked image: {linked_bin}", YELLOW)
    copy_artifacts(build_dir, session)

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    emu_cmd = [MYEMU, "-i", linked_bin, "-o", report_path, "--log-dir", session.session_dir]
    if args.headless:
        emu_cmd.append("--headless")
    emu_cmd += emulator_debug_args(args)
    if args.timer_interval:
        emu_cmd.extend(["--timer-interval", args.timer_interval])
    profile_path = None
    if args.profile:
        profile_path = session.path(args.profile)
        emu_cmd.extend(["--profile", profile_path])

    steps.run(emu_cmd, description="run emulator", log_name="02-emulator.log")
    print_serial_output(session, "kernel output")

    status_line("INFO", f"report: {report_path}", YELLOW)
    if profile_path and Path(profile_path).exists():
        status_line("INFO", f"profile: {profile_path}", YELLOW)
        status_line(
            "NEXT",
            f"python3 tools/MyProfiler/myprofiler.py report {profile_path} --image {linked_bin}",
            CYAN,
        )
    status_line("DONE", "kernel run complete", GREEN)


if __name__ == "__main__":
    main()
