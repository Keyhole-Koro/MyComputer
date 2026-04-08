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

GREEN = "32"
RED = "31"
YELLOW = "33"
CYAN = "36"
VERBOSE = False


def colored(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"


def status_line(label, message, color=CYAN):
    print(colored(f"[{label}]", color), message)


def append_log(log_path: Path, title: str, text: str):
    with log_path.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n===== {title} =====\n")
        fh.write(text)
        if text and not text.endswith("\n"):
            fh.write("\n")


def run_logged(cmd, cwd, description, log_path: Path):
    if VERBOSE:
        status_line("RUN", " ".join(str(c) for c in cmd), CYAN)
    else:
        status_line("STEP", description, CYAN)

    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    command_line = "+ " + " ".join(str(c) for c in cmd) + "\n"
    append_log(log_path, description, command_line + proc.stdout)

    if proc.returncode != 0:
        status_line("FAIL", description, RED)
        status_line("INFO", f"log: {log_path}", YELLOW)
        tail = "\n".join(proc.stdout.strip().splitlines()[-20:])
        if tail:
            print(tail)
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    if VERBOSE and proc.stdout:
        print(proc.stdout, end="")
        status_line("OK", description, GREEN)

    return proc.stdout


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


def main():
    parser = argparse.ArgumentParser(description="Build and run MyKernel sample.")
    parser.add_argument("--no-run", action="store_true", help="Build only; skip emulator run.")
    parser.add_argument("--verbose", action="store_true", help="Show full command output in the terminal.")
    parser.add_argument(
        "--log-file",
        help="Path to the combined build/run log file (default: system/MyKernel/build/run_kernel.log).",
    )
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    repo = REPO_ROOT
    kernel_dir = MYKERNEL_DIR
    build_dir = kernel_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    linked_bin = build_dir / "kernel_linked.mbin"
    build_toolchain = QA_DIR / "build_toolchain.py"
    myemu = MYEMULATOR_DIR / "build" / "myemu"

    log_path = Path(args.log_file).resolve() if args.log_file else (build_dir / "run_kernel.log")
    report_path = build_dir / "emulator_report.txt"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    status_line("INFO", f"log: {log_path}", YELLOW)

    # Build kernel using toolchain script (stub must be first for entry point)
    run_logged(
        [
            sys.executable,
            build_toolchain,
            kernel_dir / "src" / "stub.masm",
            kernel_dir / "src" / "kernel_main.mln",
            "-o",
            linked_bin,
            "--build-dir",
            build_dir,
        ],
        cwd=repo,
        description="build kernel image",
        log_path=log_path,
    )

    status_line("INFO", f"linked image: {linked_bin}", YELLOW)

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    emulator_output = run_logged(
        [myemu, "-i", linked_bin, "-o", report_path],
        cwd=repo,
        description="run emulator",
        log_path=log_path,
    )

    serial_output = extract_serial_output(emulator_output)
    if serial_output:
        status_line("PRINT", "kernel output", YELLOW)
        print(serial_output)

    status_line("INFO", f"report: {report_path}", YELLOW)
    status_line("DONE", "kernel run complete", GREEN)


if __name__ == "__main__":
    main()
