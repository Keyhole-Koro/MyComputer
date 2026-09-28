#!/usr/bin/env python3
"""
Build pipeline tool: .mln -> .masm (mlc),
.masm -> .mobj (myas) -> linked .mbin (mllinker)
Supports recursive source discovery with exclusions.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYASSEMBLER_DIR, MYLANGCOMPILER_DIR, MYLINKER_DIR, REPO_ROOT


class BuildError(RuntimeError):
    pass


def run(cmd, cwd=None):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
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


def source_kind_for_path(path: Path):
    if path.suffix == ".mln":
        return "ml"
    if path.suffix == ".masm":
        return "masm"
    return None


def source_relpath(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return Path(path.name)


def add_source(path: Path, sources, seen_paths):
    path = path.resolve()
    if path in seen_paths:
        return

    stype = source_kind_for_path(path)
    if not stype:
        return

    seen_paths.add(path)
    sources.append((path, source_relpath(path), stype))


def collect_root_sources(paths, excludes, include_masm):
    sources = []
    seen_paths = set()

    for p in paths:
        p = p.resolve()
        if p.is_dir():
            dir_sources = []
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
                        add_source(fpath, dir_sources, seen_paths)
                    elif fpath.suffix == ".masm" and include_masm:
                        add_source(fpath, dir_sources, seen_paths)
            dir_sources.sort(key=lambda item: (0 if item[2] == "ml" else 1, str(item[1]).replace("\\", "/")))
            sources.extend(dir_sources)
        else:
            if p.suffix in {".mln", ".masm"}:
                add_source(p, sources, seen_paths)
            else:
                print(f"[WARN] Skip unsupported file: {p}")
    return sources, seen_paths


def read_dependency_file(path: Path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BuildError(f"Failed to read dependency file {path}: {exc}") from exc
    if not lines or lines[0] != "MYDEPS 1":
        raise BuildError(f"Invalid dependency file header: {path}")

    dependencies = []
    for line_number, line in enumerate(lines[1:], start=2):
        if not line:
            continue
        try:
            kind, raw_path = line.split("\t", 1)
        except ValueError as exc:
            raise BuildError(
                f"Invalid dependency entry at {path}:{line_number}"
            ) from exc
        expected_suffix = {"mln": ".mln", "masm": ".masm"}.get(kind)
        if expected_suffix is None:
            raise BuildError(
                f"Unknown dependency kind '{kind}' at {path}:{line_number}"
            )
        dependency = Path(raw_path)
        if not dependency.is_absolute() or dependency.suffix != expected_suffix:
            raise BuildError(
                f"Invalid {kind} dependency path at {path}:{line_number}: {raw_path}"
            )
        dependency = dependency.resolve()
        if not dependency.is_file():
            raise BuildError(f"Dependency does not exist: {dependency}")
        dependencies.append(dependency)
    return dependencies


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
    parser.add_argument("--base", type=str, help="Base address for linking in hex (default: 0)")
    parser.add_argument("--header", action="store_true", help="Emit MBIN v2 executable header")
    parser.add_argument("--redirect", action="append", default=[],
                        help="Redirect direct calls: <original>=<entry> (repeatable)")
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
    sources, seen_sources = collect_root_sources(src_paths, args.exclude, args.masm)

    if not sources:
        print("[ERROR] No sources found.")
        return 1

    out_map = {}
    mobj_paths = []
    source_index = 0

    # Tools own import parsing and path resolution. The builder consumes their
    # dependency manifests and expands this work queue without reading source.
    while source_index < len(sources):
        src, rel, stype = sources[source_index]
        source_index += 1
        if stype == "ml":
            out_masm = build_dir / rel.with_suffix(".masm")
            out_masm.parent.mkdir(parents=True, exist_ok=True)
            ml_depfile = Path(str(out_masm) + ".ml-deps")
            cmd = [mlc]
            if args.entry:
                cmd += ["-entry", args.entry]
            # Pass redirects through to MLC as well. This is essential for a
            # call whose callee is defined in the same source file: otherwise
            # MyAssembler resolves it before the linker can redirect it.
            for redirect in args.redirect:
                cmd += ["--redirect-call", redirect]
            cmd += ["--depfile", ml_depfile, src, out_masm]
            dependency_files = [ml_depfile]
        else:
            out_masm = build_dir / rel
            out_masm.parent.mkdir(parents=True, exist_ok=True)
            cmd = None
            dependency_files = []

        if out_masm in out_map and out_map[out_masm] != src:
            raise BuildError(
                f"Output collision: {out_masm} from {src} and {out_map[out_masm]}"
            )
        out_map[out_masm] = src

        if cmd:
            run(cmd, cwd=repo)
            asm_input = out_masm
        else:
            if src.resolve() != out_masm.resolve():
                shutil.copy2(src, out_masm)
            # Resolve assembly `from` paths against the source location, not
            # against its copied build artifact.
            asm_input = src

        out_mbin = out_masm.with_suffix(".mbin")
        out_mobj = out_masm.with_suffix(".mobj")
        asm_depfile = Path(str(out_masm) + ".asm-deps")
        run([myas, asm_input, out_mbin, "--obj", out_mobj,
             "--depfile", asm_depfile], cwd=repo)
        mobj_paths.append(out_mobj)
        dependency_files.append(asm_depfile)

        for dependency_file in dependency_files:
            for dependency in read_dependency_file(dependency_file):
                if dependency in seen_sources:
                    continue
                add_source(dependency, sources, seen_sources)

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
    
    # Make sure heap_sym is last so the heap is at the end of the binary
    final_mobj = []
    heap_sym_mobj = None
    for m in unique_mobj:
        if m.name == "heap_sym.mobj":
            heap_sym_mobj = m
        else:
            final_mobj.append(m)
    if heap_sym_mobj:
        final_mobj.append(heap_sym_mobj)
    
    # Emit a symbol map alongside the linked image so the profiler can attribute
    # program counters to function names. Named <output>.map next to the binary.
    map_path = out_path.with_suffix(out_path.suffix + ".map")
    
    linker_cmd = [mllinker, "--map", map_path]
    if args.base:
        linker_cmd.extend(["--base", args.base])
    if args.header:
        linker_cmd.append("--header")
    for redirect in args.redirect:
        linker_cmd.extend(["--redirect", redirect])
    linker_cmd.append(out_path)
    linker_cmd.extend(final_mobj)

    run(linker_cmd, cwd=repo)
    print(f"Linked output: {out_path}")
    print(f"Symbol map: {map_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        command = " ".join(str(c) for c in exc.cmd)
        print(
            f"[ERROR] command failed (exit {exc.returncode}): {command}",
            file=sys.stderr,
        )
        raise SystemExit(exc.returncode)
    except BuildError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
