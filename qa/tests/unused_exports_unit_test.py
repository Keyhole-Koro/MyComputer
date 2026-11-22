#!/usr/bin/env python3
"""qa/tools/unused_exports.py's decisions, from symbol lines written by hand.

unused_exports_test.py runs the whole tool with a built mlc; this needs none.
Run with `python3 -m unittest discover -s qa/tests -p '*_unit_test.py'`.
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from qa.tools import unused_exports  # noqa: E402

ROOT = Path("/project")


def define(kind, symbol, path, line=1):
    return f"{kind}\t{symbol}\t{ROOT / path}\t{line}"


def use(user, symbol):
    return f"use\t{user}\t{symbol}"


def instance(symbol, path, line):
    return f"instance\t{symbol}\t{ROOT / path}\t{line}"


def findings(*units, assembly=()):
    program = unused_exports.Program(ROOT)
    for lines in units:
        program.add_unit(lines)
    for text in assembly:
        program.add_assembly(text)
    return [(f.path, f.symbol) for f in program.findings()]


class ProgramTest(unittest.TestCase):
    def test_unused_function_is_reported_and_used_one_is_not(self):
        unit = [define("function", "used", "a.mln"), define("function", "unused", "a.mln", 2),
                define("function", "caller", "b.mln"), use("caller", "used")]
        self.assertEqual(findings(unit), [("a.mln", "unused"), ("b.mln", "caller")])

    def test_use_from_another_unit_counts(self):
        self.assertEqual(findings([define("global", "g", "a.mln")], [use("main", "g")]), [])

    def test_self_recursion_is_not_a_use(self):
        unit = [define("function", "f", "a.mln"), use("f", "f")]
        self.assertEqual(findings(unit), [("a.mln", "f")])

    def test_never_reported(self):
        unit = [
            define("impl", "Show_i32_show", "a.mln"),
            *(define("function", name, "a.mln") for name in sorted(unused_exports.ENTRY_POINTS)),
            define("function", "rows_insert", "db/rows.model.mln"),
            define("function", "fixture_only", "toolchain/MyLangCompiler/tests/x.mln"),
            *(define("function", name, "mock.mln") for name in sorted(unused_exports.TEST_RUNNER_USES)),
        ]
        self.assertEqual(findings(unit), [])

    def test_fixture_tree_prefix_must_be_a_whole_directory(self):
        unit = [define("function", "f", "toolchain/MyLangCompiler/tests2/x.mln")]
        self.assertEqual(findings(unit), [("toolchain/MyLangCompiler/tests2/x.mln", "f")])

    def test_template_used_through_an_instance(self):
        template = define("template", "List_push", "list.mln", 5)
        unused = define("template", "List_pop", "list.mln", 9)
        unit = [instance("List_push__i32", "list.mln", 5), use("main", "List_push__i32")]
        self.assertEqual(findings([template, unused], unit), [("list.mln", "List_pop")])

    def test_template_used_only_by_itself_is_unused(self):
        template = define("template", "walk", "tree.mln", 3)
        unit = [instance("walk__i32", "tree.mln", 3), use("walk__i32", "walk__i32")]
        self.assertEqual(findings([template], unit), [("tree.mln", "walk")])

    def test_template_used_from_another_template_instance(self):
        outer = define("template", "outer", "t.mln", 1)
        inner = define("template", "inner", "t.mln", 2)
        unit = [instance("outer__i32", "t.mln", 1), instance("inner__i32", "t.mln", 2),
                use("outer__i32", "inner__i32")]
        # inner is used by outer's instance; nothing uses outer.
        self.assertEqual(findings([outer, inner], unit), [("t.mln", "outer")])

    def test_assembly_mentions_count_but_comments_do_not(self):
        unit = [define("function", "called", "a.mln"), define("function", "commented", "a.mln")]
        assembly = ["    CALL called ; commented\n; commented\n"]
        self.assertEqual(findings(unit, assembly=assembly), [("a.mln", "commented")])

    def test_one_finding_per_path_and_symbol_in_order(self):
        unit = [define("function", "z", "b.mln", 7), define("function", "z", "b.mln", 7),
                define("function", "y", "b.mln"), define("function", "x", "a.mln")]
        program = unused_exports.Program(ROOT)
        program.add_unit(unit)
        result = program.findings()
        self.assertEqual([(f.path, f.symbol) for f in result],
                         [("a.mln", "x"), ("b.mln", "y"), ("b.mln", "z")])
        self.assertEqual(result[2].line, 7)


class HelperTest(unittest.TestCase):
    def test_under(self):
        under = unused_exports.under
        self.assertTrue(under("a/b", ["a/b"]))
        self.assertTrue(under("a/b/c.mln", ["x", "a/b"]))
        self.assertFalse(under("a/bc/d.mln", ["a/b"]))
        self.assertFalse(under("a/b", []))

    def test_allowlist(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "allow.txt"
            self.assertEqual(unused_exports.read_allowlist(path), set())
            path.write_text("# header\n\n  a.mln f  # why\nb.mln g\n   # only a comment\n", encoding="utf-8")
            self.assertEqual(unused_exports.read_allowlist(path), {("a.mln", "f"), ("b.mln", "g")})

            found = [unused_exports.Definition("function", "h", "c.mln", 3)]
            unused_exports.write_allowlist(path, found)
            self.assertEqual(unused_exports.read_allowlist(path), {("c.mln", "h")})
            self.assertTrue(path.read_text(encoding="utf-8").startswith("# "))

    def test_find_sources(self):
        names = (
            "a.mln", "b.masm", "c.txt", "z/d.mln", "z/e_gen_test.mln",
            "build/x.mln", "node_modules/x.mln", "target/x.mln", "__pycache__/x.mln",
            ".hidden/x.mln", "qa/tests/fixtures/x.mln", "qa/tests/kept.mln",
            "toolchain/MyAssembler/tests/x.masm", "toolchain/MyAssembler/src/y.masm",
        )
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for name in names:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("", encoding="utf-8")
            self.assertEqual(unused_exports.find_sources(root), [
                "a.mln", "b.masm", "qa/tests/kept.mln", "toolchain/MyAssembler/src/y.masm", "z/d.mln",
            ])


if __name__ == "__main__":
    unittest.main()
