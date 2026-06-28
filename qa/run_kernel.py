#!/usr/bin/env python3
"""
Build and run the sample kernel from MyKernel using the toolchain:
  .mln -> .masm (mlc) -> .mbin/.mobj (myas) -> linked .mbin (mllinker) -> run (myemu)
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


def extract_serial_output(emulator_output: str) -> str:
    lines = emulator_output.splitlines()
    serial_lines = []
    seen_load = False

    for line in lines:
        if not seen_load:
            if line.startswith("Loading binary from "):
                seen_load = True
            continue
        if line.startswith("Stack Contents:"):
            break
        serial_lines.append(line)

    return "\n".join(serial_lines).strip()


def without_log_dir(cmd):
    stripped = []
    skip_next = False
    for item in cmd:
        if skip_next:
            skip_next = False
            continue
        if str(item) == "--log-dir":
            skip_next = True
            continue
        stripped.append(item)
    return stripped


def main():
    parser = argparse.ArgumentParser(description="Build and run MyKernel sample.")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run.")
    parser.add_argument("--headless", action="store_true", help="Run emulator without display.")
    parser.add_argument("--verbose", action="store_true", help="Show full command output in the terminal.")
    parser.add_argument(
        "--log-file",
        help="Compatibility alias for --log-dir; parent directory is used as the debug session directory.",
    )
    parser.add_argument("--log-dir", help="Debug session directory (default: system/MyKernel/build/sessions/<timestamp>-kernel).")
    parser.add_argument("--trace", action="store_true", help="Pass --trace to emulator.")
    parser.add_argument("--break", dest="break_addr", help="Pass --break to emulator.")
    parser.add_argument("--step", help="Pass --step to emulator.")
    parser.add_argument("--mem", nargs=2, metavar=("ADDR", "LEN"), help="Pass --mem to emulator.")
    parser.add_argument(
        "--timer-interval",
        dest="timer_interval",
        help="Pass --timer-interval to emulator (raise a timer IRQ every N instructions).",
    )
    parser.add_argument(
        "--source",
        help="Path to the MyLang kernel source file to build and run. Defaults to system/MyKernel/src/kernel_main.mln",
    )
    parser.add_argument(
        "--stub",
        help="Path to the stub.masm file. Defaults to system/MyKernel/src/stub.masm",
    )
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    repo = REPO_ROOT
    kernel_dir = MYKERNEL_DIR
    build_dir = kernel_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    kernel_source = Path(args.source).resolve() if args.source else kernel_dir / "src" / "kernel_main.mln"
    kernel_stub = Path(args.stub).resolve() if args.stub else kernel_dir / "src" / "stub.masm"
    linked_bin = build_dir / f"{kernel_source.stem}_linked.mbin"
    build_toolchain = QA_DIR / "build_toolchain.py"
    myemu = MYEMULATOR_DIR / "build" / "myemu"

    if args.log_dir:
        session_dir = Path(args.log_dir).resolve()
    elif args.log_file:
        session_dir = Path(args.log_file).resolve().parent
    else:
        session_dir = default_session_dir(build_dir / "sessions", kernel_source.stem)
    session = DebugSession(session_dir, kernel_source.stem)
    report_path = session.path("registers.txt")

    status_line("INFO", f"session: {session.session_dir}", YELLOW)

    # Build kernel using toolchain script (stub must be first for entry point)
    run_step(
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
        cwd=repo,
        description="build kernel image",
        session=session,
        log_name="01-build-kernel.log",
    )

    status_line("INFO", f"linked image: {linked_bin}", YELLOW)
    copy_artifacts(build_dir, session)

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    emu_cmd = [myemu, "-i", linked_bin, "-o", report_path, "--log-dir", session.session_dir]
    if args.headless:
        emu_cmd.append("--headless")
    if args.trace:
        emu_cmd.append("--trace")
    if args.break_addr:
        emu_cmd.extend(["--break", args.break_addr])
    if args.step:
        emu_cmd.extend(["--step", args.step])
    if args.mem:
        emu_cmd.extend(["--mem", args.mem[0], args.mem[1]])
    if args.timer_interval:
        emu_cmd.extend(["--timer-interval", args.timer_interval])

    try:
        emulator_output = run_step(
            emu_cmd,
            cwd=repo,
            description="run emulator",
            session=session,
            log_name="02-emulator.log",
            quiet_fail=True,
        )
    except subprocess.CalledProcessError as exc:
        if "Unknown option: --log-dir" not in (exc.output or ""):
            raise
        status_line("INFO", "emulator does not support --log-dir; retrying legacy run", YELLOW)
        emulator_output = run_step(
            without_log_dir(emu_cmd),
            cwd=repo,
            description="run emulator (legacy)",
            session=session,
            log_name="02-emulator-legacy.log",
        )

    serial_path = session.path("serial.txt")
    debug_output_requested = args.trace or args.break_addr or args.step or args.mem
    if serial_path.exists():
        serial_output = serial_path.read_text(encoding="utf-8", errors="replace").strip()
    elif debug_output_requested:
        serial_output = ""
    else:
        serial_output = extract_serial_output(emulator_output)
    if serial_output:
        status_line("PRINT", "kernel output", YELLOW)
        print(serial_output)

    status_line("INFO", f"report: {report_path}", YELLOW)
    status_line("DONE", "kernel run complete", GREEN)


if __name__ == "__main__":
    main()
