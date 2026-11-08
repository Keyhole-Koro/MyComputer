#!/usr/bin/env python3
"""Build every user-space program into an MBIN executable
(build/user/<name>.mbin), linked at the user code base with the executable
header the kernel loader expects (MYOS-015):

- system/MyOS/user/apps/*.mln -- console programs, each `package app;`
  exporting `i32 main()`; user/lib/start.masm calls it and exits with its
  return value.
- system/MyOS/src/apps/*.dom.mln -- desktop apps (MYOS-022), each with an
  `i32 main()` that hands its type to the SDK's app.run. The shell lists them
  from their headers.

The images are then placed on the disk image by tools/mkfs.py (see
qa/runners/run_system.py)."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYOS_DIR, QA_DIR, REPO_ROOT

USER_DIR = MYOS_DIR / "user"
# A desktop app is src/apps/<name>.dom.mln; the disk image keeps it in /apps,
# apart from the console programs in /bin.
GUI_APP_DIR = MYOS_DIR / "src" / "apps"
GUI_APP_SUFFIX = ".dom.mln"
# MyLang materializes symbol addresses with a 21-bit immediate, so a
# compiled program must be linked below 2 MB. 0x20000..0xFFFFF is RAM the
# kernel never touches (the firmware stub sits at 0, the kernel image at
# 0x100000); the loader maps a v2 image at the base it was linked at.
USER_CODE_BASE = "0x00020000"


def gui_app_sources() -> list:
    return sorted(GUI_APP_DIR.glob("*" + GUI_APP_SUFFIX))


def gui_app_name(source: Path) -> str:
    return source.name[: -len(GUI_APP_SUFFIX)]


def build_app(source: Path, out_dir: Path, build_dir: Path, quiet: bool, gui: bool = False) -> Path:
    """Link one program as out_dir/<name>.mbin. A console program starts at
    the start stub, which calls its main() and exits with the result; a
    desktop app's main() runs the app and never returns, so it has no use
    for the stub."""
    if gui:
        name, stub, label, kind = gui_app_name(source), [], "app", "app"
    else:
        name, stub, label, kind = source.stem, [str(USER_DIR / "lib" / "start.masm")], "user", "user app"
    out = out_dir / (name + ".mbin")
    cmd = [
        sys.executable, str(QA_DIR / "runners" / "build_toolchain.py"),
        *stub, str(source),
        "-o", str(out), "--build-dir", str(build_dir / name),
        "--base", USER_CODE_BASE, "--header",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        raise SystemExit(f"{kind} build failed: {source.name}")
    if not quiet:
        print(f"[{label}] {source.name} -> {out} ({out.stat().st_size} bytes)")
    return out


def build_all(out_dir: Path, build_dir: Path, quiet: bool = False) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    built = []
    for source in sorted((USER_DIR / "apps").glob("*.mln")):
        built.append(build_app(source, out_dir, build_dir, quiet))
    for source in gui_app_sources():
        built.append(build_app(source, out_dir, build_dir, quiet, gui=True))
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "build" / "user"))
    parser.add_argument("--build-dir", default=str(REPO_ROOT / "build" / "user" / "obj"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    build_all(Path(args.out_dir), Path(args.build_dir), args.quiet)


if __name__ == "__main__":
    main()
