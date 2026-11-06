#!/usr/bin/env python3
"""Report exported functions, methods and globals that nothing references.

Every `.mln` source is compiled with `mlc --emit-symbols`, which lists what the
source exports and which symbols its finished assembly names, so a call the
compiler generated counts like a written one: a `.dom.mln` element, a
trampoline, a drop, `==` on a trait, a `.model.mln` expansion, a mock facade.
Sources are compiled with --error-trace to include the calls that adds.
Every `.masm` source is read for the names it mentions. An export is a finding
when no source, tests included, names it other than from its own body.

What is decided here rather than by the compiler:

- A trait impl method is never a finding. The trait requires it, so it cannot
  be deleted alone; what it calls still counts as used.
- A generic function or method is one export, used when any source references
  an instance of it. A template nothing instantiates is a finding: it is
  exported code that no program contains. A library's intended public surface
  goes in the allowlist with the rest.
- A `.model.mln` source declares a table and the compiler writes its functions,
  so nothing there can be deleted by hand. Its expansion is not reported.
- Exports of `.masm` sources are not reported. They are linker contracts and
  hardware entry points rather than MyLang API.
- Two sources that export one symbol are one export: a use of the name counts
  for both, as it would at link time for whichever is in the image.
- Inputs of other tools' tests (FIXTURE_TREES) are not reported, and many do
  not compile on purpose; those that compile count as users. Any other source
  must compile: one that does not could hide uses, so the run stops.

Findings are compared with an allowlist of `<path> <symbol>` lines. An entry
that is no longer a finding is only mentioned, so deleting an export does not
need the list changed in the same step; --write-allow rewrites the list.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOW = REPO_ROOT / "qa" / "unused-exports-allow.txt"

ENTRY_POINTS = {"main", "kernel_main", "fw_main", "__START__"}

# Called from the assembly mytest writes for each mocked target
# (mockEntryAssembly in toolchain/MyLangTester/src/TestRunner.java), which
# exists only while a test is being built.
TEST_RUNNER_USES = {
    "mock_current_callback", "mock_current_result", "mock_dispatch", "mock_enter",
    "mock_leave", "mock_record", "mock_should_call_original", "mock_unexpected",
}

FIXTURE_TREES = (
    "toolchain/MyLangCompiler/docs",
    "toolchain/MyLangCompiler/tests",
    "toolchain/MyLangTestKit/tests",
    "tools/MyLangServerProtocol/tests",
)

# Sources that link against nothing here, or that are this tool's own fixture.
SKIPPED_TREES = (
    "qa/tests/fixtures",
    "toolchain/MyAssembler/tests",
    "toolchain/MyLinker/tests",
)
SKIPPED_DIRECTORIES = {"build", "node_modules", "target", "__pycache__"}

SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

Definition = namedtuple("Definition", "kind symbol path line")


def under(path, trees):
    return any(path == tree or path.startswith(tree + "/") for tree in trees)


def find_sources(root):
    """Paths relative to root, in a stable order, of every .mln and .masm."""
    sources = []
    for directory, subdirectories, files in os.walk(root):
        relative = Path(directory).relative_to(root).as_posix()
        subdirectories[:] = sorted(
            name for name in subdirectories
            if not name.startswith(".") and name not in SKIPPED_DIRECTORIES
            and not under(f"{relative}/{name}".removeprefix("./"), SKIPPED_TREES))
        for name in sorted(files):
            if name.endswith((".mln", ".masm")) and "_gen_test" not in name:
                sources.append(f"{relative}/{name}".removeprefix("./"))
    return sources


def compile_source(mlc, root, source):
    """Returns the symbol file's lines, or None and why it failed."""
    with tempfile.TemporaryDirectory(prefix="unused-exports-") as work:
        symbols = Path(work) / "symbols"
        process = subprocess.run(
            [str(mlc), "--error-trace", "--emit-symbols", str(symbols), str(root / source),
             str(Path(work) / "out.masm")],
            cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if process.returncode != 0:
            return None, process.stdout
        lines = symbols.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "MYSYMBOLS 1":
        return None, "unexpected symbol file"
    return lines[1:], None


class Program:
    """What every source exports and references."""

    def __init__(self, root):
        self.root = root.resolve()
        self.definitions = []
        self.used_symbols = set(TEST_RUNNER_USES)
        self.used_templates = set()

    def relative(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def add_unit(self, lines):
        instances = {}
        uses = []
        for line in lines:
            fields = line.split("\t")
            if fields[0] == "use":
                uses.append((fields[1], fields[2]))
            elif fields[0] == "instance":
                instances[fields[1]] = (fields[2], int(fields[3]))
            else:
                kind, symbol, path, source_line = fields
                self.definitions.append(
                    Definition(kind, symbol, self.relative(path), int(source_line)))
        for user, symbol in uses:
            template = instances.get(symbol)
            if template is None:
                if user != symbol:
                    self.used_symbols.add(symbol)
            elif instances.get(user) != template:
                self.used_templates.add(template)

    def add_assembly(self, text):
        for line in text.splitlines():
            self.used_symbols.update(SYMBOL.findall(line.split(";", 1)[0]))

    def is_used(self, definition):
        if definition.kind == "template":
            location = (str(self.root / definition.path), definition.line)
            return location in self.used_templates
        return definition.symbol in self.used_symbols

    def findings(self):
        found = {}
        for definition in self.definitions:
            if (definition.kind == "impl" or definition.symbol in ENTRY_POINTS or
                    definition.path.endswith(".model.mln") or
                    under(definition.path, FIXTURE_TREES) or self.is_used(definition)):
                continue
            found[(definition.path, definition.symbol)] = definition
        return [found[key] for key in sorted(found)]


def collect(root, mlc, jobs):
    """Compiles every source. Returns (Program, errors)."""
    program = Program(root)
    sources = find_sources(root)
    errors = []
    modules = [source for source in sources if source.endswith(".mln")]
    with ThreadPoolExecutor(jobs) as pool:
        results = pool.map(lambda source: compile_source(mlc, root, source), modules)
        for source, (lines, failure) in zip(modules, results):
            if lines is not None:
                program.add_unit(lines)
            elif not under(source, FIXTURE_TREES):
                errors.append(f"{source} did not compile:\n{failure}")
    for source in sources:
        if source.endswith(".masm"):
            program.add_assembly((root / source).read_text(encoding="utf-8", errors="replace"))
    return program, errors


def read_allowlist(path):
    if not path.exists():
        return set()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            source, symbol = line.split()
            entries.add((source, symbol))
    return entries


def write_allowlist(path, findings):
    lines = [
        "# Exports nothing references, kept on purpose or until they are deleted.",
        "# See qa/tools/unused_exports.py. Lines are `<path> <symbol>`.",
    ]
    lines += [f"{finding.path} {finding.symbol}" for finding in findings]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Report exports nothing references.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to scan")
    parser.add_argument("--mlc", type=Path,
                        default=REPO_ROOT / "toolchain" / "MyLangCompiler" / "mlc")
    parser.add_argument("--allow", type=Path, default=DEFAULT_ALLOW, help="allowlist file")
    parser.add_argument("--write-allow", action="store_true",
                        help="make the allowlist the current findings")
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    args = parser.parse_args()

    root = args.root.resolve()
    program, errors = collect(root, args.mlc.resolve(), args.jobs)
    for error in errors:
        print(f"[ERROR] {error}", file=sys.stderr)
    if errors:
        return 2

    findings = program.findings()
    if args.write_allow:
        write_allowlist(args.allow, findings)
        print(f"{args.allow}: {len(findings)} entries")
        return 0

    allowed = read_allowlist(args.allow)
    found = {(finding.path, finding.symbol) for finding in findings}
    unlisted = [finding for finding in findings
                if (finding.path, finding.symbol) not in allowed]
    for finding in unlisted:
        print(f"{finding.path}:{finding.line}: unused {finding.kind} {finding.symbol}")
    stale = sorted(allowed - found)
    for source, symbol in stale:
        print(f"[NOTE] no longer unused, or gone: {source} {symbol}")
    print(f"{len(found)} unused exports, {len(unlisted)} not in {args.allow.name}, "
          f"{len(stale)} stale entries")
    return 1 if unlisted else 0


if __name__ == "__main__":
    raise SystemExit(main())
