#!/usr/bin/env python3
"""
Build pipeline tool: .mln -> .masm (mlc) -> .mobj (myas) -> linked .mbin (mllinker)
Supports recursive source discovery with exclusions.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_paths import MYASSEMBLER_DIR, MYLANGCOMPILER_DIR, MYLINKER_DIR, REPO_ROOT


def run(cmd, cwd=None):
    print("+ " + " ".join(str(c) for c in cmd))
    subprocess.check_call([str(c) for c in cmd], cwd=cwd)


def norm_rel(p: str) -> str:
    return p.replace("\\", "/").strip("/")


def should_exclude(rel: str, excludes) -> bool:
    if not rel:
        return False
    rel = norm_rel(rel)
    for ex in excludes:
        if not ex:
            continue
        exn = norm_rel(ex)
        if not exn:
            continue
        if "/" in exn:
            if rel == exn or rel.startswith(exn + "/"):
                return True
        else:
            parts = rel.split("/")
            if exn in parts:
                return True
    return False


def collect_sources(paths, excludes, include_masm):
    sources = []

    for p in paths:
        p = p.resolve()
        if p.is_dir():
            for root, dirs, files in os.walk(p, topdown=True):
                root_path = Path(root)
                rel_root = root_path.relative_to(p)
                rel_root_str = "" if rel_root == Path(".") else norm_rel(str(rel_root))

                # prune excluded dirs
                keep_dirs = []
                for d in dirs:
                    rel_dir = d if not rel_root_str else f"{rel_root_str}/{d}"
                    if not should_exclude(rel_dir, excludes):
                        keep_dirs.append(d)
                dirs[:] = keep_dirs

                for name in files:
                    rel_file = name if not rel_root_str else f"{rel_root_str}/{name}"
                    if should_exclude(rel_file, excludes):
                        continue
                    fpath = root_path / name
                    if fpath.suffix == ".mln":
                        sources.append((fpath, Path(rel_file), "ml"))
                    elif fpath.suffix == ".masm" and include_masm:
                        sources.append((fpath, Path(rel_file), "masm"))
        else:
            rel_name = p.name
            if p.suffix == ".mln":
                sources.append((p, Path(rel_name), "ml"))
            elif p.suffix == ".masm":
                sources.append((p, Path(rel_name), "masm"))
            else:
                print(f"[WARN] Skip unsupported file: {p}")

    return sources


def main():
    parser = argparse.ArgumentParser(
        description="Build .mln + .masm sources into a linked .mbin via mlc/myas/mllinker.")
    parser.add_argument("sources", nargs="+", help="Source files or directories")
    parser.add_argument("-o", "--out", required=True, help="Output linked .mbin path")
    parser.add_argument("--build-dir", help="Directory for intermediate outputs")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude relative path or dir name")
    parser.add_argument("--entry", help="Entry function name mapped to __START__ (mlc)")
    parser.add_argument("--masm", action="store_true", help="Include .masm when scanning directories")
    parser.add_argument("--clean", action="store_true", help="Clean build directory before build")
    args = parser.parse_args()

    repo = REPO_ROOT
    mlc = MYLANGCOMPILER_DIR / "mlc"
    myas = MYASSEMBLER_DIR / "build" / "myas"
    mllinker = MYLINKER_DIR / "mllinker"

    out_path = Path(args.out).resolve()
    build_dir = Path(args.build_dir).resolve() if args.build_dir else out_path.parent.resolve()

    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    src_paths = [Path(p).resolve() for p in args.sources]
    sources = collect_sources(src_paths, args.exclude, args.masm)

    if not sources:
        print("[ERROR] No sources found.")
        return 1

    # Prevent output collisions
    out_map = {}
    for src, rel, stype in sources:
        if stype == "ml":
            out_masm = build_dir / rel.with_suffix(".masm")
        else:
            out_masm = build_dir / rel
        
        if out_masm in out_map and out_map[out_masm] != src:
            print(f"[ERROR] Output collision: {out_masm} from {src} and {out_map[out_masm]}")
            return 1
        out_map[out_masm] = src

    masm_outputs = []

    # Compile/Copy to .masm
    for src, rel, stype in sources:
        if stype == "ml":
            out_masm = build_dir / rel.with_suffix(".masm")
            out_masm.parent.mkdir(parents=True, exist_ok=True)
            cmd = [mlc]
            if args.entry:
                cmd += ["-entry", args.entry]
            cmd += [src, out_masm]
            run(cmd, cwd=repo)
            masm_outputs.append(out_masm)
        elif stype == "masm":
            out_masm = build_dir / rel
            out_masm.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != out_masm.resolve():
                shutil.copy2(src, out_masm)
            masm_outputs.append(out_masm)

    # Assemble .masm -> .mobj
    mobj_paths = []
    for masm in masm_outputs:
        out_mbin = masm.with_suffix(".mbin")
        out_mobj = masm.with_suffix(".mobj")
        run([myas, masm, out_mbin, "--obj", out_mobj], cwd=repo)
        mobj_paths.append(out_mobj)

    if not mobj_paths:
        print("[ERROR] No .mobj outputs generated.")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Remove duplicates but preserve order
    unique_mobj = []
    seen = set()
    for p in mobj_paths:
        if p not in seen:
            unique_mobj.append(p)
            seen.add(p)
    
    run([mllinker, out_path] + unique_mobj, cwd=repo)
    print(f"Linked output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
