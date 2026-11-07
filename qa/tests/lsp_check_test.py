#!/usr/bin/env python3
"""qa/tools/lsp_check.py tells the language server's mistakes from real errors."""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "qa" / "tools" / "lsp_check.py"

GOOD = "i32 main() { return 0; }\n"
BROKEN = "i32 main() { return 0 }\n"
FIXTURE = "toolchain/MyLangCompiler/tests/fail/on_purpose.mln"


def run(root, *arguments):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), *map(str, arguments)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def fake_compiler(path, status):
    """A compiler whose parser always gives the same answer."""
    path.write_text(f"#!/bin/sh\necho 'fake: rejected'\nexit {status}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


with tempfile.TemporaryDirectory() as work:
    scratch = Path(work)
    root = scratch / "tree"
    (root / FIXTURE).parent.mkdir(parents=True)
    (root / "good.mln").write_text(GOOD, encoding="utf-8")
    accepts = fake_compiler(scratch / "accepts", 0)
    rejects = fake_compiler(scratch / "rejects", 1)

    clean = run(root)
    assert clean.returncode == 0, clean.stdout
    assert clean.stdout == "1 sources checked, 0 findings\n", clean.stdout

    (root / "broken.mln").write_text(BROKEN, encoding="utf-8")
    (root / FIXTURE).write_text(BROKEN, encoding="utf-8")

    # Both reject it, so the source is wrong, and a fixture may be wrong on purpose.
    agreed = run(root)
    assert agreed.returncode == 1, agreed.stdout
    assert "broken.mln:1:" in agreed.stdout and ": error: " in agreed.stdout, agreed.stdout
    assert "on_purpose" not in agreed.stdout, agreed.stdout

    named = run(root, root / FIXTURE)
    assert named.returncode == 1 and "on_purpose.mln:1:" in named.stdout, named.stdout

    # mlc parses what the server marks, fixture or not.
    alarm = run(root, "--mlc", accepts)
    assert alarm.returncode == 1, alarm.stdout
    assert alarm.stdout.count("lsp false alarm") == 2, alarm.stdout

    # mlc rejects what the server passes.
    missed = run(root, "--mlc", rejects)
    assert missed.returncode == 1, missed.stdout
    assert "good.mln: lsp missed: fake: rejected" in missed.stdout, missed.stdout

    # A server that cannot check must not look like a clean tree.
    dead = run(root, "--checker", scratch / "no-such-checker")
    assert dead.returncode == 2, dead.stdout
    assert "did not answer" in dead.stdout, dead.stdout

    stuck = fake_compiler(scratch / "stuck", 0)
    silent = run(root, "--checker", stuck)
    assert silent.returncode == 2, silent.stdout

print("lsp check: ok")
