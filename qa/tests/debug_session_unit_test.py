#!/usr/bin/env python3
"""qa/tools/debug_session.py, which every runner logs through.

Run with `python3 -m unittest discover -s qa/tests -p '*_unit_test.py'`.
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from qa.tools import debug_session  # noqa: E402


class SlugTest(unittest.TestCase):
    def test_safe_slug(self):
        self.assertEqual(debug_session.safe_slug("hello world/x"), "hello-world-x")
        self.assertEqual(debug_session.safe_slug("a.b_c-d"), "a.b_c-d")
        self.assertEqual(debug_session.safe_slug("  --kernel--  "), "kernel")
        self.assertEqual(debug_session.safe_slug("../../etc"), "..-..-etc")
        self.assertEqual(debug_session.safe_slug("日本"), "run")
        self.assertEqual(debug_session.safe_slug(""), "run")

    def test_default_session_dir(self):
        path = debug_session.default_session_dir(Path("/base"), "my run")
        self.assertEqual(path.parent, Path("/base"))
        self.assertRegex(path.name, r"^\d{8}-\d{6}-my-run$")


class SummarizeFailureTest(unittest.TestCase):
    def test_first_diagnostic_with_its_context(self):
        output = "\n".join([
            "+ mlc foo.mln",
            "src/foo.mln:12:5: error[E0001]: unknown name 'nope'",
            "  12 | return nope;",
            "     |        ^",
            "src/bar.mln:1:1: error: second",
            "  ignored",
        ])
        self.assertEqual(debug_session.summarize_failure(output), "\n".join([
            "src/foo.mln:12:5: error[E0001]: unknown name 'nope'",
            "  12 | return nope;",
            "     |        ^",
        ]))

    def test_warnings_and_fatal_errors_count(self):
        self.assertEqual(debug_session.summarize_failure("x\na.masm:3:1: warning: w\n"), "a.masm:3:1: warning: w")
        self.assertEqual(debug_session.summarize_failure("a.c:1:2: fatal error: f"), "a.c:1:2: fatal error: f")

    def test_context_is_at_most_eight_lines(self):
        output = "a.mln:1:1: error: e\n" + "".join(f"\tline {i}\n" for i in range(12))
        self.assertEqual(len(debug_session.summarize_failure(output).splitlines()), 9)

    def test_falls_back_to_the_tail(self):
        output = "\n".join(f"line {i}" for i in range(30))
        self.assertEqual(debug_session.summarize_failure(output, fallback_lines=3), "line 27\nline 28\nline 29")
        self.assertEqual(debug_session.summarize_failure("no position: error: here"), "no position: error: here")
        self.assertEqual(debug_session.summarize_failure(""), "")
        self.assertEqual(debug_session.summarize_failure(None), "")


class SessionTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()

    def manifest(self, session):
        return json.loads(session.path("manifest.json").read_text(encoding="utf-8"))

    def test_session_layout_and_manifest(self):
        session = debug_session.DebugSession(self.root / "s", "demo")
        for name in ("steps", "artifacts", "memory"):
            self.assertTrue(session.path(name).is_dir(), name)
        session.write_manifest({"entry": "main"})
        session.write_manifest()
        self.assertEqual(self.manifest(session),
                         {"name": "demo", "session_dir": str(self.root / "s"), "steps": [], "entry": "main"})

    def test_run_logged_success(self):
        session = debug_session.DebugSession(self.root / "s", "demo")
        cmd = [sys.executable, "-c", "print('hi')"]
        output = debug_session.run_logged(cmd, self.root, "say hi", session, "01-hi.log")
        self.assertEqual(output, "hi\n")
        log = session.path("steps", "01-hi.log").read_text(encoding="utf-8")
        self.assertEqual(log, "+ " + " ".join(cmd) + "\nhi\n")
        self.assertIn("===== say hi =====\n" + log, session.path("combined.log").read_text(encoding="utf-8"))
        (step,) = self.manifest(session)["steps"]
        self.assertEqual(step, {"description": "say hi", "command": cmd, "cwd": str(self.root),
                                "returncode": 0, "log": str(session.path("steps", "01-hi.log"))})

    def test_run_logged_failure(self):
        session = debug_session.DebugSession(self.root / "s", "demo")
        cmd = [sys.executable, "-c", "import sys; print('bad'); sys.exit(3)"]
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            debug_session.run_logged(cmd, self.root, "fail", session, "02-fail.log")
        self.assertEqual(raised.exception.returncode, 3)
        self.assertEqual(raised.exception.output, "bad\n")
        self.assertEqual(self.manifest(session)["steps"][0]["returncode"], 3)
        self.assertTrue(session.path("steps", "02-fail.log").read_text(encoding="utf-8").endswith("bad\n"))

    def test_run_logged_echo(self):
        session = debug_session.DebugSession(self.root / "s", "demo")
        cmd = [sys.executable, "-c", "print('one'); print('two')"]
        with contextlib.redirect_stdout(io.StringIO()) as echoed:
            output = debug_session.run_logged(cmd, self.root, "echo", session, "03-echo.log", echo_output=True)
        self.assertEqual(output, "one\ntwo\n")
        self.assertEqual(echoed.getvalue(), "one\ntwo\n")

    def test_copy_artifacts_skips_sessions_and_other_files(self):
        build = self.root / "build"
        for name in ("a.masm", "b.txt", "c.log", "sub/d.mobj", "sub/e.mbin.map",
                     "sessions/old/artifacts/f.masm"):
            path = build / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name, encoding="utf-8")
        # As the runners do: the session lives inside the directory it copies.
        session = debug_session.DebugSession(build / "sessions" / "now", "demo")
        debug_session.copy_artifacts(build, session)
        artifacts = session.path("artifacts")
        copied = sorted(str(p.relative_to(artifacts)) for p in artifacts.rglob("*") if p.is_file())
        self.assertEqual(copied, ["a.masm", "b.txt", "sub/d.mobj"])
        self.assertEqual((artifacts / "sub" / "d.mobj").read_text(encoding="utf-8"), "sub/d.mobj")

    def test_copy_artifacts_suffixes(self):
        build = self.root / "build"
        build.mkdir()
        (build / "a.masm").write_text("", encoding="utf-8")
        (build / "b.log").write_text("", encoding="utf-8")
        session = debug_session.DebugSession(self.root / "s", "demo")
        debug_session.copy_artifacts(build, session, suffixes=(".log",))
        self.assertEqual([p.name for p in session.path("artifacts").iterdir()], ["b.log"])


if __name__ == "__main__":
    unittest.main()
