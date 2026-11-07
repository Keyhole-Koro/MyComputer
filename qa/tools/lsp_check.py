#!/usr/bin/env python3
"""Report what the language server shows for MyLang sources, without an editor.

Sources go through the server's own diagnostics, and the compiler's parser
decides who is right. The server parses with a grammar of its own, so the two
can drift apart:

- `lsp false alarm`: the server marks an error in a source mlc parses. The
  grammar is missing something.
- `lsp missed`: mlc's parser rejects a source and the server shows nothing.
- `error`: both reject it, so the source itself is wrong.

The server shows no errors when its checker cannot run, which looks like a clean
file. So a source that must pass and one that must fail go through it first, and
a checker that gets either wrong ends the run with status 2.

Paths on the command line narrow the run to those files and directories. Inputs
of other tools' tests (FIXTURE_TREES) often fail on purpose, so there only a
false alarm counts, unless a path names them.
"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mln_check import select_sources
from unused_exports import FIXTURE_TREES, REPO_ROOT, find_sources, under

sys.path.insert(0, str(REPO_ROOT / "tools" / "MyLangServerProtocol" / "src"))

from mylang_lsp.features.diagnostics import DiagnosticsService  # noqa: E402
from mylang_lsp.frontend.native import NativeFrontendClient  # noqa: E402

MUST_PASS = "i32 main() { return 0; }\n"
MUST_FAIL = "i32 main() { return 0 }\n"
PROBE_URI = "file:///lsp-check-probe.mln"


def probe(client, service):
    """Why the checker cannot be trusted, or None."""
    if client.query(MUST_PASS, PROBE_URI) is None:
        return f"the language server's checker did not answer ({client.binary})"
    if service.analyze(MUST_PASS, PROBE_URI):
        return "the language server marks a valid source"
    if not service.analyze(MUST_FAIL, PROBE_URI):
        return "the language server shows nothing for a broken source"
    return None


def server_diagnostics(client, service, root, sources):
    """Maps each source to the server's diagnostics, or None if it did not answer."""
    found = {}
    for source in sources:
        path = root / source
        text = path.read_text(encoding="utf-8", errors="replace")
        uri = path.as_uri()
        found[source] = None if client.query(text, uri) is None else service.analyze(text, uri)
    return found


def parser_verdict(mlc, root, source):
    """Returns whether mlc's parser accepts the source, and its first error line."""
    process = subprocess.run([str(mlc), "--parse-only", source], cwd=root, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = process.stdout.splitlines()
    return process.returncode == 0, lines[0] if lines else ""


def place(source, diagnostic):
    start = diagnostic["range"]["start"]
    return f"{source}:{start['line'] + 1}:{start['character'] + 1}"


def findings(source, diagnostics, parsed, parser_error, on_purpose):
    """What to report for one source."""
    if diagnostics and parsed:
        return [f"{place(source, diagnostic)}: lsp false alarm: {diagnostic['message']}"
                for diagnostic in diagnostics]
    if on_purpose:
        return []
    if diagnostics:
        return [f"{place(source, diagnostic)}: error: {diagnostic['message']}"
                for diagnostic in diagnostics]
    if not parsed:
        return [f"{source}: lsp missed: {parser_error}"]
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="files or directories, instead of every source")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--mlc", type=Path,
                        default=REPO_ROOT / "toolchain" / "MyLangCompiler" / "mlc")
    parser.add_argument("--checker", type=Path, help="the checker binary, instead of the built one")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args()

    root = args.root.resolve()
    mlc = args.mlc.resolve()
    client = NativeFrontendClient(REPO_ROOT)
    if args.checker:
        client.binary = args.checker
        client.build_attempted = True
    service = DiagnosticsService(client.query)
    try:
        problem = probe(client, service)
        if problem:
            print(problem, file=sys.stderr)
            return 2
        if args.paths:
            sources = select_sources(root, args.paths)
        else:
            sources = [source for source in find_sources(root) if source.endswith(".mln")]
        shown = server_diagnostics(client, service, root, sources)
    finally:
        client.stop()

    silent = [source for source, diagnostics in shown.items() if diagnostics is None]
    if silent:
        print(f"the language server's checker stopped answering at {silent[0]}", file=sys.stderr)
        return 2

    with ThreadPoolExecutor(args.jobs) as pool:
        verdicts = list(pool.map(lambda source: parser_verdict(mlc, root, source), sources))

    reported = 0
    for source, (parsed, parser_error) in zip(sources, verdicts):
        on_purpose = not args.paths and under(source, FIXTURE_TREES)
        lines = findings(source, shown[source], parsed, parser_error, on_purpose)
        reported += len(lines)
        for line in lines:
            print(line)
    print(f"{len(sources)} sources checked, {reported} findings")
    return 1 if reported else 0


if __name__ == "__main__":
    sys.exit(main())
