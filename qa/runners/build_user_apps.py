#!/usr/bin/env python3
"""Build every user-space program under system/MyOS/user/apps into an MBIN
executable (build/user/<name>.mbin), linked at the user code base with the
executable header the kernel loader expects (MYOS-015).

Each app is `package app;` exporting `i32 main()`; user/lib/start.masm calls
it and exits with its return value. The images are then placed on the disk
image by tools/mkfs.py (see qa/runners/run_system.py)."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYOS_DIR, QA_DIR, REPO_ROOT

USER_DIR = MYOS_DIR / "user"
# MyLang materializes symbol addresses with a 21-bit immediate, so a
# compiled program must be linked below 2 MB. 0x20000..0xFFFFF is RAM the
# kernel never touches (the firmware stub sits at 0, the kernel image at
# 0x100000); the loader maps a v2 image at the base it was linked at.
USER_CODE_BASE = "0x00020000"


def build_app(source: Path, out_dir: Path, build_dir: Path, quiet: bool) -> Path:
    out = out_dir / (source.stem + ".mbin")
    cmd = [
        sys.executable, str(QA_DIR / "runners" / "build_toolchain.py"),
        str(USER_DIR / "lib" / "start.masm"), str(source),
        "-o", str(out), "--build-dir", str(build_dir / source.stem),
        "--base", USER_CODE_BASE, "--header",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        raise SystemExit(f"user app build failed: {source.name}")
    if not quiet:
        print(f"[user] {source.name} -> {out} ({out.stat().st_size} bytes)")
    return out


def build_all(out_dir: Path, build_dir: Path, quiet: bool = False) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    built = []
    for source in sorted((USER_DIR / "apps").glob("*.mln")):
        built.append(build_app(source, out_dir, build_dir, quiet))
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
