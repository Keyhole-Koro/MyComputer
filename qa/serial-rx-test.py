#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_paths import MYKERNEL_DIR


def main() -> int:
    runner = MYKERNEL_DIR / "tests" / "run_serial_rx_test.py"
    cmd = ["python3", str(runner), *sys.argv[1:]]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
