#!/usr/bin/env python3
"""Compatibility wrapper for the flattened QA script layout."""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / "mlc-test.py"), run_name="__main__")
