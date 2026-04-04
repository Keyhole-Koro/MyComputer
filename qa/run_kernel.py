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

from tools.project_paths import (
    MYASSEMBLER_DIR,
    MYEMULATOR_DIR,
    MYKERNEL_DIR,
    MYLANGCOMPILER_DIR,
    MYLINKER_DIR,
    QA_DIR,
    REPO_ROOT,
)

GREEN = "32"
RED = "31"
YELLOW = "33"
CYAN = "36"
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
        subprocess.check_call(cmd, cwd=cwd)
    except subprocess.CalledProcessError:
        status_line("FAIL", description, RED)
        raise
    if VERBOSE:
        status_line("OK", description, GREEN)


def main():
    parser = argparse.ArgumentParser(description="Build and run MyKernel sample.")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run.")
    parser.add_argument("--verbose", action="store_true", help="Show executed commands")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    repo = REPO_ROOT
    kernel_dir = MYKERNEL_DIR
    build_dir = kernel_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    # Tool paths
    mlc = MYLANGCOMPILER_DIR / "mlc"
    myas = MYASSEMBLER_DIR / "build" / "myas"
    mllinker = MYLINKER_DIR / "mllinker"
    myemu = MYEMULATOR_DIR / "build" / "myemu"

    # Sources
    kernel_ml = kernel_dir / "src" / "kernel_main.mln"
    stub_masm = kernel_dir / "asm" / "stub.masm"

    linked_bin = build_dir / "kernel_linked.mbin"

    build_toolchain = QA_DIR / "build_toolchain.py"

    # Build kernel using toolchain script (stub must be first for entry point)
    run([
        sys.executable, build_toolchain,
        stub_masm, kernel_ml,
        "-o", linked_bin,
        "--build-dir", build_dir
    ], cwd=repo, description="build kernel image")

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    # Run emulator
    run([myemu, "-i", linked_bin], cwd=repo, description="run emulator")
    status_line("DONE", "kernel run complete; see memory_dump.txt for RAM snapshot", GREEN)


if __name__ == "__main__":
    main()
