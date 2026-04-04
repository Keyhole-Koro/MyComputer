#!/usr/bin/env python3
"""
Build arbitrary MyLang sources into a linked .mbin and optionally run them in MyEmulator.

This is intended as a fast debug loop:
  .mln -> .masm (mlc) -> .mobj (myas) -> linked .mbin (mllinker) -> run (myemu)
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_paths import (
    MYASSEMBLER_DIR,
    MYEMULATOR_DIR,
    MYLANGCOMPILER_DIR,
    MYLINKER_DIR,
    QA_DIR,
    REPO_ROOT,
)

GREEN = "32"
RED = "31"
CYAN = "36"
YELLOW = "33"

VERBOSE = False


def colored(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"


def status_line(label, message, color=CYAN):
    print(colored(f"[{label}]", color), message)


def run(cmd, cwd, description):
    if VERBOSE:
        status_line("RUN", " ".join(str(c) for c in cmd), CYAN)
    else:
        status_line("STEP", description, CYAN)
    try:
        subprocess.check_call([str(c) for c in cmd], cwd=cwd)
    except subprocess.CalledProcessError:
        status_line("FAIL", description, RED)
        raise
    if VERBOSE:
        status_line("OK", description, GREEN)


def ensure_tools():
    run(["make", "-C", MYLANGCOMPILER_DIR, "all"], cwd=REPO_ROOT, description="build MyLangCompiler")
    run(["make", "-C", MYASSEMBLER_DIR, "all"], cwd=REPO_ROOT, description="build MyAssembler")
    run(["make", "-C", MYLINKER_DIR, "all"], cwd=REPO_ROOT, description="build MyLinker")
    run(["make", "-C", MYEMULATOR_DIR, "all"], cwd=REPO_ROOT, description="build MyEmulator")


def default_build_dir(sources):
    first = Path(sources[0]).stem if sources else "mylang"
    return QA_DIR / "outputs" / "run_mylang" / first


def main():
    parser = argparse.ArgumentParser(
        description="Build .mln/.masm sources and run the result in MyEmulator."
    )
    parser.add_argument("sources", nargs="+", help="Source files or directories (.mln and optional .masm)")
    parser.add_argument("--entry", default="main", help="Entry function name passed to mlc (default: main)")
    parser.add_argument("--build-dir", help="Directory for intermediate outputs and final linked image")
    parser.add_argument("-o", "--out", help="Output linked .mbin path (default: <build-dir>/linked.mbin)")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude relative path or directory name")
    parser.add_argument("--masm", action="store_true", help="Include .masm files when scanning directories")
    parser.add_argument("--clean", action="store_true", help="Clean build dir before build")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run")
    parser.add_argument("--reg", help="Pass --reg to emulator for a final register value")
    parser.add_argument("--emu-out", help="Pass -o to emulator to write the register report")
    parser.add_argument("--emu-verbose", action="store_true", help="Run emulator in verbose mode")
    parser.add_argument("--skip-build-tools", action="store_true", help="Skip rebuilding mlc/myas/mllinker/myemu")
    parser.add_argument("--verbose", action="store_true", help="Show executed commands")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    repo = REPO_ROOT
    build_dir = Path(args.build_dir).resolve() if args.build_dir else default_build_dir(args.sources).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    linked_bin = Path(args.out).resolve() if args.out else build_dir / "linked.mbin"

    build_toolchain = QA_DIR / "build_toolchain.py"
    myemu = MYEMULATOR_DIR / "build" / "myemu"

    if not args.skip_build_tools:
        ensure_tools()

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

    run(build_cmd, cwd=repo, description="build MyLang image")

    status_line("INFO", f"linked image: {linked_bin}", YELLOW)
    status_line("INFO", f"artifacts dir: {build_dir}", YELLOW)

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    emu_cmd = [myemu, "-i", linked_bin]
    if args.emu_out:
        emu_cmd.extend(["-o", args.emu_out])
    if args.reg:
        emu_cmd.extend(["--reg", args.reg])
    if args.emu_verbose:
        emu_cmd.append("--verbose")

    run(emu_cmd, cwd=repo, description="run emulator")
    status_line("DONE", "MyLang program finished in emulator", GREEN)


if __name__ == "__main__":
    main()
