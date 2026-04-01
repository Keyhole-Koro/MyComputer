#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.project_paths import MYLINKER_DIR


def main() -> int:
    runner = MYLINKER_DIR / "test" / "run_integration_tests.py"
    cmd = ["python3", str(runner), *sys.argv[1:]]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
