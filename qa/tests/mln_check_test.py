#!/usr/bin/env python3
"""qa/tools/mln_check.py against a tree of known errors."""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "qa" / "tools" / "mln_check.py"

SOURCES = {
    "good.mln": "i32 main() { return 0; }\n",
    "semantic.mln": "i32 main() { return nope; }\n",
    "syntax.mln": "i32 main( {\n}\n",
    "toolchain/MyLangCompiler/tests/fail/on_purpose.mln": "i32 main() { return gone; }\n",
    "toolchain/MyLangCompiler/docs/example.mln": "i32 main() { return stale; }\n",
}


def run(root, *paths):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), *map(str, paths)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


with tempfile.TemporaryDirectory() as work:
    root = Path(work)
    for name, text in SOURCES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")

    everything = run(root)
    assert everything.returncode == 1, everything.stdout
    assert "semantic.mln:1:21: error[E0001]" in everything.stdout, everything.stdout
    assert "syntax.mln:1:" in everything.stdout, everything.stdout
    assert "gone" not in everything.stdout, everything.stdout
    assert "stale" in everything.stdout, everything.stdout
    assert everything.stdout.endswith("4 sources checked, 3 with errors\n"), everything.stdout

    named = run(root, root / "good.mln")
    assert named.returncode == 0 and named.stdout == "1 sources checked, 0 with errors\n", named.stdout

    fixture = run(root, root / "toolchain/MyLangCompiler/tests/fail")
    assert fixture.returncode == 1 and "gone" in fixture.stdout, fixture.stdout

    missing = run(root, root / "missing.mln")
    assert missing.returncode == 1 and "does not exist" in missing.stdout, missing.stdout

print("mln check: ok")
