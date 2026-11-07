#!/usr/bin/env python3
"""Report the errors in MyLang sources without building anything.

Every `.mln` in the repository goes through `mlc --check`, which parses it and
runs the semantic checks. Paths on the command line narrow that to those files
and directories. Inputs of other tools' tests (FIXTURE_TREES) are left out,
since many fail on purpose, unless a path names them.

The parser stops at its first error in a file. Linking is not checked: that
takes `make build`.
"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from unused_exports import FIXTURE_TREES, REPO_ROOT, find_sources, under


def select_sources(root, paths):
    """Paths relative to root of the sources to check, in a stable order."""
    if not paths:
        return [source for source in find_sources(root)
                if source.endswith(".mln") and not under(source, FIXTURE_TREES)]
    selected = []
    for path in paths:
        target = Path(path).resolve()
        if not target.exists():
            sys.exit(f"{path} does not exist")
        if target.is_dir():
            selected += [(target / source).relative_to(root).as_posix()
                         for source in find_sources(target) if source.endswith(".mln")]
        else:
            selected.append(target.relative_to(root).as_posix())
    return selected


def check(mlc, root, source):
    """Returns the exit code and everything mlc printed."""
    process = subprocess.run([str(mlc), "--check", source], cwd=root, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return process.returncode, process.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="files or directories, instead of every source")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--mlc", type=Path,
                        default=REPO_ROOT / "toolchain" / "MyLangCompiler" / "mlc")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args()

    root = args.root.resolve()
    mlc = args.mlc.resolve()
    if not mlc.exists():
        print(f"{mlc} is missing", file=sys.stderr)
        return 2
    sources = select_sources(root, args.paths)
    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda source: check(mlc, root, source), sources))

    # An error in a shared file reaches every source that imports it.
    printed = set()
    failed = 0
    for code, output in results:
        failed += code != 0
        if output and output not in printed:
            printed.add(output)
            print(output, end="")
    print(f"{len(sources)} sources checked, {failed} with errors")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
