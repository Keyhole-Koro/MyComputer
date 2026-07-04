#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_paths import MYKERNEL_DIR, MYLANGTESTER_DIR


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg != "--verbose"]

    build = subprocess.run(["make"], cwd=MYLANGTESTER_DIR)
    if build.returncode != 0:
        return build.returncode

    runner = MYLANGTESTER_DIR / "build" / "mytest"
    test = MYKERNEL_DIR / "tests" / "serial" / "serial_rx.test.mln"
    return subprocess.run([str(runner), str(test), *args]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
