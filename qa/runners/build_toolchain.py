#!/usr/bin/env python3
"""
Build pipeline tool: .mln -> .masm (mlc),
.masm -> .mobj (myas) -> linked .mbin (mllinker)
Supports recursive source discovery with exclusions.

Each source is one unit of work: mlc for a .mln, then myas. The tools'
dependency manifests name the sources a unit imports, and those become units
in turn. Units run in parallel (--jobs). A unit whose inputs have not changed
since it was built is not run again: a stamp beside its outputs records the
tools, the options and a hash of every source the compilation read -- its
imports, transitively, and the project's mylang.toml. The link is skipped the
same way when none of its objects changed. The objects are linked in the
order a one-at-a-time build would have found them, so the image does not
depend on which unit finished first.

Each job compiles its units through one `mlc --serve`, which keeps the modules
a unit imports loaded for the next unit instead of parsing them again
(MyLangCompiler's module_cache.c). A unit the server fails, or cannot give a
kept module to, is compiled again by an mlc of its own, whose result stands.
--no-mlc-server (or MYBUILD_MLC_SERVER=0) runs an mlc per unit throughout.
"""

import argparse
import concurrent.futures
import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYASSEMBLER_DIR, MYLANGCOMPILER_DIR, MYLINKER_DIR, REPO_ROOT

MLC = MYLANGCOMPILER_DIR / "mlc"
MYAS = MYASSEMBLER_DIR / "build" / "myas"
MLLINKER = MYLINKER_DIR / "mllinker"

# Bump when what a stamp records, or how a unit is built, changes: every
# stamp written before then stops matching.
STAMP_VERSION = 1


class BuildError(RuntimeError):
    pass


class UnitFailed(subprocess.CalledProcessError):
    """A tool failed on a source; output holds the unit's commands and output."""

    def __init__(self, source: Path, returncode: int, cmd, output: str):
        super().__init__(returncode, cmd, output=output)
        self.source = source


def command_line(cmd) -> str:
    return "+ " + " ".join(str(c) for c in cmd)


