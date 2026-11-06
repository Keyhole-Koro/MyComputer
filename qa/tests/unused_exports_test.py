#!/usr/bin/env python3
"""qa/tools/unused_exports.py against a tree of known exports."""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "qa" / "tools" / "unused_exports.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "unused_exports"

EXPECTED = {
    "dom.mln: unused function dom_Separator",
    "lib.mln: unused global lib_g_unread",
    "lib.mln: unused function lib_never_called",
    "lib.mln: unused function lib_only_recursive",
    "lib.mln: unused template never_instantiated",
    "lib.mln: unused template Pair__second",
    "lib.mln: unused method Key__raw",
}

ALLOWLIST = """# A comment, and a line with one after it.
dom.mln dom_Separator  # kept
lib.mln lib_g_unread
lib.mln lib_never_called
lib.mln lib_only_recursive
lib.mln never_instantiated
lib.mln Pair__second
lib.mln Key__raw
lib.mln gone_by_now
"""


def run(allow):
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(FIXTURE), "--allow", str(allow)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def findings(output):
    """Finding lines, without the line numbers."""
    found = set()
    for line in output.splitlines():
        path, separator, rest = line.partition(":")
        if separator and ": unused " in line:
            found.add(f"{path}:{rest.split(':', 1)[1]}")
    return found


def main():
    with tempfile.TemporaryDirectory(prefix="unused-exports-test-") as work:
        allow = Path(work) / "allow.txt"

        result = run(allow)
        if result.returncode != 1:
            raise SystemExit(f"expected exit 1 without an allowlist:\n{result.stdout}")
        found = findings(result.stdout)
        if found != EXPECTED:
            raise SystemExit("wrong findings:\n"
                             f"  missing: {sorted(EXPECTED - found)}\n"
                             f"  unexpected: {sorted(found - EXPECTED)}")

        allow.write_text(ALLOWLIST, encoding="utf-8")
        result = run(allow)
        if result.returncode != 0 or findings(result.stdout):
            raise SystemExit(f"the allowlist should cover every finding:\n{result.stdout}")
        if "lib.mln gone_by_now" not in result.stdout:
            raise SystemExit(f"a stale entry should be mentioned:\n{result.stdout}")

        allow.write_text("lib.mln lib_never_called\n", encoding="utf-8")
        result = run(allow)
        if result.returncode != 1 or "lib.mln: unused function lib_never_called" in findings(result.stdout):
            raise SystemExit(f"an allowed finding should not be listed:\n{result.stdout}")
    print("[PASS] unused exports fixture")


if __name__ == "__main__":
    main()
