#!/usr/bin/env python3
"""qa/runners/build_toolchain.py without mlc, myas or mllinker.

Run with `python3 -m unittest discover -s qa/tests -p '*_unit_test.py'`.
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from qa.runners import build_toolchain  # noqa: E402

SCRIPT = REPO_ROOT / "qa" / "runners" / "build_toolchain.py"
SOURCE = "i32 main() { return 0; }\n"


def run_script(cwd: Path, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120,
    )


class CleanTest(unittest.TestCase):
    def test_clean_without_build_dir_keeps_the_sources(self):
        # The build directory defaults to the output's directory, which here
        # is the directory holding the source and everything else.
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / "x.mln").write_text(SOURCE, encoding="utf-8")
            (root / "notes.txt").write_text("keep me\n", encoding="utf-8")
            proc = run_script(root, "x.mln", "-o", "out.mbin", "--clean", "--no-mlc-server", "-j", "1")
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("--clean", proc.stdout)
            self.assertTrue((root / "x.mln").is_file(), proc.stdout)
            self.assertTrue((root / "notes.txt").is_file(), proc.stdout)

    def test_clean_of_an_enclosing_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / "src").mkdir()
            (root / "src" / "x.mln").write_text(SOURCE, encoding="utf-8")
            proc = run_script(root / "src", "x.mln", "-o", "out/x.mbin", "--build-dir", "..",
                              "--clean", "--no-mlc-server", "-j", "1")
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertTrue((root / "src" / "x.mln").is_file(), proc.stdout)

    def test_clean_of_a_separate_build_dir_still_cleans(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / "src").mkdir()
            (root / "src" / "x.mln").write_text(SOURCE, encoding="utf-8")
            build = root / "build"
            build.mkdir()
            (build / "stale.mobj").write_text("stale\n", encoding="utf-8")
            # Without a built toolchain the build itself fails after the
            # clean; with one it succeeds. Either way the stale file is gone.
            proc = run_script(root, "src/x.mln", "-o", "build/x.mbin", "--build-dir", "build",
                              "--clean", "--no-mlc-server", "-j", "1")
            self.assertFalse((build / "stale.mobj").exists(), proc.stdout)
            self.assertTrue((root / "src" / "x.mln").is_file(), proc.stdout)

    def test_check_clean_target(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            source = root / "src" / "x.mln"
            check = build_toolchain.check_clean_target
            for build_dir in (root, root / "src", REPO_ROOT, REPO_ROOT.parent, Path(root.anchor)):
                with self.subTest(build_dir=build_dir):
                    with self.assertRaises(build_toolchain.BuildError):
                        check(build_dir, [source], cwd=root / "elsewhere")
            with self.assertRaises(build_toolchain.BuildError):
                check(root / "build", [source], cwd=root / "build" / "sub")
            check(root / "build", [source], cwd=root)
            check(REPO_ROOT / "build", [REPO_ROOT / "system" / "x.mln"], cwd=REPO_ROOT)


class ExcludeTest(unittest.TestCase):
    def test_norm_rel(self):
        self.assertEqual(build_toolchain.norm_rel("\\a\\b\\"), "a/b")
        self.assertEqual(build_toolchain.norm_rel("/a/b/"), "a/b")

    def test_should_exclude(self):
        exclude = build_toolchain.should_exclude
        # A bare name matches any path component.
        self.assertTrue(exclude("a/tests/x.mln", ["tests"]))
        self.assertFalse(exclude("a/tests2/x.mln", ["tests"]))
        # A path matches itself and what is under it, from the root only.
        self.assertTrue(exclude("a/b", ["a/b"]))
        self.assertTrue(exclude("a/b/x.mln", ["a/b/"]))
        self.assertFalse(exclude("a/bc/x.mln", ["a/b"]))
        self.assertFalse(exclude("z/a/b/x.mln", ["a/b"]))
        self.assertTrue(exclude("a\\b\\x.mln", ["a/b"]))
        # Nothing to match, or nothing to match against.
        self.assertFalse(exclude("", ["a"]))
        self.assertFalse(exclude("a/x.mln", ["", "/"]))
        self.assertFalse(exclude("a/x.mln", []))


class DependencyFileTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.mln = self.root / "dep.mln"
        self.masm = self.root / "dep.masm"
        self.mln.write_text(SOURCE, encoding="utf-8")
        self.masm.write_text("", encoding="utf-8")

    def depfile(self, text: str) -> Path:
        path = self.root / "unit.ml-deps"
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_entries_in_order(self):
        path = self.depfile(f"MYDEPS 1\nmasm\t{self.masm}\n\nmln\t{self.mln}\n")
        self.assertEqual(build_toolchain.read_dependency_file(path), [self.masm, self.mln])

    def test_header_only(self):
        self.assertEqual(build_toolchain.read_dependency_file(self.depfile("MYDEPS 1\n")), [])

    def test_rejects(self):
        cases = {
            "empty": "",
            "header": f"MYDEPS 2\nmln\t{self.mln}\n",
            "no tab": f"MYDEPS 1\nmln {self.mln}\n",
            "unknown kind": f"MYDEPS 1\nobj\t{self.mln}\n",
            "relative path": "MYDEPS 1\nmln\tdep.mln\n",
            "wrong suffix": f"MYDEPS 1\nmln\t{self.masm}\n",
            "missing dependency": f"MYDEPS 1\nmln\t{self.root / 'gone.mln'}\n",
        }
        for name, text in cases.items():
            with self.subTest(name):
                with self.assertRaises(build_toolchain.BuildError):
                    build_toolchain.read_dependency_file(self.depfile(text))

    def test_missing_depfile(self):
        with self.assertRaises(build_toolchain.BuildError):
            build_toolchain.read_dependency_file(self.root / "absent.ml-deps")


class CollectRootSourcesTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        for name in ("tree/b.mln", "tree/a.masm", "tree/sub/c.mln", "tree/skip/d.mln",
                     "tree/notes.txt", "single.mln", "other.txt"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def names(self, sources):
        return [(path.name, kind) for path, _, kind in sources]

    def test_directory_without_masm(self):
        sources, seen = build_toolchain.collect_root_sources([self.root / "tree"], ["skip"], False)
        self.assertEqual(self.names(sources), [("b.mln", "ml"), ("c.mln", "ml")])
        self.assertEqual(seen, {path for path, _, _ in sources})

    def test_directory_with_masm_lists_mln_first(self):
        sources, _ = build_toolchain.collect_root_sources([self.root / "tree"], ["skip"], True)
        self.assertEqual(self.names(sources), [("b.mln", "ml"), ("c.mln", "ml"), ("a.masm", "masm")])

    def test_files_keep_their_order_and_appear_once(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            sources, _ = build_toolchain.collect_root_sources(
                [self.root / "single.mln", self.root / "other.txt", self.root / "tree",
                 self.root / "tree" / "b.mln"],
                [], False)
        self.assertEqual(self.names(sources),
                         [("single.mln", "ml"), ("b.mln", "ml"), ("c.mln", "ml"), ("d.mln", "ml")])
        self.assertIn("[WARN] Skip unsupported file", out.getvalue())

    def test_relative_path_inside_the_repository(self):
        source = REPO_ROOT / "qa" / "x.mln"
        self.assertEqual(build_toolchain.source_relpath(source), Path("qa/x.mln"))
        self.assertEqual(build_toolchain.source_relpath(self.root / "single.mln"), Path("single.mln"))


class BuilderTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.builder = build_toolchain.Builder(self.root / "build", jobs=1, mlc_server=False)

    def unit(self, builder, name, kind="ml"):
        src = self.root / "src" / name
        unit, _ = builder.unit_for(src, Path(name), kind)
        return unit

    def test_link_order_is_breadth_first_with_heap_last(self):
        a, b, c, d, heap = (self.unit(self.builder, f"{n}.mln") for n in ("a", "b", "c", "d", "heap_sym"))
        outside = self.root / "src" / "not_a_unit.mln"
        a.deps = [c.src, heap.src, outside, b.src]
        b.deps = [d.src]
        c.deps = [a.src, d.src]
        roots = [(a.src, a.rel, "ml"), (b.src, b.rel, "ml")]
        self.assertEqual(self.builder.link_order(roots),
                         [a.out_mobj, b.out_mobj, c.out_mobj, d.out_mobj, heap.out_mobj])

    def test_output_collision(self):
        self.builder.unit_for(self.root / "one" / "x.mln", Path("x.mln"), "ml")
        _, new = self.builder.unit_for(self.root / "one" / "x.mln", Path("x.mln"), "ml")
        self.assertFalse(new)
        with self.assertRaises(build_toolchain.BuildError):
            self.builder.unit_for(self.root / "two" / "x.mln", Path("x.mln"), "ml")

    def built_masm_unit(self):
        """A .masm unit whose outputs exist and whose stamp was written."""
        (self.root / "src").mkdir()
        (self.root / "src" / "mylang.toml").write_text("[project]\n", encoding="utf-8")
        (self.root / "src" / "a.masm").write_text("; one\n", encoding="utf-8")
        unit = self.unit(self.builder, "a.masm", "masm")
        self.assertEqual(unit.config, self.root / "src" / "mylang.toml")
        unit.out_masm.parent.mkdir(parents=True)
        for output in unit.outputs():
            output.write_text("", encoding="utf-8")
        unit.rebuilt = True
        self.builder.write_unit_stamps()
        return unit

    def is_current(self) -> bool:
        # A new builder, as the next build would be: hashes are read once per build.
        builder = build_toolchain.Builder(self.root / "build", jobs=1, mlc_server=False)
        return builder.unit_is_current(self.unit(builder, "a.masm", "masm"))

    def test_unchanged_unit_is_current(self):
        self.built_masm_unit()
        self.assertTrue(self.is_current())

    def test_changed_source_invalidates_the_stamp(self):
        self.built_masm_unit()
        (self.root / "src" / "a.masm").write_text("; two\n", encoding="utf-8")
        self.assertFalse(self.is_current())

    def test_changed_project_config_invalidates_the_stamp(self):
        self.built_masm_unit()
        (self.root / "src" / "mylang.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        self.assertFalse(self.is_current())

    def test_missing_output_invalidates_the_stamp(self):
        unit = self.built_masm_unit()
        unit.out_mobj.unlink()
        self.assertFalse(self.is_current())

    def test_unreadable_stamp_is_not_current(self):
        unit = self.built_masm_unit()
        for text in ("{", "[]", '{"key": "other", "inputs": {}}'):
            with self.subTest(text=text):
                unit.stamp.write_text(text, encoding="utf-8")
                self.assertFalse(self.is_current())


class StampFileTest(unittest.TestCase):
    def test_write_json_atomically_and_read_stamp(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "x.stamp"
            build_toolchain.write_json_atomically(path, {"key": "k", "inputs": {"a": "1"}})
            self.assertEqual(build_toolchain.read_stamp(path), {"key": "k", "inputs": {"a": "1"}})
            self.assertEqual(sorted(p.name for p in Path(work).iterdir()), ["x.stamp"])
            build_toolchain.write_json_atomically(path, ["not", "a", "stamp"])
            self.assertIsNone(build_toolchain.read_stamp(path))
            self.assertIsNone(build_toolchain.read_stamp(Path(work) / "absent.stamp"))


class DefaultJobsTest(unittest.TestCase):
    def test_mybuild_jobs(self):
        cpus = os.cpu_count() or 1
        for value, expected in (("3", 3), (" 2 ", 2), ("0", 1), ("-4", 1), ("", cpus), ("  ", cpus)):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"MYBUILD_JOBS": value}):
                    self.assertEqual(build_toolchain.default_jobs(), expected)
        with mock.patch.dict(os.environ):
            os.environ.pop("MYBUILD_JOBS", None)
            self.assertEqual(build_toolchain.default_jobs(), cpus)


if __name__ == "__main__":
    unittest.main()
