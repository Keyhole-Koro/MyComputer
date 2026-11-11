#!/usr/bin/env python3
"""
Run every test suite in the project with one command.

Two phases:

  1. Build — for each toolchain/runtime component, invoke its Makefile. `make`
     does an incremental build (using the build system's own cache), so an
     already-current binary is reused. If the build fails, the component is
     cleaned and rebuilt once from scratch; a second failure marks every suite
     that depends on it as failed without running it.

  2. Test — component-local suites run in parallel. Cross-component E2E suites
     run serially because their component-owned runners may perform incremental
     builds of shared toolchain dependencies. Results are tallied into a
     summary; a single failure makes the whole run exit non-zero.

Usage:
  python3 qa/tests/test-all.py [--verbose] [--jobs N] [--no-build] [suite ...]

  suite     restrict to named suites (default: all). Known suites are listed
            below in SUITES.
  --jobs    max parallel component-local suites (default: CPU count).
  --no-build  skip phase 1 and use whatever binaries already exist.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import (
    MYASSEMBLER_DIR,
    MYEMULATOR_DIR,
    MYKERNEL_DIR,
    MYLANGCOMPILER_DIR,
    MYLANGTESTER_DIR,
    MYLINKER_DIR,
    MYOS_DIR,
    REPO_ROOT,
)
from qa.runners.runner_common import CYAN, GREEN, MYEMU, RED, YELLOW, colored, status_line


# ---------------------------------------------------------------------------
# Phase 1: build components via their Makefiles.
# ---------------------------------------------------------------------------

# name -> (directory, make target, produced artifact)
COMPONENTS = {
    "mlc": (MYLANGCOMPILER_DIR, "mlc", MYLANGCOMPILER_DIR / "mlc"),
    "syntax-check": (MYLANGCOMPILER_DIR, "syntax-check", MYLANGCOMPILER_DIR / "mylang-syntax-check"),
    "mytest": (MYLANGTESTER_DIR, "all", MYLANGTESTER_DIR / "build" / "mytest"),
    "myas": (MYASSEMBLER_DIR, "all", MYASSEMBLER_DIR / "build" / "myas"),
    "mllinker": (MYLINKER_DIR, "all", MYLINKER_DIR / "mllinker"),
    "myemu": (MYEMULATOR_DIR, "all", MYEMU),
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

    status_line("WARN", f"{name}: build failed, cleaning and rebuilding", YELLOW)
    subprocess.run(["make", "clean"], cwd=directory,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = _make(directory, target, verbose)
    if proc.returncode == 0 and artifact.exists():
        return True, "rebuilt from clean"
    tail = proc.stdout[-800:] if proc.stdout else "(no output)"
    return False, f"build failed after clean:\n{tail}"


# ---------------------------------------------------------------------------
# Phase 2: test suites. QA invokes component-owned public targets or
# executables; test discovery and assertions remain inside each submodule.
# ---------------------------------------------------------------------------

# mytest builds MyLang tests and runs them in the emulator, so a suite that
# runs it needs the whole toolchain.
MYTEST_DEPS = ("mlc", "mytest", "myas", "mllinker", "myemu")


def mytest_suite(*tests):
    """A suite that runs these MyLang test files with mytest."""
    return [str(COMPONENTS["mytest"][2]), *map(str, tests)], list(MYTEST_DEPS)


# name -> (runner argv, [required components])
SUITES = {
    "compiler": (
        ["make", "-C", str(MYLANGCOMPILER_DIR), "test-component"],
        ["mlc"],
    ),
    "assembler": (
        ["make", "-C", str(MYASSEMBLER_DIR), "test-component"],
        ["myas"],
    ),
    "linker": (
        ["make", "-C", str(MYLINKER_DIR), "test-component"],
        ["mllinker"],
    ),
    "emulator": (
        ["make", "-C", str(MYEMULATOR_DIR), "test-component"],
        ["myemu"],
    ),
    "profiler": (
        [sys.executable, str(REPO_ROOT / "tools" / "MyProfiler" / "tests" / "test_profiler.py")],
        [],
    ),
    "compiler-e2e": (
        ["make", "-C", str(MYLANGCOMPILER_DIR), "test-e2e"],
        ["mlc", "myas", "mllinker", "myemu"],
    ),
    "testkit": (
        ["python3", str(REPO_ROOT / "toolchain" / "MyLangTestKit" / "tests" / "run_integration_tests.py")],
        list(MYTEST_DEPS),
    ),
    # MyLangTester's own fixtures (pragma layouts and the like), run through mytest.
    "tester": (
        ["make", "-C", str(MYLANGTESTER_DIR), "test"],
        list(MYTEST_DEPS),
    ),
    "assembler-e2e": (
        ["make", "-C", str(MYASSEMBLER_DIR), "test-e2e"],
        ["myas", "mllinker", "myemu"],
    ),
    "heap": mytest_suite(
        MYKERNEL_DIR / "tests" / "heap" / "allocator.unsafe.test.mln",
        MYKERNEL_DIR / "tests" / "heap" / "exhaustion.unsafe.test.mln",
    ),
    "app-sdk": mytest_suite(
        REPO_ROOT / "system" / "MyAppFramework" / "tests" / "ui_requests.dom.unsafe.test.mln",
    ),
    "stdlib": mytest_suite(MYKERNEL_DIR / "tests" / "libs" / "std.unsafe.test.mln"),
    "mmu": mytest_suite(MYKERNEL_DIR / "tests" / "mmu" / "mmu.unsafe.test.mln"),
    "fs-directories": mytest_suite(MYOS_DIR / "tests" / "fs" / "directories.unsafe.test.mln"),
    "fs-smoke": mytest_suite(MYOS_DIR / "tests" / "fs" / "fs_smoke.unsafe.test.mln"),
    "fs-errors": mytest_suite(
        MYOS_DIR / "tests" / "fs" / "error_contracts.unsafe.test.mln",
        MYOS_DIR / "tests" / "fs" / "ssd_unavailable.unsafe.test.mln",
        MYOS_DIR / "tests" / "fs" / "mocked_ssd.unsafe.test.mln",
        MYOS_DIR / "tests" / "fs" / "mocked_result.unsafe.test.mln",
    ),
    "disk-fixture": mytest_suite(MYOS_DIR / "tests" / "fs" / "disk_fixture.unsafe.test.mln"),
    "minode-fd": mytest_suite(MYOS_DIR / "tests" / "fs" / "minode_fd.unsafe.test.mln"),
    "scheduler": mytest_suite(
        MYKERNEL_DIR / "tests" / "scheduler" / "scheduler.unsafe.test.mln",
        MYKERNEL_DIR / "tests" / "scheduler" / "mock_context.unsafe.test.mln",
    ),
    "process": mytest_suite(
        MYKERNEL_DIR / "tests" / "process" / "process.unsafe.test.mln",
        MYOS_DIR / "tests" / "proc" / "pid_reuse.unsafe.test.mln",
    ),
    "thread": mytest_suite(MYKERNEL_DIR / "tests" / "thread" / "thread.unsafe.test.mln"),
    "serial-rx": mytest_suite(MYKERNEL_DIR / "tests" / "serial" / "serial_rx.unsafe.test.mln"),
    "dom": mytest_suite(MYKERNEL_DIR / "tests" / "dom" / "dom_lowering.dom.unsafe.test.mln"),
    "dom-hit": mytest_suite(MYOS_DIR / "tests" / "dom" / "dom_hit_dispatch.unsafe.test.mln"),
    "dom-terminal": mytest_suite(MYOS_DIR / "tests" / "dom" / "dom_terminal.unsafe.test.mln"),
    "input-queues": mytest_suite(MYKERNEL_DIR / "tests" / "io" / "input_queues.unsafe.test.mln"),
    "graphics": mytest_suite(MYOS_DIR / "tests" / "ui" / "graphics.unsafe.test.mln"),
    "readme": (
        ["python3", str(REPO_ROOT / "tools" / "readme_media.py"), "--check"],
        [],
    ),
    "unused-exports": (
        ["python3", str(REPO_ROOT / "qa" / "tools" / "unused_exports.py")],
        ["mlc"],
    ),
    "unused-exports-tool": (
        ["python3", str(REPO_ROOT / "qa" / "tests" / "unused_exports_test.py")],
        ["mlc"],
    ),
    "mln-check": (
        ["python3", str(REPO_ROOT / "qa" / "tools" / "mln_check.py")],
        ["mlc"],
    ),
    "mln-check-tool": (
        ["python3", str(REPO_ROOT / "qa" / "tests" / "mln_check_test.py")],
        ["mlc"],
    ),
    "lsp": (
        ["python3", str(REPO_ROOT / "tools" / "MyLangServerProtocol" / "tests" / "run.py")],
        ["mlc", "syntax-check"],
    ),
    "lsp-check": (
        ["python3", str(REPO_ROOT / "qa" / "tools" / "lsp_check.py")],
        ["mlc", "syntax-check"],
    ),
    "lsp-check-tool": (
        ["python3", str(REPO_ROOT / "qa" / "tests" / "lsp_check_test.py")],
        ["mlc", "syntax-check"],
    ),
}

# These suites may incrementally build the same sibling repositories internally.
# The LSP suites share one parse table, which a grammar change makes them rebuild.
SERIAL_SUITES = {"compiler-e2e", "assembler-e2e", "testkit", "lsp", "lsp-check", "lsp-check-tool"}


def run_suite(name):
    """Run one suite in a child process. Returns (name, ok, output)."""
    argv, _ = SUITES[name]
    proc = subprocess.run(
        argv, cwd=REPO_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return name, proc.returncode == 0, proc.stdout


def record_result(results, name, ok, output, verbose):
    results[name] = (ok, output)
    label, code = ("PASS", GREEN) if ok else ("FAIL", RED)
    status_line(label, name, code)
    if verbose and output:
        print(output, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Run all project test suites.")
    ap.add_argument("suites", nargs="*", help="restrict to these suites")
    ap.add_argument("--verbose", action="store_true",
                    help="stream build and suite output")
    ap.add_argument("--jobs", type=int, default=None,
                    help="max parallel component-local suites (default: CPU count)")
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
        status_line("INFO", "skipping build phase (--no-build)", YELLOW)
    else:
        status_line("BUILD", f"building: {', '.join(sorted(needed))}")
        for name in sorted(needed):
            ok, detail = build_component(name, args.verbose)
            if ok:
                status_line("OK", f"{name}: {detail}", GREEN)
            else:
                status_line("FAIL", f"{name}: {detail}", RED)
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

    parallel_runnable = [s for s in runnable if s not in SERIAL_SUITES]
    serial_runnable = [s for s in runnable if s in SERIAL_SUITES]

    if parallel_runnable:
        status_line("TEST", f"running {len(parallel_runnable)} component/system suite(s) in parallel")
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(run_suite, s): s for s in parallel_runnable}
            for fut in as_completed(futures):
                name, ok, output = fut.result()
                record_result(results, name, ok, output, args.verbose)

    if serial_runnable:
        status_line("E2E", f"running {len(serial_runnable)} toolchain suite(s) serially")
        for suite in serial_runnable:
            name, ok, output = run_suite(suite)
            record_result(results, name, ok, output, args.verbose)

    # Summary, in the declared order for stable reading.
    print()
    status_line("SUMMARY", "results:")
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
    status_line("DONE", f"{passed}/{total} suites passed", code)
    if passed != total and not args.verbose:
        status_line("INFO", "re-run with --verbose to see failing suite output", CYAN)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
