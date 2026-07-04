#!/usr/bin/env python3
"""
Run every test suite in the project with one command.

Two phases:

  1. Build — for each toolchain/runtime component, invoke its Makefile. `make`
     does an incremental build (using the build system's own cache), so an
     already-current binary is reused. If the build fails, the component is
     cleaned and rebuilt once from scratch; a second failure marks every suite
     that depends on it as failed without running it.

  2. Test — each suite runs in its own process, in parallel (suite-level
     granularity). Results are tallied into a summary; a single failure makes
     the whole run exit non-zero, so this is safe to call straight from CI.

Usage:
  python3 qa/test-all.py [--verbose] [--jobs N] [--no-build] [suite ...]

  suite     restrict to named suites (default: all). Known suites are listed
            below in SUITES.
  --jobs    max parallel suites (default: CPU count).
  --no-build  skip phase 1 and use whatever binaries already exist.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_paths import (
    MYASSEMBLER_DIR,
    MYEMULATOR_DIR,
    MYKERNEL_DIR,
    MYLANGCOMPILER_DIR,
    MYLANGTESTER_DIR,
    MYLINKER_DIR,
    REPO_ROOT,
)

GREEN, RED, CYAN, YELLOW = "32", "31", "36", "33"


def colored(text, code):
    return f"\033[{code}m{text}\033[0m"


def status(label, msg, code=CYAN):
    print(colored(f"[{label}]", code), msg, flush=True)


# ---------------------------------------------------------------------------
# Phase 1: build components via their Makefiles.
# ---------------------------------------------------------------------------

# name -> (directory, make target, produced artifact)
COMPONENTS = {
    "mlc":   (MYLANGCOMPILER_DIR, "mlc", MYLANGCOMPILER_DIR / "mlc"),
    "mytest": (MYLANGTESTER_DIR, "all", MYLANGTESTER_DIR / "build" / "mytest"),
    "myas":  (MYASSEMBLER_DIR, "all", MYASSEMBLER_DIR / "build" / "myas"),
    "mllinker": (MYLINKER_DIR, "all", MYLINKER_DIR / "mllinker"),
    "myemu": (MYEMULATOR_DIR, "all", MYEMULATOR_DIR / "build" / "myemu"),
}


def _make(directory, target, verbose):
    proc = subprocess.run(
        ["make", target], cwd=directory,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if verbose and proc.stdout:
        print(proc.stdout, flush=True)
    return proc


def build_component(name, verbose):
    """Build one component, retrying once from clean on failure.

    Returns (ok, detail). On the retry path we run `make clean` then rebuild,
    so a stale or corrupt incremental cache cannot wedge the run.
    """
    directory, target, artifact = COMPONENTS[name]
    proc = _make(directory, target, verbose)
    if proc.returncode == 0 and artifact.exists():
        return True, "up to date" if not verbose else "built"

    status("WARN", f"{name}: build failed, cleaning and rebuilding", YELLOW)
    subprocess.run(["make", "clean"], cwd=directory,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = _make(directory, target, verbose)
    if proc.returncode == 0 and artifact.exists():
        return True, "rebuilt from clean"
    tail = proc.stdout[-800:] if proc.stdout else "(no output)"
    return False, f"build failed after clean:\n{tail}"


# ---------------------------------------------------------------------------
# Phase 2: test suites. Each maps to a runner command and the components it
# needs; if a needed component failed to build, the suite is skipped-as-failed.
# ---------------------------------------------------------------------------

# name -> (runner argv, [required components])
SUITES = {
    "compiler": (
        ["python3", str(MYLANGCOMPILER_DIR / "tests" / "run_integration_tests.py")],
        ["mlc"],
    ),
    "assembler": (
        ["python3", str(MYASSEMBLER_DIR / "tests" / "run_integration_tests.py")],
        ["myas"],
    ),
    "linker": (
        ["python3", str(MYLINKER_DIR / "test" / "run_integration_tests.py")],
        ["mllinker"],
    ),
    "heap": (
        ["python3", str(MYKERNEL_DIR / "tests" / "run_heap_tests.py")],
        ["mlc", "myas", "mllinker", "myemu"],
    ),
    "serial-rx": (
        [str(MYLANGTESTER_DIR / "build" / "mytest"), str(MYKERNEL_DIR / "tests" / "serial_rx.test.mln")],
        ["mlc", "mytest", "myas", "mllinker", "myemu"],
    ),
    "scheduler": (
        ["python3", str(MYKERNEL_DIR / "tests" / "run_scheduler_test.py")],
        ["mlc", "myas", "mllinker", "myemu"],
    ),
}


def run_suite(name):
    """Run one suite in a child process. Returns (name, ok, output)."""
    argv, _ = SUITES[name]
    proc = subprocess.run(
        argv, cwd=REPO_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return name, proc.returncode == 0, proc.stdout


def main():
    ap = argparse.ArgumentParser(description="Run all project test suites.")
    ap.add_argument("suites", nargs="*", help="restrict to these suites")
    ap.add_argument("--verbose", action="store_true",
                    help="stream build and suite output")
    ap.add_argument("--jobs", type=int, default=None,
                    help="max parallel suites (default: CPU count)")
    ap.add_argument("--no-build", action="store_true",
                    help="skip the build phase, use existing binaries")
    args = ap.parse_args()

    selected = args.suites or list(SUITES)
    unknown = [s for s in selected if s not in SUITES]
    if unknown:
        print(f"[ERROR] unknown suite(s): {', '.join(unknown)}. "
              f"Known: {', '.join(SUITES)}")
        return 2

    # Which components do the selected suites actually need?
    needed = set()
    for s in selected:
        needed.update(SUITES[s][1])

    failed_builds = set()
    if args.no_build:
        status("INFO", "skipping build phase (--no-build)", YELLOW)
    else:
        status("BUILD", f"building: {', '.join(sorted(needed))}")
        for name in sorted(needed):
            ok, detail = build_component(name, args.verbose)
            if ok:
                status("OK", f"{name}: {detail}", GREEN)
            else:
                status("FAIL", f"{name}: {detail}", RED)
                failed_builds.add(name)

    # Run suites whose components all built; mark the rest failed-without-running.
    runnable, blocked = [], []
    for s in selected:
        if set(SUITES[s][1]) & failed_builds:
            blocked.append(s)
        else:
            runnable.append(s)

    results = {}
    for s in blocked:
        bad = ", ".join(sorted(set(SUITES[s][1]) & failed_builds))
        results[s] = (False, f"skipped: dependency build failed ({bad})")

    if runnable:
        status("TEST", f"running {len(runnable)} suite(s) in parallel")
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(run_suite, s): s for s in runnable}
            for fut in as_completed(futures):
                name, ok, output = fut.result()
                results[name] = (ok, output)
                label, code = ("PASS", GREEN) if ok else ("FAIL", RED)
                status(label, name, code)
                if args.verbose and output:
                    print(output, flush=True)

    # Summary, in the declared order for stable reading.
    print()
    status("SUMMARY", "results:")
    passed = 0
    for s in selected:
        ok, detail = results[s]
        if ok:
            passed += 1
            print(f"  {colored('PASS', GREEN)}  {s}")
        else:
            print(f"  {colored('FAIL', RED)}  {s}")
            if not args.verbose and detail and detail.startswith("skipped"):
                print(f"        {detail}")

    total = len(selected)
    code = GREEN if passed == total else RED
    status("DONE", f"{passed}/{total} suites passed", code)
    if passed != total and not args.verbose:
        status("INFO", "re-run with --verbose to see failing suite output", CYAN)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
