#!/usr/bin/env python3
"""Build every user-space program into an MBIN executable
(build/user/<name>.mbin), linked at the user code base with the executable
header the kernel loader expects (MYOS-015):

- system/MyOS/user/apps/*.mln -- console programs, each `namespace app;`
  exporting `i32 main()`; user/lib/start.masm calls it and exits with its
  return value.
- system/MyOS/src/apps/*.dom.mln -- desktop apps (MYOS-022), each with an
  `i32 main()` that hands its type to the SDK's app.run. The shell lists them
  from their headers.

The programs are built together, in one build directory, so a source they
share (the SDK, the UI protocol) is compiled once rather than once per
program; see qa/runners/build_toolchain.py.

The images are then placed on the disk image by tools/mkfs.py (see
qa/runners/run_system.py)."""

import argparse
import io
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qa.runners.build_toolchain import Builder, BuildError, Target, UnitFailed
from tools.project_paths import MYOS_DIR, REPO_ROOT

USER_DIR = MYOS_DIR / "user"
# A desktop app is src/apps/<name>.dom.mln; the disk image keeps it in /apps,
# apart from the console programs in /bin.
GUI_APP_DIR = MYOS_DIR / "src" / "apps"
GUI_APP_SUFFIX = ".dom.mln"
# A process's code and data start at 1 GB, above the kernel's identity mapping
# of RAM (docs/design/user-space-processes-and-syscalls.md); the loader maps a
# v2 image at the base it was linked at.
USER_CODE_BASE = "0x40000000"


def gui_app_sources() -> list:
    return sorted(GUI_APP_DIR.glob("*" + GUI_APP_SUFFIX))


def gui_app_name(source: Path) -> str:
    return source.name[: -len(GUI_APP_SUFFIX)]


def app_target(source: Path, out_dir: Path, gui: bool) -> Target:
    """How one program is linked, as out_dir/<name>.mbin. A console program
    starts at the start stub, which calls its main() and exits with the
    result; a desktop app's main() runs the app and never returns, so it has
    no use for the stub."""
    if gui:
        name, stub = gui_app_name(source), []
    else:
        name, stub = source.stem, [USER_DIR / "lib" / "start.masm"]
    return Target(roots=[*stub, source], out=out_dir / (name + ".mbin"),
                  base=USER_CODE_BASE, header=True)


def build_all(out_dir: Path, build_dir: Path, quiet: bool = False, jobs=None) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    programs = [(source, False) for source in sorted((USER_DIR / "apps").glob("*.mln"))]
    programs += [(source, True) for source in gui_app_sources()]
    targets = [app_target(source, out_dir, gui) for source, gui in programs]

    log = io.StringIO() if quiet else None
    try:
        Builder(build_dir, jobs=jobs, out=log).build(targets)
    except (subprocess.CalledProcessError, BuildError) as exc:
        if log:
            print(log.getvalue(), end="")
        if isinstance(exc, UnitFailed):
            what = exc.source.relative_to(REPO_ROOT) if exc.source.is_relative_to(REPO_ROOT) else exc.source
        elif isinstance(exc, BuildError):
            what = exc
        else:
            what = " ".join(str(c) for c in exc.cmd)
        raise SystemExit(f"user program build failed: {what}")

    if not quiet:
        for (source, gui), target in zip(programs, targets):
            label = "app" if gui else "user"
            print(f"[{label}] {source.name} -> {target.out} ({target.out.stat().st_size} bytes)")
    # The disk image takes every image here, so one whose source is gone (an
    # app that was removed) must not stay behind.
    names = {target.out.name for target in targets}
    for stale in out_dir.glob("*.mbin"):
        if stale.name not in names:
            for leftover in out_dir.glob(stale.name + "*"):
                leftover.unlink()
    return [target.out for target in targets]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "build" / "user"))
    parser.add_argument("--build-dir", default=str(REPO_ROOT / "build" / "user" / "obj"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("-j", "--jobs", type=int, default=None,
                        help="Sources built at once (default: MYBUILD_JOBS, else the CPU count)")
    args = parser.parse_args()
    build_all(Path(args.out_dir), Path(args.build_dir), args.quiet, args.jobs)


if __name__ == "__main__":
    main()