class MlcServer:
    """One `mlc --serve`: compiles a unit per line of arguments and ends each
    with a line of "\\x1e" and its status -- 0 compiled, 1 failed, 2 compile it
    again in a fresh process. Most compile errors end the process instead."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [str(MLC), "--serve"], cwd=REPO_ROOT,
            # A serving mlc writes its diagnostics to stdout; an mlc too old to
            # serve would only print its usage here.
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, errors="replace",
        )
        # An mlc that can serve says so first; an older one exits.
        self.serving = self.proc.stdout.readline() == "\x1eserving\n"

    def compile(self, args) -> tuple:
        """(status, output), status None when the server has gone."""
        try:
            self.proc.stdin.write("\t".join(str(a) for a in args) + "\n")
            self.proc.stdin.flush()
        except OSError:
            return None, ""
        lines = []
        for line in self.proc.stdout:
            if line.startswith("\x1e"):
                return int(line[1:]), "".join(lines)
            lines.append(line)
        return None, "".join(lines)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait()


def server_default() -> bool:
    return os.environ.get("MYBUILD_MLC_SERVER", "1").strip() != "0"


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


@functools.cache
def resolved(path: str) -> Path:
    """Path(path).resolve(), once per path: every manifest names the shared
    imports again, and resolving a path stats each of its directories."""
    return Path(path).resolve()


def source_relpath(path: Path) -> Path:
    try:
        return resolved(str(path)).relative_to(REPO_ROOT)
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
        dependency = resolved(raw_path)
        if not dependency.is_file():
            raise BuildError(f"Dependency does not exist: {dependency}")
        dependencies.append(dependency)
    return dependencies


def default_jobs() -> int:
    """MYBUILD_JOBS, else one job per CPU. A runner that already runs several
    builds at once sets MYBUILD_JOBS so they do not each take every CPU."""
    configured = os.environ.get("MYBUILD_JOBS", "")
    if configured.strip():
        return max(1, int(configured))
    return os.cpu_count() or 1


class FileHashes:
    """Content hashes, each file read once per build. Missing files hash to None."""

    def __init__(self):
        self._hashes = {}
        self._lock = threading.Lock()

    def get(self, path) -> str | None:
        key = str(path)
        with self._lock:
            if key in self._hashes:
                return self._hashes[key]
        try:
            digest = hashlib.blake2b(Path(key).read_bytes(), digest_size=16).hexdigest()
        except OSError:
            digest = None
        with self._lock:
            self._hashes[key] = digest
        return digest


def project_config(source: Path, cache: dict) -> Path | None:
    """The mylang.toml mlc reads for source: the first one in its directory or
    above (driver_compile.c, project_config_path)."""
    directory = source.parent
    if directory in cache:
        return cache[directory]
    found = None
    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / "mylang.toml"
        if candidate.is_file():
            found = candidate
            break
    cache[directory] = found
    return found


def write_json_atomically(path: Path, value) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def read_stamp(path: Path):
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return stamp if isinstance(stamp, dict) else None


@dataclass
class Unit:
    src: Path
    rel: Path
    kind: str  # "ml" or "masm"
    out_masm: Path
    config: Path | None
    deps: list = field(default_factory=list)
    rebuilt: bool = False

    @property
    def ml_depfile(self) -> Path:
        return Path(str(self.out_masm) + ".ml-deps")

    @property
    def asm_depfile(self) -> Path:
        return Path(str(self.out_masm) + ".asm-deps")

    @property
    def out_mobj(self) -> Path:
        return self.out_masm.with_suffix(".mobj")

    @property
    def out_mbin(self) -> Path:
        return self.out_masm.with_suffix(".mbin")

    @property
    def stamp(self) -> Path:
        return Path(str(self.out_masm) + ".stamp")

    def outputs(self):
        outputs = [self.out_mobj, self.asm_depfile]
        if self.kind == "ml":
            outputs += [self.out_masm, self.ml_depfile]
        elif self.src != self.out_masm:
            outputs.append(self.out_masm)
        return outputs

    def depfiles(self):
        return [self.ml_depfile, self.asm_depfile] if self.kind == "ml" else [self.asm_depfile]


@dataclass
class Target:
    """One linked image: its root sources (files or directories) and how it
    is linked."""
    roots: list
    out: Path
    base: str | None = None
    header: bool = False


class Builder:
    """Builds targets that share one build directory and one set of compile
    options. A source several targets import is compiled once."""

    def __init__(self, build_dir: Path, *, entry=None, redirects=(), error_trace=False,
                 excludes=(), include_masm=False, jobs=None, asm_report=False, out=None,
                 mlc_server=None):
        self.build_dir = Path(build_dir).resolve()
        self.entry = entry
        self.redirects = list(redirects)
        self.error_trace = error_trace
        self.excludes = list(excludes)
        self.include_masm = include_masm
        self.jobs = max(1, jobs or default_jobs())
        self.asm_report = asm_report
        self.out = out or sys.stdout
        self.hashes = FileHashes()
        self.units = {}
        self.out_map = {}
        self.config_cache = {}
        self.print_lock = threading.Lock()
        self.use_server = server_default() if mlc_server is None else mlc_server
        self.thread_state = threading.local()
        self.servers = []
        self.servers_lock = threading.Lock()

    # Output -------------------------------------------------------------

    def emit(self, text: str) -> None:
        if not text:
            return
        with self.print_lock:
            self.out.write(text if text.endswith("\n") else text + "\n")
            self.out.flush()

    # Units --------------------------------------------------------------

    def unit_for(self, src: Path, rel: Path, kind: str) -> tuple:
        """The unit for src and whether it is new."""
        if src in self.units:
            return self.units[src], False
        out_masm = self.build_dir / (rel.with_suffix(".masm") if kind == "ml" else rel)
        if out_masm in self.out_map and self.out_map[out_masm] != src:
            raise BuildError(f"Output collision: {out_masm} from {src} and {self.out_map[out_masm]}")
        self.out_map[out_masm] = src
        unit = Unit(src, rel, kind, out_masm, project_config(src, self.config_cache))
        self.units[src] = unit
        return unit, True

    def mlc_command(self, unit: Unit):
        cmd = [MLC, "--line-info"]
        if self.entry:
            cmd += ["-entry", self.entry]
        # Pass redirects through to MLC as well. This is essential for a call
        # whose callee is defined in the same source file: otherwise
        # MyAssembler resolves it before the linker can redirect it.
        for redirect in self.redirects:
            cmd += ["--redirect-call", redirect]
        if self.error_trace:
            cmd += ["--error-trace"]
        return cmd + ["--depfile", unit.ml_depfile, unit.src, unit.out_masm]

    def myas_command(self, unit: Unit):
        # Resolve assembly `from` paths against the source location, not
        # against its copied build artifact.
        asm_input = unit.out_masm if unit.kind == "ml" else unit.src
        cmd = [MYAS, asm_input, unit.out_mbin, "--obj", unit.out_mobj, "--depfile", unit.asm_depfile]
        return cmd + (["--report"] if self.asm_report else [])

    def unit_key(self, unit: Unit) -> str:
        """What the unit's outputs depend on besides its sources."""
        parts = [
            STAMP_VERSION, unit.kind,
            [str(c) for c in self.mlc_command(unit)] if unit.kind == "ml" else None,
            [str(c) for c in self.myas_command(unit)],
            self.hashes.get(MLC) if unit.kind == "ml" else None,
            self.hashes.get(MYAS),
            str(unit.config) if unit.config else None,
        ]
        return hashlib.blake2b(json.dumps(parts).encode(), digest_size=16).hexdigest()

    def unit_is_current(self, unit: Unit) -> bool:
        stamp = read_stamp(unit.stamp)
        if not stamp or stamp.get("key") != self.unit_key(unit):
            return False
        inputs = stamp.get("inputs")
        if not isinstance(inputs, dict) or str(unit.src) not in inputs:
            return False
        if not all(path.exists() for path in unit.outputs()):
            return False
        return all(self.hashes.get(path) == digest for path, digest in inputs.items())

    def unit_dependencies(self, unit: Unit) -> list:
        dependencies = []
        for depfile in unit.depfiles():
            dependencies += read_dependency_file(depfile)
        return dependencies

    def run_tool(self, unit: Unit, cmd, log: list) -> None:
        proc = subprocess.run(
            [str(c) for c in cmd], cwd=REPO_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
        )
        log.append(command_line(cmd) + "\n" + proc.stdout)
        if proc.returncode != 0:
            raise UnitFailed(unit.src, proc.returncode, [str(c) for c in cmd], "".join(log))

    def server(self):
        """This worker's mlc server, started on first use."""
        server = getattr(self.thread_state, "server", None)
        if server is None:
            server = MlcServer()
            self.thread_state.server = server
            with self.servers_lock:
                self.servers.append(server)
        return server

    def close_servers(self) -> None:
        with self.servers_lock:
            servers, self.servers = self.servers, []
        for server in servers:
            server.close()

    def compile_unit(self, unit: Unit, log: list) -> None:
        """mlc on the unit, through this worker's server when there is one."""
        cmd = self.mlc_command(unit)
        if self.use_server:
            server = self.server()
            if not server.serving:
                # An mlc built before --serve: the build goes on without servers.
                self.use_server = False
                self.thread_state.server = None
            else:
                status, output = server.compile(cmd[1:])
                if status == 0:
                    log.append(command_line(cmd) + "\n" + output)
                    return
                if status is None:
                    # The server ended, on a compile error as a rule; the next
                    # unit starts another.
                    self.thread_state.server = None
        # Failed, could not reuse a kept module, or no server: an mlc of its
        # own compiles the unit, and its result and diagnostics are the ones
        # that count.
        self.run_tool(unit, cmd, log)

    def build_unit(self, unit: Unit) -> str:
        """Run in a worker: build the unit unless it is current, then read
        what it imports. Returns the unit's log."""
        if self.unit_is_current(unit):
            unit.deps = self.unit_dependencies(unit)
            return ""
        # Until the build succeeds the outputs match no stamp: a stamp left
        # over would vouch for them if the source went back to what it was.
        unit.stamp.unlink(missing_ok=True)
        unit.out_masm.parent.mkdir(parents=True, exist_ok=True)
        self.hashes.get(unit.src)  # as the tools are about to read it
        log = []
        if unit.kind == "ml":
            self.compile_unit(unit, log)
        elif unit.src != unit.out_masm:
            shutil.copy2(unit.src, unit.out_masm)
        self.run_tool(unit, self.myas_command(unit), log)
        unit.deps = self.unit_dependencies(unit)
        unit.rebuilt = True
        return "".join(log)

    def build_units(self, roots: list) -> None:
        """Build every unit reachable from roots, jobs at a time."""
        failures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.jobs) as pool:
            running = {}

            def submit(unit):
                running[pool.submit(self.build_unit, unit)] = unit

            for src, rel, kind in roots:
                unit, new = self.unit_for(src, rel, kind)
                if new:
                    submit(unit)
            while running:
                done, _ = concurrent.futures.wait(running, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    unit = running.pop(future)
                    try:
                        self.emit(future.result())
                    except (UnitFailed, BuildError) as exc:
                        failures.append(exc)
                        continue
                    except OSError as exc:
                        failures.append(BuildError(f"{unit.src}: {exc}"))
                        continue
                    if failures:
                        continue
                    for dependency in unit.deps:
                        kind = source_kind_for_path(dependency)
                        if not kind:
                            continue
                        dep_unit, new = self.unit_for(dependency, source_relpath(dependency), kind)
                        if new:
                            submit(dep_unit)
        if failures:
            # Every failure's output last, so the first diagnostic in the log
            # is the one that stopped the build.
            for failure in failures:
                if isinstance(failure, UnitFailed):
                    self.emit(failure.output)
            raise failures[0]

    def closure(self, src: Path) -> list:
        seen = {src}
        stack = [src]
        while stack:
            for dependency in self.units[stack.pop()].deps:
                if dependency in self.units and dependency not in seen:
                    seen.add(dependency)
                    stack.append(dependency)
        return sorted(seen)

    def write_unit_stamps(self) -> None:
        for unit in self.units.values():
            if not unit.rebuilt:
                continue
            sources = self.closure(unit.src)
            inputs = {str(path): self.hashes.get(path) for path in sources}
            for path in sources:
                config = self.units[path].config
                if config:
                    inputs[str(config)] = self.hashes.get(config)
            write_json_atomically(unit.stamp, {"key": self.unit_key(unit), "inputs": inputs})

    # Linking ------------------------------------------------------------

    def link_order(self, roots: list) -> list:
        """The objects in the order a one-at-a-time build finds them: the
        roots, then each unit's imports as its manifests list them, breadth
        first. heap_sym goes last so the heap is at the end of the binary."""
        order = [src for src, _, _ in roots]
        seen = set(order)
        index = 0
        while index < len(order):
            for dependency in self.units[order[index]].deps:
                if dependency in self.units and dependency not in seen:
                    seen.add(dependency)
                    order.append(dependency)
            index += 1
        objects = []
        for src in order:
            obj = self.units[src].out_mobj
            if obj not in objects:
                objects.append(obj)
        heap = [obj for obj in objects if obj.name == "heap_sym.mobj"]
        return [obj for obj in objects if obj.name != "heap_sym.mobj"] + heap

    def link(self, target: Target, roots: list) -> None:
        out_path = Path(target.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Emit a symbol map alongside the linked image so the profiler can attribute
        # program counters to function names. Named <output>.map next to the binary.
        map_path = out_path.with_suffix(out_path.suffix + ".map")
        lines_path = out_path.with_suffix(out_path.suffix + ".lines")
        objects = self.link_order(roots)

        cmd = [MLLINKER, "--map", map_path, "--lines", lines_path]
        if target.base:
            cmd += ["--base", target.base]
        if target.header:
            cmd.append("--header")
        for redirect in self.redirects:
            cmd += ["--redirect", redirect]
        cmd += [out_path, *objects]

        stamp_path = Path(str(out_path) + ".stamp")
        key = hashlib.blake2b(json.dumps([
            STAMP_VERSION, [str(c) for c in cmd], self.hashes.get(MLLINKER),
            [self.hashes.get(obj) for obj in objects],
        ]).encode(), digest_size=16).hexdigest()
        stamp = read_stamp(stamp_path)
        if stamp and stamp.get("key") == key and all(p.exists() for p in (out_path, map_path, lines_path)):
            self.emit(f"Link up to date: {out_path}")
        else:
            stamp_path.unlink(missing_ok=True)
            proc = subprocess.run(
                [str(c) for c in cmd], cwd=REPO_ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
            )
            self.emit(command_line(cmd) + "\n" + proc.stdout)
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, [str(c) for c in cmd], output=proc.stdout)
            write_json_atomically(stamp_path, {"key": key})
        self.emit(f"Linked output: {out_path}\nSymbol map: {map_path}")

    # Entry point ----------------------------------------------------------

    def build(self, targets: list) -> None:
        roots_of = []
        all_roots = []
        for target in targets:
            roots, _ = collect_root_sources([Path(p) for p in target.roots], self.excludes, self.include_masm)
            if not roots:
                raise BuildError(f"No sources found for {target.out}.")
            roots_of.append(roots)
            all_roots += roots
        self.build_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.build_units(all_roots)
        finally:
            self.close_servers()
        self.write_unit_stamps()
        rebuilt = sum(1 for unit in self.units.values() if unit.rebuilt)
        self.emit(f"{rebuilt} of {len(self.units)} sources built, "
                  f"{len(self.units) - rebuilt} up to date ({self.jobs} jobs)")
        for target, roots in zip(targets, roots_of):
            self.link(target, roots)


def check_clean_target(build_dir: Path, sources, cwd: Path | None = None) -> None:
    """Refuse a --clean that would delete more than build output: a build
    directory holding a source, the repository or the current directory."""
    build_dir = Path(build_dir).resolve()
    cwd = Path(cwd if cwd is not None else os.getcwd()).resolve()

    def encloses(path: Path) -> bool:
        return path == build_dir or build_dir in path.parents

    protected = [Path(source).resolve() for source in sources] + [REPO_ROOT, cwd]
    for path in protected:
        if encloses(path):
            raise BuildError(
                f"--clean would delete {build_dir}, which contains {path}; "
                "pass a separate --build-dir"
            )


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
    parser.add_argument("--error-trace", action="store_true",
                        default=os.environ.get("MYLANG_ERROR_TRACE") == "1",
                        help="Compile with mlc --error-trace (also MYLANG_ERROR_TRACE=1)")
    parser.add_argument("--redirect", action="append", default=[],
                        help="Redirect direct calls: <original>=<entry> (repeatable)")
    parser.add_argument("-j", "--jobs", type=int, default=None,
                        help="Sources built at once (default: MYBUILD_JOBS, else the CPU count)")
    parser.add_argument("--no-mlc-server", action="store_true",
                        help="Run an mlc per source rather than one `mlc --serve` per job")
    parser.add_argument("--asm-report", action="store_true",
                        help="Have myas write its debug report and hex dump beside each object")
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    build_dir = Path(args.build_dir).resolve() if args.build_dir else out_path.parent.resolve()
    if args.clean and build_dir.exists():
        check_clean_target(build_dir, args.sources)
        shutil.rmtree(build_dir)

    builder = Builder(
        build_dir, entry=args.entry, redirects=args.redirect, error_trace=args.error_trace,
        excludes=args.exclude, include_masm=args.masm, jobs=args.jobs, asm_report=args.asm_report,
        mlc_server=False if args.no_mlc_server else None,
    )
    builder.build([Target(roots=args.sources, out=out_path, base=args.base, header=args.header)])
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
