#!/usr/bin/env python3
"""
Build arbitrary MyLang sources into a linked .mbin and optionally run them in MyEmulator.

This is intended as a fast debug loop:
  .mln -> .masm (mlc) -> .mobj (myas) -> linked .mbin (mllinker) -> run (myemu)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYASSEMBLER_DIR, MYLANGCOMPILER_DIR, MYLINKER_DIR, QA_DIR
from qa.runners.runner_common import (
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


def ensure_tools(steps):
    steps.run(["make", "-C", MYLANGCOMPILER_DIR, "all"], description="build MyLangCompiler", log_name="01-build-mlc.log")
    steps.run(["make", "-C", MYASSEMBLER_DIR, "all"], description="build MyAssembler", log_name="02-build-myas.log")
    steps.run(["make", "-C", MYLINKER_DIR, "all"], description="build MyLinker", log_name="03-build-mllinker.log")
    build_emulator(steps, description="build MyEmulator", log_name="04-build-myemu.log")


def default_build_dir(sources):
    first = Path(sources[0]).stem if sources else "mylang"
    return QA_DIR / "outputs" / "run_mylang" / first


def main():
    parser = argparse.ArgumentParser(
        description="Build .mlx/.mln/.masm sources and run the result in MyEmulator."
    )
    parser.add_argument("sources", nargs="+", help="Source files or directories (.mlx/.mln and optional .masm)")
    parser.add_argument("--entry", default="main", help="Entry function name passed to mlc (default: main)")
    parser.add_argument("--build-dir", help="Directory for intermediate outputs and final linked image")
    parser.add_argument("--headless", action="store_true", help="Run emulator without display.")
    parser.add_argument("-o", "--out", help="Output linked .mbin path (default: <build-dir>/linked.mbin)")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude relative path or directory name")
    parser.add_argument("--masm", action="store_true", help="Include .masm files when scanning directories")
    parser.add_argument("--clean", action="store_true", help="Clean build dir before build")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run")
    parser.add_argument("--reg", help="Pass --reg to emulator for a final register value")
    parser.add_argument("--emu-out", help="Pass -o to emulator to write the register report")
    parser.add_argument("--emu-verbose", action="store_true", help="Run emulator in verbose mode")
    parser.add_argument("--trace", action="store_true", help="Pass --trace to emulator")
    parser.add_argument("--break", dest="break_addr", help="Pass --break to emulator")
    parser.add_argument("--step", help="Pass --step to emulator")
    parser.add_argument("--mem", nargs=2, metavar=("ADDR", "LEN"), help="Pass --mem to emulator")
    parser.add_argument("--log-dir", help="Debug session directory (default: qa/outputs/sessions/<timestamp>-<name>)")
    parser.add_argument("--skip-build-tools", action="store_true", help="Skip rebuilding mlc/myas/mllinker/myemu")
    parser.add_argument("--verbose", action="store_true", help="Show executed commands")
    args = parser.parse_args()

    build_dir = Path(args.build_dir).resolve() if args.build_dir else default_build_dir(args.sources).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    linked_bin = Path(args.out).resolve() if args.out else build_dir / "linked.mbin"
    session_name = Path(args.sources[0]).stem if args.sources else "mylang"
    session_dir = Path(args.log_dir).resolve() if args.log_dir else default_session_dir(QA_DIR / "outputs" / "sessions", session_name)
    session = DebugSession(session_dir, session_name)
    session.write_manifest(
        {
            "sources": [str(Path(s).resolve()) for s in args.sources],
            "build_dir": str(build_dir),
            "linked_image": str(linked_bin),
            "entry": args.entry,
        }
    )
    steps = StepRunner(session, args.verbose, summarize_failures=False)
    status_line("INFO", f"session: {session.session_dir}", YELLOW)

    build_toolchain = QA_DIR / "runners" / "build_toolchain.py"

    if not args.skip_build_tools:
        ensure_tools(steps)

    build_cmd = [
        sys.executable,
        build_toolchain,
        *args.sources,
        "-o",
        linked_bin,
        "--build-dir",
        build_dir,
        "--entry",
        args.entry,
    ]
    if args.masm:
        build_cmd.append("--masm")
    if args.clean:
        build_cmd.append("--clean")
    for ex in args.exclude:
        build_cmd.extend(["--exclude", ex])

    steps.run(build_cmd, description="build MyLang image", log_name="05-build-image.log")

    status_line("INFO", f"linked image: {linked_bin}", YELLOW)
    status_line("INFO", f"artifacts dir: {build_dir}", YELLOW)
    copy_artifacts(build_dir, session)

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    emu_cmd = [MYEMU, "-i", linked_bin]
    if args.headless:
        emu_cmd.append("--headless")
    emu_report = Path(args.emu_out).resolve() if args.emu_out else session.path("registers.txt")
    emu_cmd.extend(["-o", emu_report])
    emu_cmd.extend(["--log-dir", session.session_dir])
    if args.reg:
        emu_cmd.extend(["--reg", args.reg])
    if args.emu_verbose:
        emu_cmd.append("--verbose")
    emu_cmd += emulator_debug_args(args)

    steps.run(emu_cmd, description="run emulator", log_name="06-emulator.log")
    print_serial_output(session, "serial output")
    status_line("DONE", "MyLang program finished in emulator", GREEN)


if __name__ == "__main__":
    main()
