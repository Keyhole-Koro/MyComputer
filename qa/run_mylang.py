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
from qa.debug_session import DebugSession, copy_artifacts, default_session_dir, run_logged

GREEN = "32"
RED = "31"
CYAN = "36"
YELLOW = "33"

VERBOSE = False


def colored(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"


def status_line(label, message, color=CYAN):
    print(colored(f"[{label}]", color), message)


def run(cmd, cwd, description, session=None, log_name=None, quiet_fail=False):
    output = None
    if VERBOSE:
        status_line("RUN", " ".join(str(c) for c in cmd), CYAN)
    else:
        status_line("STEP", description, CYAN)
    try:
        if session is None:
            subprocess.check_call([str(c) for c in cmd], cwd=cwd)
        else:
            output = run_logged(cmd, cwd, description, session, log_name or f"{description}.log")
            if VERBOSE and output:
                print(output, end="")
    except subprocess.CalledProcessError as exc:
        if not quiet_fail:
            status_line("FAIL", description, RED)
            if session is not None:
                status_line("INFO", f"session: {session.session_dir}", YELLOW)
                tail = "\n".join((exc.output or "").strip().splitlines()[-20:])
                if tail:
                    print(tail)
        raise
    if VERBOSE:
        status_line("OK", description, GREEN)
    return output


def ensure_tools(session=None):
    run(["make", "-C", MYLANGCOMPILER_DIR, "all"], cwd=REPO_ROOT, description="build MyLangCompiler", session=session, log_name="01-build-mlc.log")
    run(["make", "-C", MYASSEMBLER_DIR, "all"], cwd=REPO_ROOT, description="build MyAssembler", session=session, log_name="02-build-myas.log")
    run(["make", "-C", MYLINKER_DIR, "all"], cwd=REPO_ROOT, description="build MyLinker", session=session, log_name="03-build-mllinker.log")
    try:
        run(
            ["make", "-C", MYEMULATOR_DIR, "all"],
            cwd=REPO_ROOT,
            description="build MyEmulator",
            session=session,
            log_name="04-build-myemu.log",
            quiet_fail=True,
        )
    except subprocess.CalledProcessError as exc:
        myemu = MYEMULATOR_DIR / "build" / "myemu"
        if "cargo: not found" not in (exc.output or "") or not myemu.exists():
            status_line("FAIL", "build MyEmulator", RED)
            if session is not None:
                status_line("INFO", f"session: {session.session_dir}", YELLOW)
                tail = "\n".join((exc.output or "").strip().splitlines()[-20:])
                if tail:
                    print(tail)
            raise
        status_line("INFO", f"cargo not found; using existing emulator: {myemu}", YELLOW)


def default_build_dir(sources):
    first = Path(sources[0]).stem if sources else "mylang"
    return QA_DIR / "outputs" / "run_mylang" / first


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
    parser = argparse.ArgumentParser(
        description="Build .mln/.masm sources and run the result in MyEmulator."
    )
    parser.add_argument("sources", nargs="+", help="Source files or directories (.mln and optional .masm)")
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

    global VERBOSE
    VERBOSE = args.verbose

    repo = REPO_ROOT
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
    status_line("INFO", f"session: {session.session_dir}", YELLOW)

    build_toolchain = QA_DIR / "build_toolchain.py"
    myemu = MYEMULATOR_DIR / "build" / "myemu"

    if not args.skip_build_tools:
        ensure_tools(session)

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

    run(build_cmd, cwd=repo, description="build MyLang image", session=session, log_name="05-build-image.log")

    status_line("INFO", f"linked image: {linked_bin}", YELLOW)
    status_line("INFO", f"artifacts dir: {build_dir}", YELLOW)
    copy_artifacts(build_dir, session)

    if args.no_run:
        status_line("DONE", "build complete; skipped emulator run", GREEN)
        return

    emu_cmd = [myemu, "-i", linked_bin]
    if args.headless:
        emu_cmd.append("--headless")
    emu_report = Path(args.emu_out).resolve() if args.emu_out else session.path("registers.txt")
    emu_cmd.extend(["-o", emu_report])
    emu_cmd.extend(["--log-dir", session.session_dir])
    if args.reg:
        emu_cmd.extend(["--reg", args.reg])
    if args.emu_verbose:
        emu_cmd.append("--verbose")
    if args.trace:
        emu_cmd.append("--trace")
    if args.break_addr:
        emu_cmd.extend(["--break", args.break_addr])
    if args.step:
        emu_cmd.extend(["--step", args.step])
    if args.mem:
        emu_cmd.extend(["--mem", args.mem[0], args.mem[1]])

    emulator_output = ""
    try:
        emulator_output = run(
            emu_cmd,
            cwd=repo,
            description="run emulator",
            session=session,
            log_name="06-emulator.log",
            quiet_fail=True,
        )
    except subprocess.CalledProcessError as exc:
        if "Unknown option: --log-dir" not in (exc.output or ""):
            raise
        status_line("INFO", "emulator does not support --log-dir; retrying legacy run", YELLOW)
        emulator_output = run(
            without_log_dir(emu_cmd),
            cwd=repo,
            description="run emulator (legacy)",
            session=session,
            log_name="06-emulator-legacy.log",
        )
    serial_path = session.path("serial.txt")
    debug_output_requested = args.trace or args.break_addr or args.step or args.mem or args.emu_verbose
    if serial_path.exists():
        serial_output = serial_path.read_text(encoding="utf-8", errors="replace").strip()
    elif debug_output_requested:
        serial_output = ""
    else:
        serial_output = extract_serial_output(emulator_output)
    if serial_output:
        status_line("PRINT", "serial output", YELLOW)
        print(serial_output)
    status_line("DONE", "MyLang program finished in emulator", GREEN)


if __name__ == "__main__":
    main()
