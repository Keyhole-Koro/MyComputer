#!/usr/bin/env python3
"""qa/runners/build_toolchain.py without mlc, myas or mllinker.

Run with `python3 -m unittest discover -s qa/tests -p '*_unit_test.py'`.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
