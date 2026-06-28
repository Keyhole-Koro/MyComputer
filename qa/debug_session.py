#!/usr/bin/env python3
"""Small debug-session helpers for QA runner scripts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    slug = slug.strip("-")
    return slug or "run"


def default_session_dir(base_dir: Path, name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return base_dir / f"{stamp}-{safe_slug(name)}"


class DebugSession:
    def __init__(self, session_dir: Path, name: str):
        self.session_dir = session_dir.resolve()
        self.name = name
        self.steps = []
        self.extra = {}
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "steps").mkdir(exist_ok=True)
        (self.session_dir / "artifacts").mkdir(exist_ok=True)
        (self.session_dir / "memory").mkdir(exist_ok=True)

    def path(self, *parts: str) -> Path:
        return self.session_dir.joinpath(*parts)

    def add_step(self, description: str, cmd, cwd: Path, returncode: int, log_path: Path):
        self.steps.append(
            {
                "description": description,
                "command": [str(c) for c in cmd],
                "cwd": str(cwd),
                "returncode": returncode,
                "log": str(log_path),
            }
        )
        self.write_manifest()

    def write_manifest(self, extra=None):
        if extra:
            self.extra.update(extra)
        payload = {
            "name": self.name,
            "session_dir": str(self.session_dir),
            "steps": self.steps,
        }
        payload.update(self.extra)
        self.path("manifest.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def append_combined_log(session: DebugSession, title: str, text: str):
    with session.path("combined.log").open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n===== {title} =====\n")
        fh.write(text)
        if text and not text.endswith("\n"):
            fh.write("\n")


def run_logged(cmd, cwd: Path, description: str, session: DebugSession, log_name: str):
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    log_path = session.path("steps", log_name)
    command_line = "+ " + " ".join(str(c) for c in cmd) + "\n"
    log_text = command_line + proc.stdout
    log_path.write_text(log_text, encoding="utf-8", errors="replace")
    append_combined_log(session, description, log_text)
    session.add_step(description, cmd, cwd, proc.returncode, log_path)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout)

    return proc.stdout


def copy_artifacts(src_dir: Path, session: DebugSession, suffixes=(".masm", ".mobj", ".mbin", ".bin", ".txt")):
    artifacts_dir = session.path("artifacts")
    src_dir = src_dir.resolve()

    # Walk manually so we can prune the "sessions" tree entirely. Recursing into
    # it would re-copy previous sessions' artifacts on every run, nesting them
    # deeper each time until the copy explodes (artifacts/sessions/.../sessions/...).
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "sessions"]
        root_path = Path(root)
        for name in files:
            src = root_path / name
            if src.suffix not in suffixes:
                continue
            rel = src.relative_to(src_dir)
            dst = artifacts_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
